"""
handlers/admin_dashboard.py — Web admin dashboard (Phase 6b).

Session-authenticated HTTP routes for feature flags, stats, and user moderation.
"""

import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from config import settings
from db.postgres import get_pool
from db.redis_client import get_redis
from services.admin import get_stats_dict, list_flags, list_users, set_block_status, toggle_flag
from utils.security import SESSION_TTL_SECONDS, create_session_token, verify_session_token

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

LOGIN_RATE_LIMIT_MAX = 5
LOGIN_RATE_LIMIT_WINDOW = 300  # 5 minutes


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def is_login_rate_limited(redis, ip: str) -> bool:
    key = f"admin_login_attempts:{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, LOGIN_RATE_LIMIT_WINDOW)
    return count > LOGIN_RATE_LIMIT_MAX


async def require_admin_session_api(request: Request) -> None:
    token = request.cookies.get("admin_session")
    if not token or not verify_session_token(token, settings.admin_session_secret):
        raise HTTPException(status_code=401, detail="Not authenticated")


def _session_cookie_secure() -> bool:
    return settings.env == "production"


@router.get("/admin/login")
async def login_page():
    return FileResponse(STATIC_DIR / "admin_login.html")


@router.post("/admin/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password", "")
    ip = get_client_ip(request)
    redis = get_redis()
    if await is_login_rate_limited(redis, ip):
        return JSONResponse(
            {"detail": "Too many attempts — try again later."},
            status_code=429,
        )
    if not settings.admin_dashboard_password or not hmac.compare_digest(
        password, settings.admin_dashboard_password
    ):
        return RedirectResponse("/admin/login?error=1", status_code=303)
    token = create_session_token(settings.admin_session_secret)
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        "admin_session",
        token,
        httponly=True,
        secure=_session_cookie_secure(),
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@router.post("/admin/logout")
async def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(
        "admin_session",
        httponly=True,
        secure=_session_cookie_secure(),
        samesite="lax",
    )
    return response


@router.get("/admin")
async def dashboard_page(request: Request):
    token = request.cookies.get("admin_session")
    if not token or not verify_session_token(token, settings.admin_session_secret):
        return RedirectResponse("/admin/login", status_code=303)
    return FileResponse(STATIC_DIR / "admin_dashboard.html")


@router.get("/admin/api/flags", dependencies=[Depends(require_admin_session_api)])
async def api_list_flags():
    return {"flags": await list_flags(get_pool())}


@router.post("/admin/api/flags/{key}/toggle", dependencies=[Depends(require_admin_session_api)])
async def api_toggle_flag(key: str):
    try:
        new_state = await toggle_flag(get_pool(), key)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown flag")
    return {"key": key, "enabled": new_state}


@router.get("/admin/api/stats", dependencies=[Depends(require_admin_session_api)])
async def api_stats():
    return await get_stats_dict(get_pool())


@router.get("/admin/api/users", dependencies=[Depends(require_admin_session_api)])
async def api_list_users(search: str = "", blocked_only: bool = False, page: int = 1):
    return await list_users(get_pool(), search or None, blocked_only, page)


@router.post("/admin/api/users/{psid}/block", dependencies=[Depends(require_admin_session_api)])
async def api_block_user(psid: str):
    if not await set_block_status(get_pool(), psid, True):
        raise HTTPException(status_code=404, detail="User not found")
    return {"psid": psid, "is_blocked": True}


@router.post("/admin/api/users/{psid}/unblock", dependencies=[Depends(require_admin_session_api)])
async def api_unblock_user(psid: str):
    if not await set_block_status(get_pool(), psid, False):
        raise HTTPException(status_code=404, detail="User not found")
    return {"psid": psid, "is_blocked": False}
