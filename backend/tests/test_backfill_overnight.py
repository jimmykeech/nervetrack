from datetime import date, datetime

from app.services.backfill_overnight import SENTINEL, backfill_overnight


def test_backfill_splits_existing_overnight_posture_row(db, user_id):
    db.execute(
        "INSERT INTO sit_stand_sessions "
        "(user_id, entry_date, posture, started_at, ended_at, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, date(2026, 6, 13), "lying",
         datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 7, 0), 32400],
    )
    backfill_overnight(db)
    rows = db.query(
        "SELECT entry_date, duration_seconds FROM sit_stand_sessions WHERE user_id = ? "
        "ORDER BY entry_date", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [7200, 25200]


def test_backfill_splits_tingling_and_recomputes(db, user_id):
    db.execute(
        "INSERT INTO tingling_sessions "
        "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, date(2026, 6, 13), 5,
         datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 7, 0), 32400],
    )
    backfill_overnight(db)
    rows = db.query("SELECT entry_date FROM tingling_sessions WHERE user_id = ? ORDER BY entry_date",
                    [user_id])
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    agg = db.query_one(
        "SELECT tingling_duration_minutes FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, date(2026, 6, 14)],
    )
    assert agg["tingling_duration_minutes"] == 420


def test_backfill_is_idempotent(db, user_id):
    db.execute(
        "INSERT INTO sit_stand_sessions "
        "(user_id, entry_date, posture, started_at, ended_at, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, date(2026, 6, 13), "lying",
         datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 7, 0), 32400],
    )
    backfill_overnight(db)
    backfill_overnight(db)  # second run must be a no-op
    count = db.query_one("SELECT COUNT(*) AS n FROM sit_stand_sessions WHERE user_id = ?", [user_id])
    assert count["n"] == 2
    assert db.query_one("SELECT version FROM schema_migrations WHERE version = ?", [SENTINEL])


def test_backfill_leaves_same_day_rows_untouched(db, user_id):
    db.execute(
        "INSERT INTO sit_stand_sessions "
        "(user_id, entry_date, posture, started_at, ended_at, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, date(2026, 6, 13), "sitting",
         datetime(2026, 6, 13, 9, 0), datetime(2026, 6, 13, 10, 0), 3600],
    )
    backfill_overnight(db)
    count = db.query_one("SELECT COUNT(*) AS n FROM sit_stand_sessions WHERE user_id = ?", [user_id])
    assert count["n"] == 1
