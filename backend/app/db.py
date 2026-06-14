"""SQLite connection management (thread-local) and a tiny migration runner.

Each thread gets its own connection so SQLite's WAL mode serves concurrent
readers; the single-writer rule is handled by busy_timeout. Rich Python types
(UUID, datetime, date, bool) round-trip via registered adapters/converters so the
service layer sees the same types it saw under the previous engine.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _register_types() -> None:
    # Write side: rich Python types -> canonical TEXT (UUIDs in dashed form).
    sqlite3.register_adapter(uuid.UUID, str)
    sqlite3.register_adapter(datetime, lambda d: d.isoformat())
    sqlite3.register_adapter(date, lambda d: d.isoformat())
    # Decimal columns (e.g. DECIMAL(3,1)) stored as real; the converter restores
    # Decimal with one decimal place so round-trips preserve trailing zeroes.
    sqlite3.register_adapter(Decimal, float)
    sqlite3.register_converter("DECIMAL", lambda b: Decimal(b.decode()))
    # Read side: driven by each column's declared type via PARSE_DECLTYPES.
    sqlite3.register_converter("UUID", lambda b: uuid.UUID(b.decode()))
    sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))
    sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
    sqlite3.register_converter("BOOLEAN", lambda b: b != b"0")


_register_types()


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class Database:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Open the creating thread's connection eagerly so WAL mode (database-level,
        # persistent) is set before any reads/writes.
        self._local.conn = self._new_connection()

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,  # autocommit; explicit transactions via cursor()
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # idempotent; persists in the file
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.create_function("gen_random_uuid", 0, _gen_uuid)
        return conn

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._new_connection()
            self._local.conn = conn
        return conn

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Connection]:
        """Yield this thread's connection inside an explicit transaction.

        Autocommit is on, so multi-statement units that must be atomic wrap here.
        """
        conn = self._conn
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
        self._conn.execute(sql, params or [])

    def query(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        cur = self._conn.execute(sql, params or [])
        return [dict(row) for row in cur.fetchall()]

    def query_one(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def migrate(self) -> None:
        """Apply ordered .sql migration files exactly once."""
        conn = self._conn
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')));"
        )
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            try:
                conn.executescript("BEGIN;\n" + path.read_text() + "\nCOMMIT;")
            except Exception:
                # The in-script BEGIN leaves an open transaction on failure; roll it
                # back with execute() (NOT executescript, which would COMMIT first).
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", [version])

    def close(self) -> None:
        # Per-thread worker connections are intentionally process-lifetime and are
        # closed on process/thread exit.  WAL replication and checkpointing are
        # handled by Litestream (added in a later task), so an explicit app-side
        # checkpoint is intentionally absent here to avoid conflicting with it.
        # This method only closes the calling thread's connection.
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


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
