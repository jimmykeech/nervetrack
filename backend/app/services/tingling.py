"""Tingling timer logic, scoped per user. One interval runs at a time.

Mutations recompute the day's daily-entry tingling fields (max level, summed
minutes), which are timer-owned.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.db import Database
from app.models.tingling import DayTingling, TinglingInterval
from app.services.entries import ensure_entry
from app.services.interval_split import DaySegment, day_segments
from app.services.timeutil import local_date, local_tz, now_utc, to_utc_naive


def current_interval(db: Database, user_id: UUID) -> TinglingInterval | None:
    row = db.query_one(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    return TinglingInterval(**row) if row else None


def _rewrite_as_segments(
    db: Database, user_id: UUID, interval_id: UUID, level, segments: list[DaySegment]
) -> list[dict]:
    """Rewrite one row into per-day rows: the first reuses ``interval_id``, the rest
    are inserted. All resulting rows are completed (each within a single day)."""
    first = segments[0]
    rows = [
        db.query_one(
            "UPDATE tingling_sessions SET level = ?, started_at = ?, ended_at = ?, "
            "duration_seconds = ?, entry_date = ? WHERE id = ? AND user_id = ? RETURNING *",
            [level, first.started_at, first.ended_at, first.duration_seconds,
             first.entry_date, interval_id, user_id],
        )
    ]
    for seg in segments[1:]:
        rows.append(
            db.query_one(
                "INSERT INTO tingling_sessions "
                "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
                [user_id, seg.entry_date, level, seg.started_at, seg.ended_at,
                 seg.duration_seconds],
            )
        )
    return rows


def _close_and_split(db: Database, user_id: UUID, at: datetime) -> list[dict] | None:
    """Close the running interval at ``at``, splitting across local midnight. Bare
    (the caller owns the transaction). Returns the resulting rows, or None if nothing
    was running."""
    running = db.query_one(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    if running is None:
        return None
    segments = day_segments(running["started_at"], at, local_tz())
    return _rewrite_as_segments(db, user_id, running["id"], running["level"], segments)


def stop(db: Database, user_id: UUID, at: datetime | None = None) -> TinglingInterval | None:
    at = to_utc_naive(at) if at else now_utc()
    with db.cursor():
        rows = _close_and_split(db, user_id, at)
        if rows is None:
            return None
        for entry_date in {r["entry_date"] for r in rows}:
            _recompute_daily_tingling(db, user_id, entry_date)
    return TinglingInterval(**rows[-1])


def start(db: Database, user_id: UUID, level: Decimal) -> TinglingInterval:
    with db.cursor():
        now = now_utc()
        closed = _close_and_split(db, user_id, now)
        row = db.query_one(
            "INSERT INTO tingling_sessions (user_id, entry_date, level, started_at) "
            "VALUES (?, ?, ?, ?) RETURNING *",
            [user_id, local_date(now), level, now],
        )
        assert row is not None
        affected = {r["entry_date"] for r in (closed or [])} | {row["entry_date"]}
        for entry_date in affected:
            _recompute_daily_tingling(db, user_id, entry_date)
    return TinglingInterval(**row)


def _running_segment(
    db: Database, user_id: UUID, entry_date: date
) -> tuple[TinglingInterval, DaySegment] | None:
    """The running interval and its segment for ``entry_date`` (or None)."""
    running = current_interval(db, user_id)
    if running is None:
        return None
    for seg in day_segments(running.started_at, now_utc(), local_tz()):
        if seg.entry_date == entry_date:
            return running, seg
    return None


def day(db: Database, user_id: UUID, entry_date: date) -> DayTingling:
    rows = db.query(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND entry_date = ? "
        "AND ended_at IS NOT NULL ORDER BY started_at",
        [user_id, entry_date],
    )
    intervals = [TinglingInterval(**r) for r in rows]
    running_field: TinglingInterval | None = None
    seg_pair = _running_segment(db, user_id, entry_date)
    if seg_pair is not None:
        interval, seg = seg_pair
        is_current_day = seg.entry_date == local_date(now_utc())
        virtual = TinglingInterval(
            id=interval.id,
            entry_date=entry_date,
            level=interval.level,
            started_at=seg.started_at,
            ended_at=None if is_current_day else seg.ended_at,
            duration_seconds=None if is_current_day else seg.duration_seconds,
        )
        intervals.append(virtual)
        if is_current_day:
            running_field = virtual
    intervals.sort(key=lambda i: i.started_at)
    return DayTingling(entry_date=entry_date, intervals=intervals, running=running_field)


def delete_interval(db: Database, user_id: UUID, interval_id: UUID) -> bool:
    with db.cursor():
        row = db.query_one(
            "DELETE FROM tingling_sessions WHERE id = ? AND user_id = ? RETURNING entry_date",
            [interval_id, user_id],
        )
        if row is None:
            return False
        _recompute_daily_tingling(db, user_id, row["entry_date"])
    return True


def _recompute_daily_tingling(db: Database, user_id: UUID, entry_date: date) -> None:
    agg = db.query_one(
        "SELECT COUNT(*) AS n, MAX(level) AS lvl, SUM(duration_seconds) AS secs "
        "FROM tingling_sessions WHERE user_id = ? AND entry_date = ?",
        [user_id, entry_date],
    )
    assert agg is not None
    if agg["n"] == 0:
        db.execute(
            "UPDATE daily_entries SET tingling_level = NULL, tingling_duration_minutes = NULL, "
            "updated_at = ? WHERE user_id = ? AND entry_date = ?",
            [now_utc(), user_id, entry_date],
        )
        return
    entry_id = ensure_entry(db, user_id, entry_date)
    minutes = ((agg["secs"] or 0) + 30) // 60
    db.execute(
        "UPDATE daily_entries SET tingling_level = ?, tingling_duration_minutes = ?, "
        "updated_at = ? WHERE id = ?",
        [agg["lvl"], minutes, now_utc(), entry_id],
    )
