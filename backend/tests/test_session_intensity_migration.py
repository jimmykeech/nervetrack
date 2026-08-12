"""Migration 0009: backfill onto single-session days, then a guarded recompute.

Builds a database with only the migrations before 0009 applied, seeds rows in
the pre-migration shape, then applies 0009 alone and inspects the result. This
mirrors the ``test_records_migration.py`` pattern but needs its own pre/post
staging since 0009 transforms existing data rather than adding new tables.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.db import MIGRATIONS_DIR, Database

_MIGRATION = "0009_session_intensity_derived"


def _migrate_up_to_but_excluding(db: Database, version: str) -> None:
    conn = db._conn
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, "
        "applied_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')));"
    )
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.stem >= version:
            continue
        conn.executescript("BEGIN;\n" + path.read_text() + "\nCOMMIT;")
        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", [path.stem])


def _apply(db: Database, version: str) -> None:
    conn = db._conn
    path = MIGRATIONS_DIR / f"{version}.sql"
    conn.executescript("BEGIN;\n" + path.read_text() + "\nCOMMIT;")
    conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", [version])


def _make_user(db: Database) -> UUID:
    row = db.query_one(
        "INSERT INTO users (google_sub, email, name) VALUES (?, ?, ?) RETURNING id",
        ["sub-migration", "migration@example.com", "Migration User"],
    )
    return row["id"]


def test_backfill_and_guarded_recompute(tmp_path):
    db = Database(str(tmp_path / "migration.db"))
    try:
        _migrate_up_to_but_excluding(db, _MIGRATION)
        user_id = _make_user(db)

        # Day A: the importer's shape — one session with no intensity of its own,
        # day-level value already stored. Backfill should copy it onto the session;
        # the subsequent recompute should then read it straight back (no change).
        day_a = db.query_one(
            "INSERT INTO daily_entries (user_id, entry_date, strengthening_done, "
            "session_intensity) VALUES (?, ?, TRUE, ?) RETURNING id",
            [user_id, date(2026, 1, 1), 7],
        )["id"]
        db.execute(
            "INSERT INTO strength_sessions (daily_entry_id, performed_at, intensity) "
            "VALUES (?, ?, NULL)",
            [day_a, datetime(2026, 1, 1, 12, 0)],
        )

        # Day B: orphan — a day-level value with zero sessions to attribute it to.
        # Neither statement may touch it; the value must survive untouched.
        day_b = db.query_one(
            "INSERT INTO daily_entries (user_id, entry_date, strengthening_done, "
            "session_intensity) VALUES (?, ?, TRUE, ?) RETURNING id",
            [user_id, date(2026, 1, 2), 5],
        )["id"]

        # Day C: two sessions (not the importer's one-session shape), one with a
        # real intensity already. The backfill guard (COUNT(*) = 1) must not fire
        # here; the recompute should just take MAX across the real values.
        day_c = db.query_one(
            "INSERT INTO daily_entries (user_id, entry_date, strengthening_done, "
            "session_intensity) VALUES (?, ?, TRUE, ?) RETURNING id",
            [user_id, date(2026, 1, 3), 3],
        )["id"]
        db.execute(
            "INSERT INTO strength_sessions (daily_entry_id, performed_at, intensity) "
            "VALUES (?, ?, ?)",
            [day_c, datetime(2026, 1, 3, 9, 0), 4],
        )
        db.execute(
            "INSERT INTO strength_sessions (daily_entry_id, performed_at, intensity) "
            "VALUES (?, ?, NULL)",
            [day_c, datetime(2026, 1, 3, 18, 0)],
        )

        _apply(db, _MIGRATION)

        session_a = db.query_one(
            "SELECT intensity FROM strength_sessions WHERE daily_entry_id = ?", [day_a]
        )
        assert session_a["intensity"] == 7  # backfilled from the day value

        entry_a = db.query_one(
            "SELECT session_intensity FROM daily_entries WHERE id = ?", [day_a]
        )
        assert entry_a["session_intensity"] == 7

        entry_b = db.query_one(
            "SELECT session_intensity FROM daily_entries WHERE id = ?", [day_b]
        )
        assert entry_b["session_intensity"] == 5  # orphan value preserved, not blanked

        entry_c = db.query_one(
            "SELECT session_intensity FROM daily_entries WHERE id = ?", [day_c]
        )
        assert entry_c["session_intensity"] == 4  # MAX(4, NULL); not backfilled

        sessions_c = db.query(
            "SELECT intensity FROM strength_sessions WHERE daily_entry_id = ? "
            "ORDER BY performed_at",
            [day_c],
        )
        assert [s["intensity"] for s in sessions_c] == [4, None]  # untouched
    finally:
        db.close()
