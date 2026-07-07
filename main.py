"""
main.py — FastAPI application entry point.

Phase 1: infrastructure only.
  - Lifespan: initialise / close Postgres pool and Redis client.
  - GET /healthz: real connectivity check — not a stub.

Phase 2 addition:
  - GET/POST /webhook: Facebook Messenger webhook (verification + event receiver).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config import settings
from db.postgres import init_pool, close_pool, ping as pg_ping
from db.redis_client import init_redis, close_redis, ping as redis_ping
from handlers.admin_dashboard import router as admin_dashboard_router
from handlers.webhook import router as webhook_router
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: initialise connections.
    Shutdown: close them gracefully.

    Using lifespan (not deprecated on_event) as recommended by FastAPI 0.93+.
    """
    logger.info("Application starting up. env=%s", settings.env)

    # Init Postgres (retries internally via tenacity)
    await init_pool(settings.database_url)

    # Init Redis (retries internally via tenacity)
    await init_redis(settings.redis_url)

    logger.info("All connections established. Application ready.")

    yield  # ← application runs here

    logger.info("Application shutting down.")
    await close_pool()
    await close_redis()
    logger.info("Shutdown complete.")


# ── Application ──────────────────────────────────────────────────
app = FastAPI(
    title="Messenger AI Assistant",
    description="Phase 2 — webhook core. Echo bot end-to-end.",
    version="0.2.0",
    lifespan=lifespan,
    # Disable docs in production; they're enabled in dev by default.
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url=None,
)

# ── Routers ───────────────────────────────────────────────────────
# Phase 2: Messenger webhook (GET verification + POST event receiver)
app.include_router(webhook_router)

# Phase 6b: Web admin dashboard (/admin/*)
app.include_router(admin_dashboard_router)


# ── Health check ─────────────────────────────────────────────────
@app.get("/healthz", tags=["infrastructure"])
async def healthz() -> JSONResponse:
    """
    Real connectivity health check — not a stub.

    Returns 200 only when BOTH Postgres and Redis respond successfully.
    Returns 503 with a per-service breakdown if either is degraded.

    Render uses this path to determine if traffic should be routed here.
    """
    db_ok = await pg_ping()
    redis_ok = await redis_ping()

    payload = {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }
    status_code = 200 if (db_ok and redis_ok) else 503
    return JSONResponse(content=payload, status_code=status_code)
