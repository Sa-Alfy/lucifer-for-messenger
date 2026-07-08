"""
main.py — FastAPI application entry point.

Includes:
  - Lifespan management: opens and gracefully drains connections to Postgres and Redis.
  - Webhook route: Facebook Messenger verification handshake and event receiver.
  - Web admin dashboard: administrative analytics and database flag controls.
  - Health check: connectivity check for Postgres and Redis (returns 200/503), reporting yt-dlp version.
  - Sentry integration: privacy-first error monitoring.
  - Event retention: startup cleanup of stale webhook idempotency records.
"""

import importlib.metadata
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import settings
from db.postgres import init_pool, close_pool, get_pool, ping as pg_ping
from db.redis_client import init_redis, close_redis, ping as redis_ping
from handlers.admin_dashboard import router as admin_dashboard_router
from handlers.webhook import router as webhook_router
from services.task_registry import wait_for_shutdown
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Graceful shutdown timeout ────────────────────────────────────────────────
# 90 seconds: long enough for a yt-dlp probe + download of a long-ish video on
# a slow connection (worst-case empirically is 60–90 s for a 10-minute clip).
# Render's SIGTERM grace window is configurable; the default is 30 s on the free
# plan.  Even if Render sends SIGKILL before this timeout fires, we've already
# given tasks the best chance we can — the log will show what was still pending.
_SHUTDOWN_TIMEOUT_SECONDS = 90.0


# ── Sentry initialization ────────────────────────────────────────────────────
# Gated on DSN being present — if SENTRY_DSN is empty, nothing happens and the
# import is never executed.  This keeps the dev/test path clean.
#
# PII-free configuration — all three settings matter:
#   send_default_pii=False  — disables IP, header, and cookie capture
#   with_locals=False       — disables local variable capture in stack frames.
#                             Without this, a frame containing `text` (message
#                             text) or `psid` would be captured automatically.
#   traces_sample_rate=0.0  — no APM/performance tracing, so no request URLs
#                             with PSIDs or query parameters are ever sent.
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=False,
        with_locals=False,
        traces_sample_rate=0.0,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
    )
    logger.info("Sentry initialised (PII capture disabled).")
else:
    logger.debug("SENTRY_DSN not set — Sentry disabled.")


# ── Webhook event retention helper ────────────────────────────────────────────

async def _cleanup_old_webhook_events(pool) -> int:
    """
    Delete processed_webhook_events rows older than 30 days.

    Facebook's maximum retry window is 24–48 hours, so 30 days is a 15–30×
    safety margin.  Any row that old will never be needed for idempotency again.

    Returns the number of rows deleted.  Returns 0 if the table is empty or if
    all rows are recent — safe to call on a brand-new deployment.
    """
    async with pool.acquire() as conn:
        # DELETE ... RETURNING * then len() is the portable pattern for asyncpg
        # (fetchval with a DELETE...RETURNING count(*) subquery also works, but
        # this is clearer).
        rows = await conn.fetch(
            "DELETE FROM processed_webhook_events "
            "WHERE processed_at < now() - INTERVAL '30 days' "
            "RETURNING event_id",
        )
        return len(rows)


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: initialise connections, run one-time maintenance.
    Shutdown: drain in-flight tasks, then close connections.

    Using lifespan (not deprecated on_event) as recommended by FastAPI 0.93+.
    """
    logger.info("Application starting up. env=%s", settings.env)

    # Init Postgres (retries internally via tenacity)
    await init_pool(settings.database_url)

    # Init Redis (retries internally via tenacity)
    await init_redis(settings.redis_url)

    # One-time startup maintenance — purge stale idempotency rows.
    # Runs exactly once per process start, not on every request.
    deleted = await _cleanup_old_webhook_events(get_pool())
    logger.info(
        "Startup: deleted %d stale processed_webhook_events row(s) (older than 30 days).",
        deleted,
    )

    logger.info("All connections established. Application ready.")

    yield  # ← application runs here

    logger.info("Application shutting down.")

    # Wait for in-flight background tasks before closing connections.
    # This prevents a mid-download or mid-AI-call task from having its DB/Redis
    # connection closed underneath it during a clean deploy.
    await wait_for_shutdown(_SHUTDOWN_TIMEOUT_SECONDS)

    await close_pool()
    await close_redis()
    logger.info("Shutdown complete.")


# ── Application ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Messenger AI Assistant",
    description="FastAPI Webhook Bot with error observability, graceful shutdown, and database retention.",
    version="0.8.0",
    lifespan=lifespan,
    # Disable docs in production; they're enabled in dev by default.
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url=None,
)

# ── Routers ───────────────────────────────────────────────────────────────────
# Messenger webhook (GET verification + POST event receiver)
app.include_router(webhook_router)

# Web admin dashboard (/admin/*)
app.include_router(admin_dashboard_router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/healthz", tags=["infrastructure"])
async def healthz() -> JSONResponse:
    """
    Connectivity health check for Postgres and Redis.

    Returns 200 only when BOTH Postgres and Redis respond successfully.
    Returns 503 with a per-service breakdown if either is degraded.

    Also reports the installed yt-dlp version so Render's health-check history
    gives us a lightweight audit trail of what version was running at any
    given deployment.

    Render uses this path to determine if traffic should be routed here.
    """
    db_ok = await pg_ping()
    redis_ok = await redis_ping()

    try:
        ytdlp_version = importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        ytdlp_version = "not-installed"

    payload = {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
        "ytdlp_version": ytdlp_version,
    }
    status_code = 200 if (db_ok and redis_ok) else 503
    return JSONResponse(content=payload, status_code=status_code)
