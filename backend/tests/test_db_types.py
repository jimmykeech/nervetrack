"""SQLite layer: rich-type round-tripping and thread-local concurrency."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from app.services.timeutil import now_utc


def test_failed_migration_rolls_back(tmp_path):
    import app.db as db_module

    bad = tmp_path / "migrations"
    bad.mkdir()
    (bad / "0001_good.sql").write_text("CREATE TABLE good_tbl (id INTEGER);")
    # Second migration fails on its 2nd statement; the 1st must be rolled back.
    (bad / "0002_bad.sql").write_text(
        "CREATE TABLE will_rollback (id INTEGER);\nCREATE TABLE will_rollback (id INTEGER);"
    )
    orig = db_module.MIGRATIONS_DIR
    db_module.MIGRATIONS_DIR = bad
    try:
        database = db_module.Database(str(tmp_path / "m.db"))
        with pytest.raises(sqlite3.OperationalError):
            database.migrate()
        # The good table from 0001 applied; the partial 0002 fully rolled back.
        names = {r["name"] for r in database.query(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "good_tbl" in names
        assert "will_rollback" not in names
        assert database.query("SELECT version FROM schema_migrations") == [{"version": "0001_good"}]
        database.close()
    finally:
        db_module.MIGRATIONS_DIR = orig


def test_uuid_and_timestamp_round_trip(db):
    # users.id (UUID default) + created_at (TIMESTAMP default) come back as rich types.
    db.execute("INSERT INTO users (email) VALUES (?)", ["round@trip.test"])
    row = db.query_one("SELECT id, email, created_at FROM users WHERE email = ?", ["round@trip.test"])
    assert isinstance(row["id"], UUID)
    assert isinstance(row["created_at"], datetime)


def test_uuid_param_matches_foreign_key(db):
    # A UUID read back and used as an FK param must match the stored id (dashed form).
    db.execute("INSERT INTO users (email) VALUES (?)", ["fk@trip.test"])
    user_id = db.query_one("SELECT id FROM users WHERE email = ?", ["fk@trip.test"])["id"]
    assert isinstance(user_id, UUID)
    db.execute(
        "INSERT INTO exercises (user_id, name) VALUES (?, ?)", [user_id, "Test Exercise"]
    )
    got = db.query_one("SELECT user_id FROM exercises WHERE name = ?", ["Test Exercise"])
    assert got["user_id"] == user_id


def test_boolean_round_trip(db):
    db.execute("INSERT INTO users (email) VALUES (?)", ["bool@trip.test"])
    uid = db.query_one("SELECT id FROM users WHERE email = ?", ["bool@trip.test"])["id"]
    db.execute(
        "INSERT INTO daily_entries (user_id, entry_date, iced) VALUES (?, ?, ?)",
        [uid, "2026-06-14", True],
    )
    row = db.query_one("SELECT iced, strengthening_done FROM daily_entries WHERE user_id = ?", [uid])
    assert row["iced"] is True
    assert row["strengthening_done"] is False  # column default FALSE


def test_concurrent_writes_serialise_without_error(db):
    # Thread-local connections + busy_timeout: parallel writers must all succeed.
    db.execute("INSERT INTO users (email) VALUES (?)", ["conc@trip.test"])
    uid = db.query_one("SELECT id FROM users WHERE email = ?", ["conc@trip.test"])["id"]
    errors: list[Exception] = []

    def writer(n: int) -> None:
        try:
            db.execute(
                "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at) "
                "VALUES (?, ?, ?, ?)",
                [uid, "2026-06-14", "sitting", now_utc()],
            )
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    count = db.query_one(
        "SELECT COUNT(*) AS c FROM sit_stand_sessions WHERE user_id = ?", [uid]
    )["c"]
    assert count == 10


def test_stop_updates_duration_via_julianday(db):
    # The epoch->julianday change: a 90s interval must compute ~90 stored seconds.
    db.execute("INSERT INTO users (email) VALUES (?)", ["dur@trip.test"])
    uid = db.query_one("SELECT id FROM users WHERE email = ?", ["dur@trip.test"])["id"]
    started = now_utc() - timedelta(seconds=90)
    db.execute(
        "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at) "
        "VALUES (?, ?, ?, ?)",
        [uid, "2026-06-14", "sitting", started],
    )
    ended = started + timedelta(seconds=90)
    db.execute(
        "UPDATE sit_stand_sessions SET ended_at = ?, "
        "duration_seconds = CAST((julianday(?) - julianday(started_at)) * 86400 AS INTEGER) "
        "WHERE user_id = ? AND ended_at IS NULL",
        [ended, ended, uid],
    )
    row = db.query_one(
        "SELECT duration_seconds FROM sit_stand_sessions WHERE user_id = ?", [uid]
    )
    assert abs(row["duration_seconds"] - 90) <= 1
