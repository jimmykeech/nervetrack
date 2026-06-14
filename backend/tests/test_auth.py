"""Google OAuth callback, allowlist, session, and logout.

The Google token exchange and id_token verification are monkeypatched so the
flow can be exercised without contacting Google.
"""

from __future__ import annotations

import pytest

from app.auth import OAUTH_STATE_COOKIE, SESSION_COOKIE
from app.config import get_settings

CALLBACK = "/api/v1/auth/google/callback"


@pytest.fixture()
def oauth_env(monkeypatch):
    monkeypatch.setenv("NERVETRACK_ALLOWED_EMAILS", "allowed@example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _mock_google(monkeypatch, email: str, sub: str = "sub-1", verified: bool = True):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id_token": "fake-id-token"}

    monkeypatch.setattr("app.routers.auth.httpx.post", lambda *a, **k: _Resp())
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda tok: {"sub": sub, "email": email, "email_verified": verified, "name": "Tester"},
    )


def test_allowed_email_logs_in(client, oauth_env, monkeypatch):
    _mock_google(monkeypatch, "allowed@example.com")
    client.cookies.set(OAUTH_STATE_COOKIE, "state123")
    r = client.get(
        CALLBACK, params={"code": "c", "state": "state123"}, follow_redirects=False
    )
    assert r.status_code == 302
    assert r.headers["location"].endswith("/")  # back to the app
    # Session cookie issued; /auth/me now works.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "allowed@example.com"


def test_returning_user_logs_in_again(client, oauth_env, monkeypatch):
    """A second login of the same account must not 500.

    Regression guard: upsert_user is find-or-create (it does not UPDATE the
    existing users row). The original DuckDB engine 500'd here because it could
    not UPDATE a row referenced by a foreign key; this test keeps the second
    login working regardless of engine.
    """
    _mock_google(monkeypatch, "allowed@example.com", sub="sub-repeat")

    client.cookies.set(OAUTH_STATE_COOKIE, "state-1")
    first = client.get(CALLBACK, params={"code": "c", "state": "state-1"}, follow_redirects=False)
    assert first.status_code == 302

    client.cookies.set(OAUTH_STATE_COOKIE, "state-2")
    second = client.get(CALLBACK, params={"code": "c", "state": "state-2"}, follow_redirects=False)
    assert second.status_code == 302
    assert second.headers["location"].endswith("/")  # back to the app, not an error
    assert client.get("/api/v1/auth/me").json()["email"] == "allowed@example.com"


def test_non_invited_email_rejected(client, oauth_env, monkeypatch):
    _mock_google(monkeypatch, "stranger@example.com")
    client.cookies.set(OAUTH_STATE_COOKIE, "state123")
    r = client.get(
        CALLBACK, params={"code": "c", "state": "state123"}, follow_redirects=False
    )
    assert r.status_code == 302
    assert "error=not_invited" in r.headers["location"]
    assert client.get("/api/v1/auth/me").status_code == 401


def test_bad_state_rejected(client, oauth_env, monkeypatch):
    _mock_google(monkeypatch, "allowed@example.com")
    client.cookies.set(OAUTH_STATE_COOKIE, "expected")
    r = client.get(
        CALLBACK, params={"code": "c", "state": "different"}, follow_redirects=False
    )
    assert r.status_code == 302
    assert "error=bad_state" in r.headers["location"]


def test_logout_clears_session(client, oauth_env, monkeypatch):
    _mock_google(monkeypatch, "allowed@example.com")
    client.cookies.set(OAUTH_STATE_COOKIE, "state123")
    client.get(CALLBACK, params={"code": "c", "state": "state123"}, follow_redirects=False)
    assert client.get("/api/v1/auth/me").status_code == 200

    client.post("/api/v1/auth/logout")
    client.cookies.delete(SESSION_COOKIE)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401
