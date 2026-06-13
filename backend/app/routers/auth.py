"""Google OAuth login, logout, and current-user endpoints."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    create_session,
    current_user,
    delete_session,
    upsert_user,
    verify_google_id_token,
)
from app.config import get_settings
from app.db import Database
from app.deps import db_dep

router = APIRouter(tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _set_session_cookie(resp, token: str) -> None:
    settings = get_settings()
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/auth/google/login")
def google_login():
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(500, "Google OAuth is not configured")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    # Short-lived state cookie to defend against CSRF on the callback.
    resp.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/auth/google/callback")
def google_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
    db: Database = Depends(db_dep),
):
    settings = get_settings()
    login_url = f"{settings.frontend_url}/login"

    def fail(reason: str) -> RedirectResponse:
        r = RedirectResponse(f"{login_url}?error={reason}", status_code=302)
        r.delete_cookie(OAUTH_STATE_COOKIE, path="/")
        return r

    if error or not code:
        return fail("oauth_failed")
    if not state or not oauth_state or not secrets.compare_digest(state, oauth_state):
        return fail("bad_state")

    # Exchange the authorization code for tokens.
    try:
        token_resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        id_token_str = token_resp.json()["id_token"]
        claims = verify_google_id_token(id_token_str)
    except Exception:
        return fail("oauth_failed")

    email = (claims.get("email") or "").lower()
    if not email or not claims.get("email_verified"):
        return fail("email_unverified")
    if email not in settings.allowed_email_set():
        return fail("not_invited")

    user_id, _created = upsert_user(db, claims["sub"], email, claims.get("name"))
    token = create_session(db, user_id)
    resp = RedirectResponse(f"{settings.frontend_url}/", status_code=302)
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    _set_session_cookie(resp, token)
    return resp


@router.post("/auth/logout")
def logout(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Database = Depends(db_dep),
):
    if session_token:
        delete_session(db, session_token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/auth/me")
def me(user_id: UUID = Depends(current_user), db: Database = Depends(db_dep)):
    row = db.query_one("SELECT email, name FROM users WHERE id = ?", [user_id])
    if row is None:
        raise HTTPException(401, "Not authenticated")
    return {"email": row["email"], "name": row["name"]}
