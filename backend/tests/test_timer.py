"""Timer start/switch/stop logic."""

from __future__ import annotations

from datetime import datetime

from app.services import timer as service
from app.services.timeutil import local_date


def test_start_creates_running_interval(db, user_id):
    interval = service.start(db, user_id, "sitting", "work")
    assert interval.posture == "sitting"
    assert interval.ended_at is None
    current = service.current_interval(db, user_id)
    assert current is not None
    assert current.id == interval.id


def test_switch_stops_previous_and_starts_new(db, user_id):
    first = service.start(db, user_id, "sitting", None)
    second = service.start(db, user_id, "standing", None)
    # Only one interval runs at a time.
    current = service.current_interval(db, user_id)
    assert current is not None
    assert current.id == second.id
    # The first interval is now closed with a computed duration.
    closed = db.query_one("SELECT * FROM sit_stand_sessions WHERE id = ?", [first.id])
    assert closed["ended_at"] is not None
    assert closed["duration_seconds"] is not None
    assert closed["duration_seconds"] >= 0


def test_stop_ends_running(db, user_id):
    service.start(db, user_id, "sitting", None)
    stopped = service.stop_running(db, user_id)
    assert stopped is not None
    assert stopped.ended_at is not None
    assert service.current_interval(db, user_id) is None


def test_stop_when_nothing_running_returns_none(db, user_id):
    assert service.stop_running(db, user_id) is None


def test_day_totals_aggregate_by_posture(db, user_id):
    sit = service.start(db, user_id, "sitting", None)
    service.patch_interval(
        db,
        user_id,
        sit.id,
        posture=None,
        started_at=datetime(2026, 6, 13, 0, 0, 0),
        ended_at=datetime(2026, 6, 13, 0, 10, 0),
        label=None,
        label_set=False,
    )
    day = service.day(db, user_id, local_date(datetime(2026, 6, 13, 0, 5, 0)))
    assert day.totals.sitting == 600


def test_patch_recomputes_duration_and_date(db, user_id):
    interval = service.start(db, user_id, "sitting", None)
    updated = service.patch_interval(
        db,
        user_id,
        interval.id,
        posture="standing",
        started_at=datetime(2026, 1, 1, 9, 0, 0),
        ended_at=datetime(2026, 1, 1, 9, 30, 0),
        label=None,
        label_set=False,
    )
    assert updated is not None
    assert updated.posture == "standing"
    assert updated.duration_seconds == 1800


def test_delete_interval(db, user_id):
    interval = service.start(db, user_id, "sitting", None)
    assert service.delete_interval(db, user_id, interval.id) is True
    assert service.current_interval(db, user_id) is None
