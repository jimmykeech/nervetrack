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
from app.services.timeutil import local_date, now_utc, to_utc_naive

# Live duration for an interval: stored seconds once stopped, else elapsed-so-far.
# julianday() parses ISO-8601 text and treats naive timestamps as UTC, matching now_utc().
_LIVE_SECONDS = (
    "COALESCE(duration_seconds, "
    "CAST((julianday('now') - julianday(started_at)) * 86400 AS INTEGER))"
)


def current_interval(db: Database, user_id: UUID) -> Interval | None:
    row = db.query_one(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    return Interval(**row) if row else None


def stop_running(db: Database, user_id: UUID, at: datetime | None = None) -> Interval | None:
    """End the user's running interval (if any), computing its stored duration."""
    at = to_utc_naive(at) if at else now_utc()
    row = db.query_one(
        """
        UPDATE sit_stand_sessions
        SET ended_at = ?,
            duration_seconds = CAST((julianday(?) - julianday(started_at)) * 86400 AS INTEGER)
        WHERE user_id = ? AND ended_at IS NULL
        RETURNING *
        """,
        [at, at, user_id],
    )
    return Interval(**row) if row else None


def start(db: Database, user_id: UUID, posture: str, label: str | None) -> Interval:
    """Stop the user's running interval and start a new one immediately."""
    with db.cursor():
        now = now_utc()
        stop_running(db, user_id, now)
        row = db.query_one(
            """
            INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at, label)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *
            """,
            [user_id, local_date(now), posture, now, label],
        )
    assert row is not None
    return Interval(**row)


def day(db: Database, user_id: UUID, entry_date: date) -> DayTimer:
    rows = db.query(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND entry_date = ? ORDER BY started_at",
        [user_id, entry_date],
    )
    intervals = [Interval(**r) for r in rows]
    totals = posture_totals(db, user_id, entry_date)
    running = next((i for i in intervals if i.ended_at is None), None)
    from app.models.postures import PostureTotals

    return DayTimer(
        entry_date=entry_date,
        intervals=intervals,
        totals=PostureTotals(**totals),
        running=running,
    )


def posture_totals(db: Database, user_id: UUID, entry_date: date) -> dict[str, int]:
    rows = db.query(
        f"""
        SELECT posture, CAST(SUM({_LIVE_SECONDS}) AS INTEGER) AS secs
        FROM sit_stand_sessions
        WHERE user_id = ? AND entry_date = ?
        GROUP BY posture
        """,
        [user_id, entry_date],
    )
    totals = {"sitting": 0, "standing": 0, "lying": 0, "walking": 0}
    for r in rows:
        totals[r["posture"]] = int(r["secs"] or 0)
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
    new_date = local_date(new_start)
    duration = (
        int((new_end - new_start).total_seconds()) if new_end is not None else None
    )
    row = db.query_one(
        """
        UPDATE sit_stand_sessions
        SET posture = ?, started_at = ?, ended_at = ?, duration_seconds = ?,
            label = ?, entry_date = ?
        WHERE id = ? AND user_id = ?
        RETURNING *
        """,
        [new_posture, new_start, new_end, duration, new_label, new_date, interval_id, user_id],
    )
    return Interval(**row) if row else None


def delete_interval(db: Database, user_id: UUID, interval_id: UUID) -> bool:
    existing = db.query_one(
        "SELECT id FROM sit_stand_sessions WHERE id = ? AND user_id = ?",
        [interval_id, user_id],
    )
    if not existing:
        return False
    db.execute("DELETE FROM sit_stand_sessions WHERE id = ?", [interval_id])
    return True
