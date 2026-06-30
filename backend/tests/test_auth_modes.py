"""Auth-mode config and behaviour across none/password/google."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_config_defaults_are_neutral(monkeypatch):
    # No env: neutral OSS defaults.
    for var in ("NERVETRACK_AUTH_MODE", "NERVETRACK_TIMEZONE", "NERVETRACK_WEEK_START_DAY"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.auth_mode == "none"
    assert s.allow_registration is True
    assert s.timezone == "UTC"
    assert s.week_start_day == 0
