"""Sit/stand timer logic, scoped per user.

A single interval may be running at a time per user (postures are mutually
exclusive). The running interval lives server-side so closing the tab does not
lose it.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.db import Database
from app.models.timer import DayTimer, Interval
from app.services.interval_split import DaySegment, day_segments
from app.services.timeutil import local_date, local_tz, now_utc, to_utc_naive


def _rewrite_as_segments(
    db: Database,
    user_id: UUID,
    interval_id: UUID,
    posture: str,
    label: str | None,
    segments: list[DaySegment],
) -> list[dict]:
    """Rewrite one row into per-day rows: the first reuses ``interval_id``, the rest
    are inserted. All resulting rows are completed (each within a single day)."""
    first = segments[0]
    rows = [
        db.query_one(
            "UPDATE sit_stand_sessions SET posture = ?, started_at = ?, ended_at = ?, "
            "duration_seconds = ?, label = ?, entry_date = ? WHERE id = ? AND user_id = ? "
            "RETURNING *",
            [posture, first.started_at, first.ended_at, first.duration_seconds, label,
             first.entry_date, interval_id, user_id],
        )
    ]
    for seg in segments[1:]:
        rows.append(
            db.query_one(
                "INSERT INTO sit_stand_sessions "
                "(user_id, entry_date, posture, started_at, ended_at, duration_seconds, label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
                [user_id, seg.entry_date, posture, seg.started_at, seg.ended_at,
                 seg.duration_seconds, label],
            )
        )
    return rows


def _close_and_split(db: Database, user_id: UUID, at: datetime) -> list[dict] | None:
    """Close the running interval at ``at``, splitting across local midnight. Bare
    (the caller owns the transaction). Returns the resulting rows, or None if nothing
    was running."""
    running = db.query_one(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    if running is None:
        return None
    segments = day_segments(running["started_at"], at, local_tz())
    return _rewrite_as_segments(
        db, user_id, running["id"], running["posture"], running["label"], segments
    )


def current_interval(db: Database, user_id: UUID) -> Interval | None:
    row = db.query_one(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    return Interval(**row) if row else None


def stop_running(db: Database, user_id: UUID, at: datetime | None = None) -> Interval | None:
    """End the user's running interval (if any), splitting it across midnight."""
    at = to_utc_naive(at) if at else now_utc()
    with db.cursor():
        rows = _close_and_split(db, user_id, at)
    return Interval(**rows[-1]) if rows else None


def start(db: Database, user_id: UUID, posture: str, label: str | None) -> Interval:
    """Stop the user's running interval (splitting it) and start a new one."""
    with db.cursor():
        now = now_utc()
        _close_and_split(db, user_id, now)
        row = db.query_one(
            "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at, label) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            [user_id, local_date(now), posture, now, label],
        )
    assert row is not None
    return Interval(**row)


def _running_segment(
    db: Database, user_id: UUID, entry_date: date
) -> tuple[Interval, DaySegment] | None:
    """The running interval and its segment for ``entry_date`` (or None)."""
    running = current_interval(db, user_id)
    if running is None:
        return None
    for seg in day_segments(running.started_at, now_utc(), local_tz()):
        if seg.entry_date == entry_date:
            return running, seg
    return None


def day(db: Database, user_id: UUID, entry_date: date) -> DayTimer:
    from app.models.postures import PostureTotals

    rows = db.query(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND entry_date = ? "
        "AND ended_at IS NOT NULL ORDER BY started_at",
        [user_id, entry_date],
    )
    intervals = [Interval(**r) for r in rows]
    running_field: Interval | None = None
    seg_pair = _running_segment(db, user_id, entry_date)
    if seg_pair is not None:
        interval, seg = seg_pair
        is_current_day = seg.entry_date == local_date(now_utc())
        virtual = Interval(
            id=interval.id,
            entry_date=entry_date,
            posture=interval.posture,
            started_at=seg.started_at,
            ended_at=None if is_current_day else seg.ended_at,
            duration_seconds=None if is_current_day else seg.duration_seconds,
            label=interval.label,
        )
        intervals.append(virtual)
        if is_current_day:
            running_field = virtual
    intervals.sort(key=lambda i: i.started_at)
    totals = posture_totals(db, user_id, entry_date)
    return DayTimer(
        entry_date=entry_date,
        intervals=intervals,
        totals=PostureTotals(**totals),
        running=running_field,
    )


def posture_totals(db: Database, user_id: UUID, entry_date: date) -> dict[str, int]:
    rows = db.query(
        """
        SELECT posture, CAST(SUM(duration_seconds) AS INTEGER) AS secs
        FROM sit_stand_sessions
        WHERE user_id = ? AND entry_date = ? AND ended_at IS NOT NULL
        GROUP BY posture
        """,
        [user_id, entry_date],
    )
    totals = {"sitting": 0, "standing": 0, "lying": 0, "walking": 0}
    for r in rows:
        totals[r["posture"]] = int(r["secs"] or 0)
    running = _running_segment(db, user_id, entry_date)
    if running is not None:
        interval, seg = running
        totals[interval.posture] += seg.duration_seconds
    return totals


def patch_interval(
    db: Database,
    user_id: UUID,
    interval_id: UUID,
    posture: str | None,
    started_at: datetime | None,
    ended_at: datetime | None,
    label: str | None,
    label_set: bool,
) -> Interval | None:
    existing = db.query_one(
        "SELECT * FROM sit_stand_sessions WHERE id = ? AND user_id = ?",
        [interval_id, user_id],
    )
    if not existing:
        return None
    new_posture = posture or existing["posture"]
    new_start = to_utc_naive(started_at) if started_at else existing["started_at"]
    new_end = to_utc_naive(ended_at) if ended_at else existing["ended_at"]
    if new_end is not None and new_end <= new_start:
        raise ValueError("End must be after start")
    new_label = label if label_set else existing["label"]
    with db.cursor():
        if new_end is None:
            row = db.query_one(
                "UPDATE sit_stand_sessions SET posture = ?, started_at = ?, ended_at = NULL, "
                "duration_seconds = NULL, label = ?, entry_date = ? WHERE id = ? AND user_id = ? "
                "RETURNING *",
                [new_posture, new_start, new_label, local_date(new_start), interval_id, user_id],
            )
            return Interval(**row) if row else None
        segments = day_segments(new_start, new_end, local_tz())
        rows = _rewrite_as_segments(db, user_id, interval_id, new_posture, new_label, segments)
    return Interval(**rows[0])


def delete_interval(db: Database, user_id: UUID, interval_id: UUID) -> bool:
    existing = db.query_one(
        "SELECT id FROM sit_stand_sessions WHERE id = ? AND user_id = ?",
        [interval_id, user_id],
    )
    if not existing:
        return False
    db.execute("DELETE FROM sit_stand_sessions WHERE id = ?", [interval_id])
    return True
