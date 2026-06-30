"""Session and identity helpers.

Sessions are opaque random tokens. We store only their sha256 hash; the raw
token lives solely in the user's httpOnly cookie. Identity is established via
Google OAuth (see ``routers/auth.py``); ``verify_google_id_token`` is isolated
here so tests can monkeypatch it.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException
from passlib.context import CryptContext

from app.config import get_settings
from app.db import Database
from app.deps import db_dep
from app.services.seed import seed_user
from app.services.timeutil import now_utc

SESSION_COOKIE = "nervetrack_session"
OAUTH_STATE_COOKIE = "nervetrack_oauth_state"
LOCAL_USER_EMAIL = "local@localhost"

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_password_user(
    db: Database, email: str, password: str, name: str | None
) -> UUID:
    """Create a local password account. Raises ValueError if email exists."""
    if db.query_one("SELECT id FROM users WHERE email = ?", [email]):
        raise ValueError("email already registered")
    created = db.query_one(
        "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?) RETURNING id",
        [email, name, hash_password(password)],
    )
    assert created is not None
    seed_user(db, created["id"])
    return created["id"]


def authenticate(db: Database, email: str, password: str) -> UUID | None:
    row = db.query_one("SELECT id, password_hash FROM users WHERE email = ?", [email])
    if row is None or not row["password_hash"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return row["id"]


def get_or_create_local_user(db: Database) -> UUID:
    """Resolve the single local user (none mode), creating+seeding on first use."""
    existing = db.query_one("SELECT id FROM users WHERE email = ?", [LOCAL_USER_EMAIL])
    if existing:
        return existing["id"]
    created = db.query_one(
        "INSERT INTO users (google_sub, email, name) VALUES (NULL, ?, ?) RETURNING id",
        [LOCAL_USER_EMAIL, "Local"],
    )
    assert created is not None
    seed_user(db, created["id"])
    return created["id"]


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Database, user_id: UUID) -> str:
    """Create a session row and return the raw token for the cookie."""
    token = secrets.token_urlsafe(32)
    expires = now_utc() + timedelta(days=get_settings().session_ttl_days)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        [_hash_token(token), user_id, expires],
    )
    return token


def delete_session(db: Database, token: str) -> None:
    db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", [_hash_token(token)])


def user_for_token(db: Database, token: str) -> dict[str, Any] | None:
    return db.query_one(
        """
        SELECT u.*
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.expires_at > ?
        """,
        [_hash_token(token), now_utc()],
    )


def upsert_user(
    db: Database, google_sub: str, email: str, name: str | None
) -> tuple[UUID, bool]:
    """Find-or-create a user by Google subject. Returns (user_id, created).

    Existing users are returned as-is; we do not refresh email/name on login.
    The Google subject is the stable identity, so find-or-create is sufficient and
    the stored email/name reflect what Google returned at signup. (Refreshing them
    would be safe under SQLite if ever wanted — this find-or-create shape was first
    forced by the old DuckDB engine, which could not UPDATE a FK-referenced row.)
    """
    existing = db.query_one("SELECT id FROM users WHERE google_sub = ?", [google_sub])
    if existing:
        return existing["id"], False
    created = db.query_one(
        "INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?) RETURNING id",
        [google_sub, email, name],
    )
    assert created is not None
    seed_user(db, created["id"])
    return created["id"], True


def verify_google_id_token(id_token_str: str) -> dict[str, Any]:
    """Verify a Google ID token and return its claims.

    Isolated so tests can monkeypatch it without contacting Google.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(
        id_token_str,
        google_requests.Request(),
        get_settings().google_client_id,
    )


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Database = Depends(db_dep),
) -> UUID:
    """FastAPI dependency: resolve the signed-in user or raise 401."""
    if get_settings().auth_mode == "none":
        return get_or_create_local_user(db)
    if not session_token:
        raise HTTPException(401, "Not authenticated")
    user = user_for_token(db, session_token)
    if user is None:
        raise HTTPException(401, "Session expired or invalid")
    return user["id"]
