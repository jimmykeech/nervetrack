from __future__ import annotations

import sqlite3

import pytest


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
