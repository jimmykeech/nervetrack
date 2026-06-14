"""Application configuration loaded from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NERVETRACK_", env_file=".env", extra="ignore")

    # Path to the SQLite database file.
    db_path: str = "/data/nervetrack.db"

    # Local timezone used to derive calendar dates from UTC timestamps.
    timezone: str = "Australia/Sydney"

    # Day the tracking week starts on (0=Monday .. 6=Sunday). Default Friday.
    week_start_day: int = 4

    # CORS origins allowed to call the API (the SvelteKit dev/prod frontend).
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Google OAuth + sessions ---
    google_client_id: str = ""
    google_client_secret: str = ""
    # Public callback URL registered in the Google console (browser-facing, i.e.
    # the frontend origin which proxies /api to the backend).
    oauth_redirect_uri: str = "http://localhost:3000/api/v1/auth/google/callback"
    # Where to send the browser after a successful login.
    frontend_url: str = "http://localhost:3000"
    # Invite list: comma-separated emails permitted to sign in. Empty = nobody.
    allowed_emails: str = ""
    session_ttl_days: int = 30
    # Mark the session cookie Secure (set true when served over https).
    cookie_secure: bool = False

    # Phase 2 placeholder — unused in Phase 1.
    anthropic_api_key: str = ""

    def allowed_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
