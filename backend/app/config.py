"""Application configuration loaded from the environment."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_origin(scheme: str, host: str, port: int | None) -> str:
    """Lowercase scheme+host+port origin, filling in the scheme's default port.

    Shared by the allowlist parser below and ``services/url_guard.py`` so an
    entry like ``https://gateway.internal`` matches an incoming
    ``https://gateway.internal:443`` URL.
    """
    return f"{scheme}://{host.lower()}:{port or _DEFAULT_PORTS.get(scheme, 0)}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NERVETRACK_", env_file=".env", extra="ignore")

    # Path to the SQLite database file.
    db_path: str = "/data/nervetrack.db"

    # Local timezone used to derive calendar dates from UTC timestamps.
    timezone: str = "UTC"

    # Day the tracking week starts on (0=Monday .. 6=Sunday). Default Monday.
    week_start_day: int = 0

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

    # Authentication mode: "none" (single local user, offline), "password"
    # (local email+password accounts), or "google" (invite-only Google OAuth).
    auth_mode: str = "none"
    # In password mode, allow open self-service registration. Turn off to lock
    # an instance after the intended accounts exist.
    allow_registration: bool = True

    # Secret used to derive the Fernet key that encrypts per-user LLM API keys
    # at rest. Any non-empty string works; keep it stable or stored keys become
    # undecryptable. Required before storing an API key.
    secret_key: str = ""

    # Operator escape hatch for the SSRF guard on the per-user LLM base_url
    # (see services/url_guard.py): comma-separated origins (scheme+host[:port])
    # that are allowed even though they would otherwise fail the multi-user
    # https-only / private-address checks, e.g. a deliberately-exposed internal
    # LLM gateway.
    llm_allowed_base_urls: str = ""

    def allowed_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}

    def llm_allowed_base_url_set(self) -> set[str]:
        origins = set()
        for entry in self.llm_allowed_base_urls.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = urlsplit(entry)
            if not parts.scheme or not parts.hostname:
                continue
            origins.add(normalize_origin(parts.scheme, parts.hostname, parts.port))
        return origins

    def is_multi_user(self) -> bool:
        return self.auth_mode in ("password", "google")


@lru_cache
def get_settings() -> Settings:
    return Settings()
