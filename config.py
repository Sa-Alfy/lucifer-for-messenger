"""
config.py — Application settings loaded from environment variables.

All configuration variables are declared with typed validation via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Runtime ─────────────────────────────────────────────────
    env: str = "dev"
    port: int = 8000
    log_level: str = "INFO"

    # ── Databases ───────────────────────────────────────────────
    # No default → pydantic will raise ValidationError on startup if missing.
    database_url: str
    redis_url: str

    # ── Facebook Messenger ──────────────────────────────────────
    fb_page_access_token: str = ""
    fb_app_secret: str = ""
    fb_verify_token: str = ""
    fb_page_id: str = ""

    # ── AI Providers (Groq, Gemini, Hugging Face) ───────────────
    groq_api_key: str = ""
    hf_api_key: str = ""
    gemini_api_key: str = ""

    # ── Utilities (OpenWeatherMap, etc.) ────────────────────────
    openweather_api_key: str = ""

    # ── Supabase Image & Video Storage ──────────────────────────
    supabase_url: str = ""
    supabase_service_key: str = ""

    # ── Admin Bootstrap ─────────────────────────────────────────
    admin_bootstrap_secret: str = ""

    # ── Web Admin Dashboard ─────────────────────────────────────
    admin_dashboard_password: str = ""
    admin_session_secret: str = ""

    # ── Observability & Monitoring ──────────────────────────────
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


# Single instance — import this everywhere.
# Raises pydantic.ValidationError immediately if required vars are absent.
settings = Settings()
