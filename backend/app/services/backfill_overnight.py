"""One-time backfill: split pre-existing overnight intervals into per-day rows.

SQLite migrations here are plain .sql and cannot compute tz/DST-correct local
midnights, so this runs in Python once, guarded by a schema_migrations sentinel.
"""

from __future__ import annotations

from app.db import Database
from app.services.interval_split import _local_date, day_segments
from app.services.timeutil import local_tz
from app.services.tingling import _recompute_daily_tingling

SENTINEL = "0009_backfill_overnight_split"


def _split_posture(db: Database, tz) -> None:
    rows = db.query("SELECT * FROM sit_stand_sessions WHERE ended_at IS NOT NULL")
    for r in rows:
        if _local_date(r["started_at"], tz) == _local_date(r["ended_at"], tz):
            continue
        segs = day_segments(r["started_at"], r["ended_at"], tz)
        first = segs[0]
        db.execute(
            "UPDATE sit_stand_sessions SET ended_at = ?, duration_seconds = ?, entry_date = ? "
            "WHERE id = ?",
            [first.ended_at, first.duration_seconds, first.entry_date, r["id"]],
        )
        for seg in segs[1:]:
            db.execute(
                "INSERT INTO sit_stand_sessions "
                "(user_id, entry_date, posture, started_at, ended_at, duration_seconds, label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [r["user_id"], seg.entry_date, r["posture"], seg.started_at, seg.ended_at,
                 seg.duration_seconds, r["label"]],
            )


def _split_tingling(db: Database, tz) -> set[tuple]:
    touched: set[tuple] = set()
    rows = db.query("SELECT * FROM tingling_sessions WHERE ended_at IS NOT NULL")
    for r in rows:
        if _local_date(r["started_at"], tz) == _local_date(r["ended_at"], tz):
            continue
        segs = day_segments(r["started_at"], r["ended_at"], tz)
        first = segs[0]
        db.execute(
            "UPDATE tingling_sessions SET ended_at = ?, duration_seconds = ?, entry_date = ? "
            "WHERE id = ?",
            [first.ended_at, first.duration_seconds, first.entry_date, r["id"]],
        )
        for seg in segs[1:]:
            db.execute(
                "INSERT INTO tingling_sessions "
                "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [r["user_id"], seg.entry_date, r["level"], seg.started_at, seg.ended_at,
                 seg.duration_seconds],
            )
        for seg in segs:
            touched.add((r["user_id"], seg.entry_date))
    return touched


def backfill_overnight(db: Database) -> None:
    """Split existing overnight rows once. Safe to call on every startup."""
    if db.query_one("SELECT version FROM schema_migrations WHERE version = ?", [SENTINEL]):
        return
    tz = local_tz()
    with db.cursor():
        _split_posture(db, tz)
        for user_id, entry_date in _split_tingling(db, tz):
            _recompute_daily_tingling(db, user_id, entry_date)
        db.execute("INSERT INTO schema_migrations (version) VALUES (?)", [SENTINEL])
