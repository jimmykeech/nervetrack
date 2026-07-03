"""Tingling timer table, models, service, and aggregation."""

from __future__ import annotations

from datetime import date

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


def test_start_creates_running_interval_with_level(db, user_id):
    from app.services import tingling
    iv = tingling.start(db, user_id, 4)
    assert iv.ended_at is None
    assert iv.level == 4
    cur = tingling.current_interval(db, user_id)
    assert cur is not None and cur.id == iv.id


def test_second_start_closes_the_first(db, user_id):
    from app.services import tingling
    first = tingling.start(db, user_id, 3)
    tingling.start(db, user_id, 6)
    closed = db.query_one("SELECT * FROM tingling_sessions WHERE id = ?", [first.id])
    assert closed["ended_at"] is not None


def test_recompute_writes_max_level_and_summed_minutes(db, user_id):
    from app.services import tingling
    from app.services.entries import get_entry
    d = date(2026, 6, 20)
    # Two completed intervals: levels 3 and 7; 600s (10m) and 1200s (20m) => 30m, max 7.
    for level, secs in ((3, 600), (7, 1200)):
        db.execute(
            "INSERT INTO tingling_sessions "
            "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
            "VALUES (?, ?, ?, '2026-06-20T09:00:00', '2026-06-20T09:10:00', ?)",
            [user_id, d, level, secs],
        )
    tingling._recompute_daily_tingling(db, user_id, d)
    entry = get_entry(db, user_id, d)
    assert entry is not None
    assert int(entry.tingling_level) == 7
    assert entry.tingling_duration_minutes == 30


def test_delete_last_interval_clears_daily_fields(db, user_id):
    from app.services import tingling
    from app.services.entries import get_entry
    iv = tingling.start(db, user_id, 5)
    tingling.stop(db, user_id)
    tingling.delete_interval(db, user_id, iv.id)
    entry = get_entry(db, user_id, iv.entry_date)
    # entry may exist but tingling fields cleared
    if entry is not None:
        assert entry.tingling_level is None
        assert entry.tingling_duration_minutes is None
