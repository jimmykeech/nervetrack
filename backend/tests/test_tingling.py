"""Tingling timer table, models, service, and aggregation."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.models.tingling import TinglingStart
from app.services import tingling as service


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


def test_tingling_endpoints_flow(auth_client):
    r = auth_client.post("/api/v1/tingling/start", json={"level": 4})
    assert r.status_code == 200
    assert r.json()["ended_at"] is None
    r = auth_client.post("/api/v1/tingling/stop")
    assert r.status_code == 200
    assert auth_client.get("/api/v1/tingling/current").json() is None


def test_tingling_start_rejects_missing_level(auth_client):
    r = auth_client.post("/api/v1/tingling/start", json={})
    assert r.status_code == 422


def test_start_recomputes_previous_day_when_crossing_midnight(db, user_id):
    from datetime import date

    from app.services import tingling
    from app.services.entries import get_entry
    # A running interval left open on a prior day (600s worth), then Start next day.
    db.execute(
        "INSERT INTO tingling_sessions "
        "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
        "VALUES (?, '2026-06-20', 5, '2026-06-20T23:50:00', NULL, NULL)",
        [user_id],
    )
    tingling.start(db, user_id, 3)  # closes the prior-day interval, recomputes its day
    prev = get_entry(db, user_id, date(2026, 6, 20))
    assert prev is not None
    assert prev.tingling_duration_minutes is not None  # prior day was recomputed, not left stale
    assert int(prev.tingling_level) == 5


def _insert_running_tingling(db, user_id, level, started_at, entry_date):
    return db.query_one(
        "INSERT INTO tingling_sessions (user_id, entry_date, level, started_at) "
        "VALUES (?, ?, ?, ?) RETURNING *",
        [user_id, entry_date, level, started_at],
    )


def test_tingling_stop_splits_overnight_and_recomputes_each_day(db, user_id):
    _insert_running_tingling(db, user_id, 5, datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    service.stop(db, user_id, at=datetime(2026, 6, 14, 7, 0))
    rows = db.query(
        "SELECT entry_date, duration_seconds FROM tingling_sessions WHERE user_id = ? "
        "ORDER BY entry_date", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [7200, 25200]
    d13 = db.query_one(
        "SELECT tingling_duration_minutes FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, date(2026, 6, 13)],
    )
    d14 = db.query_one(
        "SELECT tingling_duration_minutes FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, date(2026, 6, 14)],
    )
    assert d13["tingling_duration_minutes"] == 120  # 7200s
    assert d14["tingling_duration_minutes"] == 420  # 25200s


def test_tingling_day_clips_running_overnight(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.tingling.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    _insert_running_tingling(db, user_id, 5, datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    today = service.day(db, user_id, date(2026, 6, 14))
    assert today.running is not None
    assert today.running.started_at == datetime(2026, 6, 14, 0, 0)
    assert today.running.ended_at is None
