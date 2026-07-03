"""Tingling timer table, models, service, and aggregation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.tingling import TinglingStart


def test_tingling_table_exists(db, user_id):
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "tingling_sessions" in tables


def test_tingling_start_requires_level():
    with pytest.raises(ValidationError):
        TinglingStart()  # no level
    with pytest.raises(ValidationError):
        TinglingStart(level=11)  # out of range
