"""Auth-mode config and behaviour across none/password/google."""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from app import auth as auth_mod
from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture()
def none_mode(monkeypatch):
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_config_defaults_are_neutral(monkeypatch):
    # No env: neutral OSS defaults.
    for var in ("NERVETRACK_AUTH_MODE", "NERVETRACK_TIMEZONE", "NERVETRACK_WEEK_START_DAY"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.auth_mode == "none"
    assert s.allow_registration is True
    assert s.timezone == "UTC"
    assert s.week_start_day == 0


def test_none_mode_auto_single_user(db, none_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    # No cookie at all, yet /auth/me works and is the local user.
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "local@localhost"
    # Second call resolves the SAME user (no duplicate rows).
    c.get("/api/v1/auth/me")
    rows = db.query("SELECT id FROM users WHERE email = ?", ["local@localhost"])
    assert len(rows) == 1


def test_password_hash_roundtrip():
    h = auth_mod.hash_password("hunter2pass")
    assert h != "hunter2pass"
    assert auth_mod.verify_password("hunter2pass", h) is True
    assert auth_mod.verify_password("wrong", h) is False


def test_create_and_authenticate_password_user(db):
    uid = auth_mod.create_password_user(db, "a@example.com", "hunter2pass", "Ay")
    assert auth_mod.authenticate(db, "a@example.com", "hunter2pass") == uid
    assert auth_mod.authenticate(db, "a@example.com", "nope") is None
    assert auth_mod.authenticate(db, "missing@example.com", "x") is None
    with pytest.raises(ValueError):
        auth_mod.create_password_user(db, "a@example.com", "another", "Dup")
