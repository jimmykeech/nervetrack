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
from app.services.timeutil import local_date, now_utc, to_utc_naive


def current_interval(db: Database, user_id: UUID) -> TinglingInterval | None:
    row = db.query_one(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    return TinglingInterval(**row) if row else None


def stop(db: Database, user_id: UUID, at: datetime | None = None) -> TinglingInterval | None:
    at = to_utc_naive(at) if at else now_utc()
    row = db.query_one(
        """
        UPDATE tingling_sessions
        SET ended_at = ?,
            duration_seconds = CAST((julianday(?) - julianday(started_at)) * 86400 AS INTEGER)
        WHERE user_id = ? AND ended_at IS NULL
        RETURNING *
        """,
        [at, at, user_id],
    )
    if row is None:
        return None
    _recompute_daily_tingling(db, user_id, row["entry_date"])
    return TinglingInterval(**row)


def start(db: Database, user_id: UUID, level: Decimal) -> TinglingInterval:
    with db.cursor():
        now = now_utc()
        stop(db, user_id, now)
        row = db.query_one(
            """
            INSERT INTO tingling_sessions (user_id, entry_date, level, started_at)
            VALUES (?, ?, ?, ?)
            RETURNING *
            """,
            [user_id, local_date(now), level, now],
        )
        assert row is not None
        _recompute_daily_tingling(db, user_id, row["entry_date"])
    return TinglingInterval(**row)


def day(db: Database, user_id: UUID, entry_date: date) -> DayTingling:
    rows = db.query(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND entry_date = ? ORDER BY started_at",
        [user_id, entry_date],
    )
    intervals = [TinglingInterval(**r) for r in rows]
    running = next((i for i in intervals if i.ended_at is None), None)
    return DayTingling(entry_date=entry_date, intervals=intervals, running=running)


def delete_interval(db: Database, user_id: UUID, interval_id: UUID) -> bool:
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
    minutes = round((agg["secs"] or 0) / 60)
    db.execute(
        "UPDATE daily_entries SET tingling_level = ?, tingling_duration_minutes = ?, "
        "updated_at = ? WHERE id = ?",
        [agg["lvl"], minutes, now_utc(), entry_id],
    )
