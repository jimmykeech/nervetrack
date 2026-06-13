"""DuckDB connection management and a tiny migration runner.

DuckDB is single-writer: only this process opens the file. All access goes
through one connection guarded by a re-entrant lock so the async FastAPI
workers never issue concurrent statements against it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._lock = threading.RLock()

    @contextmanager
    def cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield the shared connection under the write lock.

        DuckDB transactions are connection-scoped; serialising access keeps
        reads and writes consistent without a connection pool.
        """
        with self._lock:
            yield self._conn

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
        with self.cursor() as c:
            c.execute(sql, params or [])

    def query(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        with self.cursor() as c:
            cur = c.execute(sql, params or [])
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def query_one(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def migrate(self) -> None:
        """Apply ordered .sql migration files exactly once."""
        with self.cursor() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT now()
                )
                """
            )
            applied = {r[0] for r in c.execute("SELECT version FROM schema_migrations").fetchall()}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = path.stem
                if version in applied:
                    continue
                sql = path.read_text()
                c.execute("BEGIN TRANSACTION")
                try:
                    c.execute(sql)
                    c.execute("INSERT INTO schema_migrations (version) VALUES (?)", [version])
                    c.execute("COMMIT")
                except Exception:
                    c.execute("ROLLBACK")
                    raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_db: Database | None = None


def init_db(db_path: str) -> Database:
    global _db
    _db = Database(db_path)
    _db.migrate()
    return _db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _db
