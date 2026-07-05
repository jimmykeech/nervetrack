"""Timer start/switch/stop logic."""

from __future__ import annotations

from datetime import date, datetime

import pytest

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


def test_patch_rejects_end_not_after_start(db, user_id):
    interval = service.start(db, user_id, "sitting", None)
    with pytest.raises(ValueError):
        service.patch_interval(
            db,
            user_id,
            interval.id,
            posture=None,
            started_at=datetime(2026, 1, 1, 9, 0, 0),
            ended_at=datetime(2026, 1, 1, 9, 0, 0),  # equal -> invalid
            label=None,
            label_set=False,
        )


def test_patch_sets_and_clears_label(db, user_id):
    interval = service.start(db, user_id, "sitting", None)
    with_label = service.patch_interval(
        db, user_id, interval.id,
        posture=None, started_at=None, ended_at=None,
        label="focus", label_set=True,
    )
    assert with_label is not None and with_label.label == "focus"
    cleared = service.patch_interval(
        db, user_id, interval.id,
        posture=None, started_at=None, ended_at=None,
        label=None, label_set=True,
    )
    assert cleared is not None and cleared.label is None


def _insert_running(db, user_id, posture, started_at, entry_date):
    return db.query_one(
        "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at) "
        "VALUES (?, ?, ?, ?) RETURNING *",
        [user_id, entry_date, posture, started_at],
    )


def test_stop_splits_overnight_interval_into_per_day_rows(db, user_id):
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    service.stop_running(db, user_id, at=datetime(2026, 6, 14, 7, 0))
    rows = db.query(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? ORDER BY started_at", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [7200, 25200]
    assert all(r["posture"] == "lying" for r in rows)
    assert service.current_interval(db, user_id) is None


def test_patch_splits_when_edited_across_midnight(db, user_id):
    iv = service.start(db, user_id, "lying", None)
    service.patch_interval(
        db, user_id, iv.id, posture=None,
        started_at=datetime(2026, 6, 13, 23, 0), ended_at=datetime(2026, 6, 14, 1, 30),
        label=None, label_set=False,
    )
    rows = db.query(
        "SELECT entry_date, duration_seconds FROM sit_stand_sessions WHERE user_id = ? "
        "ORDER BY entry_date", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [3600, 5400]


def test_start_splits_previous_overnight_interval(db, user_id):
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    # A new posture at 2026-06-14 07:00 would call start(); simulate its close time by
    # stopping first (start() closes via the same _close_and_split path).
    service.stop_running(db, user_id, at=datetime(2026, 6, 14, 7, 0))
    new_iv = service.start(db, user_id, "sitting", None)
    rows = db.query("SELECT posture, ended_at FROM sit_stand_sessions WHERE user_id = ?", [user_id])
    postures = sorted(r["posture"] for r in rows)
    assert postures == ["lying", "lying", "sitting"]
    assert service.current_interval(db, user_id).id == new_iv.id


def test_posture_totals_clip_running_overnight_to_each_day(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.timer.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    assert service.posture_totals(db, user_id, date(2026, 6, 13))["lying"] == 7200
    assert service.posture_totals(db, user_id, date(2026, 6, 14))["lying"] == 25200


def test_day_returns_running_overnight_clipped_per_day(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.timer.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))

    today = service.day(db, user_id, date(2026, 6, 14))
    assert today.running is not None
    assert today.running.started_at == datetime(2026, 6, 14, 0, 0)  # clamped to midnight
    assert today.running.ended_at is None  # still running today
    assert today.totals.lying == 25200

    prev = service.day(db, user_id, date(2026, 6, 13))
    assert prev.running is None  # not the current day
    seg = next(i for i in prev.intervals if i.posture == "lying")
    assert seg.started_at == datetime(2026, 6, 13, 22, 0)
    assert seg.ended_at == datetime(2026, 6, 14, 0, 0)  # clamped to day end
    assert prev.totals.lying == 7200
