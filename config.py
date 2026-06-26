"""
config.py — Application settings loaded from environment variables.

Only `database_url` and `redis_url` are required in Phase 1.
All other keys are declared now so .env.example stays stable across phases.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Runtime ─────────────────────────────────────────────────
    env: str = "dev"
    port: int = 8000
    log_level: str = "INFO"

    # ── Required (Phase 1) ──────────────────────────────────────
    # No default → pydantic will raise ValidationError on startup if missing.
    database_url: str
    redis_url: str

    # ── Phase 2: Facebook Messenger ─────────────────────────────
    fb_page_access_token: str = ""
    fb_app_secret: str = ""
    fb_verify_token: str = ""
    fb_page_id: str = ""

    # ── Phase 3+: AI providers ──────────────────────────────────
    groq_api_key: str = ""
    hf_api_key: str = ""
    gemini_api_key: str = ""

    # ── Phase 6: Supabase management API ────────────────────────
    supabase_url: str = ""
    supabase_service_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


# Single instance — import this everywhere.
# Raises pydantic.ValidationError immediately if required vars are absent.
settings = Settings()
