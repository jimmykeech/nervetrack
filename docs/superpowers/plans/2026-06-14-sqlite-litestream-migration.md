# SQLite + Litestream Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the backend's DuckDB datastore with SQLite, and add Litestream continuous replication to Tigris on Fly.io, with no change to app behaviour.

**Architecture:** A single backend container where Litestream supervises uvicorn and streams a WAL-mode SQLite DB (on the existing Fly volume) to a Tigris bucket, restoring on boot for host-loss recovery. `db.py` becomes a thread-local SQLite layer with type adapters/converters so the service layer is unchanged. Schema and a few queries are translated to SQLite dialect. Start-fresh cutover (no data migration).

**Tech Stack:** Python 3.12, FastAPI, stdlib `sqlite3` (WAL), Litestream, Tigris (S3), Fly.io.

**Spec:** `docs/superpowers/specs/2026-06-14-sqlite-litestream-migration-design.md`

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `backend/app/db.py` | Thread-local SQLite connections, type adapters/converters, migration runner | Rewrite |
| `backend/app/migrations/0001_initial.sql` | Schema in SQLite dialect | Rewrite |
| `backend/app/services/timer.py` | Interval duration math | Modify (epoch→julianday) |
| `backend/app/config.py` | `db_path` default | Modify |
| `backend/tests/conftest.py` | File-backed test DB | Modify |
| `backend/tests/test_db_types.py` | Type round-trip + concurrency tests | Create |
| `backend/tests/test_timer.py` | Duration math test | Modify (add test) |
| `backend/pyproject.toml` | Drop `duckdb` | Modify |
| `backend/Dockerfile` | Litestream binary + entrypoint | Modify |
| `backend/litestream.yml` | Litestream replica config | Create |
| `backend/entrypoint.sh` | restore-on-boot + replicate-with-exec | Create |
| `backend/fly.toml` | `db_path` env → `.db` | Modify |
| `docker-compose.yml` | Local: bypass Litestream, plain uvicorn | Modify |
| `.gitignore` | `*.db*` instead of `*.duckdb*` | Modify |
| `docs/DEPLOY-FLY.md` | Tigris/Litestream ops + restore | Modify |

---

## Phase 1 — SQLite engine + dialect (app runs on SQLite locally, suite green)

### Task 1: Rewrite `db.py` as a thread-local SQLite layer

**Files:**
- Modify: `backend/app/db.py` (full rewrite)
- Test: `backend/tests/test_db_types.py` (created in Task 5; this task is validated by the existing suite after Task 2–4)

- [ ] **Step 1: Replace `backend/app/db.py` with the SQLite implementation**

```python
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
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _register_types() -> None:
    # Write side: rich Python types -> canonical TEXT (UUIDs in dashed form).
    sqlite3.register_adapter(uuid.UUID, str)
    sqlite3.register_adapter(datetime, lambda d: d.isoformat())
    sqlite3.register_adapter(date, lambda d: d.isoformat())
    # Read side: driven by each column's declared type via PARSE_DECLTYPES.
    sqlite3.register_converter("UUID", lambda b: uuid.UUID(b.decode()))
    sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))
    sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
    sqlite3.register_converter("BOOLEAN", lambda b: b not in (b"0", b"false", b"FALSE"))


_register_types()


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class Database:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._all_conns: list[sqlite3.Connection] = []
        self._reg_lock = threading.Lock()
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
        with self._reg_lock:
            self._all_conns.append(conn)
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
                conn.executescript("ROLLBACK;")
                raise
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", [version])

    def close(self) -> None:
        with self._reg_lock:
            for conn in self._all_conns:
                conn.close()
            self._all_conns.clear()
        self._local = threading.local()


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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/db.py
git commit -m "feat(db): rewrite db.py as thread-local SQLite layer with type adapters/converters"
```

(The suite won't pass until the migration SQL is translated in Task 2; that's expected — these tasks land together.)

---

### Task 2: Translate the schema to SQLite dialect

**Files:**
- Modify: `backend/app/migrations/0001_initial.sql` (full rewrite)

- [ ] **Step 1: Replace `backend/app/migrations/0001_initial.sql`**

UUID defaults emit a canonical dashed UUID (so DB-generated ids match `str(uuid.UUID)` from the adapter); `now()` defaults become a matching `strftime`. Declared types are kept so the `db.py` converters fire.

```sql
-- Initial NerveTrack schema (Phase 1), SQLite dialect.
-- Timestamps are stored as naive UTC ISO-8601 text; dates as ISO-8601 text.
-- UUID columns store canonical dashed UUID text.

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    google_sub TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id),
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE daily_entries (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    status TEXT CHECK (status IN ('G', 'A', 'R')),
    strengthening_done BOOLEAN DEFAULT FALSE,
    session_intensity DECIMAL(3, 1),
    sharp_pain_episodes INTEGER DEFAULT 0,
    worst_pain DECIMAL(3, 1),
    tingling_level DECIMAL(3, 1),
    tingling_duration_minutes INTEGER,
    stretches_morning BOOLEAN DEFAULT FALSE,
    stretches_night BOOLEAN DEFAULT FALSE,
    sitting_breaks TEXT,
    sleep_quality DECIMAL(2, 1),
    iced BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    UNIQUE (user_id, entry_date)
);

CREATE TABLE pain_events (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    occurred_at TIMESTAMP NOT NULL,
    pain_level DECIMAL(3, 1),
    context TEXT
);

CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    UNIQUE (user_id, name)
);

CREATE TABLE strength_sessions (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    performed_at TIMESTAMP NOT NULL,
    intensity DECIMAL(3, 1),
    notes TEXT
);

CREATE TABLE exercise_logs (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    session_id UUID NOT NULL REFERENCES strength_sessions (id),
    exercise_id UUID NOT NULL REFERENCES exercises (id),
    sets INTEGER,
    reps INTEGER,
    hold_seconds INTEGER,
    weight_kg DECIMAL(4, 1),
    difficulty DECIMAL(3, 1),
    nerve_response TEXT,
    modification TEXT
);

CREATE TABLE sit_stand_sessions (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    posture TEXT NOT NULL CHECK (posture IN ('sitting', 'standing', 'lying', 'walking')),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER,
    label TEXT
);

CREATE TABLE weekly_summaries (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    week_start DATE NOT NULL,
    strengthening_sessions INTEGER,
    avg_pain_episodes_per_day DECIMAL(5, 2),
    avg_tingling_level DECIMAL(5, 2),
    worst_pain DECIMAL(3, 1),
    overall_status TEXT CHECK (overall_status IN ('G', 'A', 'R')),
    key_observations TEXT,
    trend_vs_last_week TEXT,
    UNIQUE (user_id, week_start)
);

CREATE TABLE app_settings (
    user_id UUID NOT NULL REFERENCES users (id),
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (user_id, key)
);
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/migrations/0001_initial.sql
git commit -m "feat(db): translate schema to SQLite dialect"
```

---

### Task 3: Convert timer duration math to SQLite (`julianday`)

**Files:**
- Modify: `backend/app/services/timer.py:18-20` and `:38-39`

- [ ] **Step 1: Replace the `_LIVE_SECONDS` expression** (lines 18-20)

```python
# Live duration for an interval: stored seconds once stopped, else elapsed-so-far.
# julianday() parses ISO-8601 text and treats naive timestamps as UTC, matching now_utc().
_LIVE_SECONDS = (
    "COALESCE(duration_seconds, "
    "CAST((julianday('now') - julianday(started_at)) * 86400 AS INTEGER))"
)
```

- [ ] **Step 2: Replace the `duration_seconds` assignment in `stop_running`** (the `SET` clause, lines 38-39)

```python
        UPDATE sit_stand_sessions
        SET ended_at = ?,
            duration_seconds = CAST((julianday(?) - julianday(started_at)) * 86400 AS INTEGER)
        WHERE user_id = ? AND ended_at IS NULL
        RETURNING *
```

(The `patch_interval` Python arithmetic `new_end - new_start` is unchanged — the `TIMESTAMP` converter returns `datetime` objects, so it keeps working.)

- [ ] **Step 3: Run the timer tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_timer.py -v`
Expected: PASS (existing timer tests now green on SQLite).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/timer.py
git commit -m "feat(timer): use SQLite julianday for interval duration math"
```

---

### Task 4: Switch the test DB to a file (thread-local needs a shared file, not `:memory:`)

**Files:**
- Modify: `backend/tests/conftest.py:30-37` (the `db` fixture)

- [ ] **Step 1: Replace the `db` fixture**

```python
@pytest.fixture()
def db(tmp_path) -> Database:
    # File-backed (not :memory:) so thread-local connections opened by TestClient
    # request threads all see the same database.
    database = Database(str(tmp_path / "test.db"))
    database.migrate()
    db_module._db = database
    yield database
    database.close()
    db_module._db = None
```

- [ ] **Step 2: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS — all existing tests (incl. `test_returning_user_logs_in_again`) green on SQLite.

- [ ] **Step 3: Run ruff**

Run: `cd backend && .venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: use a file-backed SQLite DB so thread-local connections share state"
```

---

### Task 5: Add type round-trip + concurrency tests

**Files:**
- Create: `backend/tests/test_db_types.py`

- [ ] **Step 1: Write the tests**

```python
"""SQLite layer: rich-type round-tripping and thread-local concurrency."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from uuid import UUID

from app.services.timeutil import now_utc


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
```

- [ ] **Step 2: Run the new tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_db_types.py -v`
Expected: PASS (5 tests).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_db_types.py
git commit -m "test(db): cover SQLite type round-tripping and thread-local concurrency"
```

---

### Task 6: Config, dependency, and gitignore cleanup

**Files:**
- Modify: `backend/app/config.py:14`
- Modify: `backend/pyproject.toml` (dependencies)
- Modify: `.gitignore`

- [ ] **Step 1: Update `config.py` db_path default** (line 14)

```python
    db_path: str = "/data/nervetrack.db"
```

- [ ] **Step 2: Remove the `duckdb` dependency in `backend/pyproject.toml`**

Delete this line from `dependencies`:

```
    "duckdb>=1.0",
```

- [ ] **Step 3: Update `.gitignore`** — replace the two DuckDB lines

```
*.db
*.db-wal
*.db-shm
```

(Remove `*.duckdb` and `*.duckdb.wal`.)

- [ ] **Step 4: Reinstall deps and run the suite to confirm DuckDB is fully gone**

Run: `cd backend && .venv/bin/pip install -e '.[dev]' && .venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: install succeeds, all tests PASS, ruff clean. (`grep -rn duckdb backend/app` should return nothing.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/pyproject.toml .gitignore
git commit -m "chore(db): point config at sqlite path, drop duckdb dependency"
```

---

## Phase 2 — Litestream + Tigris packaging

### Task 7: Litestream config + entrypoint + Dockerfile

**Files:**
- Create: `backend/litestream.yml`
- Create: `backend/entrypoint.sh`
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Create `backend/litestream.yml`**

```yaml
# Replicate the SQLite DB to the Tigris bucket. Credentials/endpoint/bucket come
# from env vars injected by `fly storage create` (AWS_* + BUCKET_NAME).
dbs:
  - path: /data/nervetrack.db
    replicas:
      - type: s3
        bucket: ${BUCKET_NAME}
        path: nervetrack
        endpoint: ${AWS_ENDPOINT_URL_S3}
        region: ${AWS_REGION}
        access-key-id: ${AWS_ACCESS_KEY_ID}
        secret-access-key: ${AWS_SECRET_ACCESS_KEY}
```

- [ ] **Step 2: Create `backend/entrypoint.sh`**

```sh
#!/bin/sh
set -e

# Rebuild the DB from Tigris if the volume has none (fresh/host-replaced machine).
litestream restore -if-db-not-exists -config /etc/litestream.yml /data/nervetrack.db

# Run the app under Litestream so the WAL streams to Tigris continuously.
exec litestream replicate -config /etc/litestream.yml \
  -exec "uvicorn app.main:app --host :: --port 8000"
```

- [ ] **Step 3: Replace the tail of `backend/Dockerfile`**

Replace from the `# DuckDB file lives on a mounted volume.` comment through the final `CMD` with:

```dockerfile
# Litestream binary (pinned). Verify the tag against the current release.
COPY --from=litestream/litestream:0.3.13 /usr/local/bin/litestream /usr/local/bin/litestream

COPY litestream.yml /etc/litestream.yml
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# SQLite file lives on a mounted volume.
ENV NERVETRACK_DB_PATH=/data/nervetrack.db
VOLUME ["/data"]

EXPOSE 8000

# Litestream supervises uvicorn (binds IPv6 :: for Fly 6PN; see git history).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

- [ ] **Step 4: Build the image locally to confirm it assembles**

Run: `cd backend && docker build -t nervetrack-backend:sqlite .`
Expected: build succeeds; `docker run --rm --entrypoint litestream nervetrack-backend:sqlite version` prints a version.

- [ ] **Step 4b: Verify the image's bundled SQLite supports `RETURNING` (≥ 3.35)**

Run:
```bash
docker run --rm --entrypoint python nervetrack-backend:sqlite -c \
  "import sqlite3; print(sqlite3.sqlite_version); assert sqlite3.sqlite_version_info >= (3, 35), 'RETURNING needs SQLite >= 3.35'"
```
Expected: prints a version ≥ 3.35 and exits 0. (If it fails, pin a newer base image or build SQLite — the code uses `RETURNING *`.)

- [ ] **Step 5: Commit**

```bash
git add backend/litestream.yml backend/entrypoint.sh backend/Dockerfile
git commit -m "feat(deploy): supervise uvicorn with Litestream, restore-on-boot from Tigris"
```

---

### Task 8: Update Fly + local-compose config for the SQLite path

**Files:**
- Modify: `backend/fly.toml` (the `NERVETRACK_DB_PATH` env line)
- Modify: `docker-compose.yml` (backend service)

- [ ] **Step 1: Update `backend/fly.toml`** `[env]`

```toml
  NERVETRACK_DB_PATH = "/data/nervetrack.db"
```

- [ ] **Step 2: Bypass Litestream locally in `docker-compose.yml`**

Add to the `backend` service so local dev runs plain uvicorn (no Litestream/Tigris) against a SQLite file on the volume:

```yaml
    entrypoint: ['uvicorn', 'app.main:app', '--host', '::', '--port', '8000']
```

And change the backend env line:

```yaml
      NERVETRACK_DB_PATH: /data/nervetrack.db
```

- [ ] **Step 3: Smoke-test the local stack**

Run: `docker compose up --build -d && sleep 5 && curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/healthz`
Expected: `200`. Then `docker compose down`.

- [ ] **Step 4: Commit**

```bash
git add backend/fly.toml docker-compose.yml
git commit -m "chore(deploy): sqlite db path for fly + plain-uvicorn local compose"
```

---

## Phase 3 — Cutover (ops)

### Task 9: Provision Tigris, deploy, verify replication + restore, document

These are operator steps (run by a human with `fly` access), not code. Execute in order and check each.

- [ ] **Step 1: Create the Tigris bucket** (injects `AWS_*` + `BUCKET_NAME` secrets into the backend app)

```bash
fly storage create --app nervetrack-backend
```

- [ ] **Step 2: Deploy the backend** (immediate strategy, single machine)

```bash
cd backend && fly deploy --remote-only
```

- [ ] **Step 3: Verify the app is healthy and reachable**

```bash
curl -i https://nervetrack.jameskeech.io/api/v1/auth/me   # expect HTTP 401
```

- [ ] **Step 4: Verify Litestream is replicating to Tigris**

```bash
fly ssh console --app nervetrack-backend \
  -C "litestream snapshots -config /etc/litestream.yml /data/nervetrack.db"
```
Expected: at least one snapshot listed (objects exist in the bucket).

- [ ] **Step 5: Prove a restore works** (restore the replica to a scratch path and open it)

```bash
fly ssh console --app nervetrack-backend -C "sh -c '\
  litestream restore -config /etc/litestream.yml -o /tmp/restore-check.db /data/nervetrack.db && \
  sqlite3 /tmp/restore-check.db \"SELECT count(*) FROM schema_migrations;\" && \
  rm -f /tmp/restore-check.db'"
```
Expected: prints `1` (the applied migration), confirming a restorable replica.

- [ ] **Step 6: Log in via the browser** to confirm end-to-end (seeds a fresh user in SQLite).

- [ ] **Step 7: Update `docs/DEPLOY-FLY.md`** — replace DuckDB references and the backup section with the Litestream model

Add a "Datastore: SQLite + Litestream" section covering: the bucket is created by `fly storage create`; the DB lives at `/data/nervetrack.db`; Litestream streams to Tigris continuously; recovery on host loss is automatic restore-on-boot (`entrypoint.sh`); and the manual restore command from Step 5. Remove the DuckDB snapshot-only "Backups" guidance.

- [ ] **Step 8: Delete the stale DuckDB file** from the volume (only after the SQLite version is confirmed healthy)

```bash
fly ssh console --app nervetrack-backend -C "rm -f /data/nervetrack.duckdb /data/nervetrack.duckdb.wal"
```

- [ ] **Step 9: Commit the docs**

```bash
git add docs/DEPLOY-FLY.md
git commit -m "docs(deploy): document SQLite + Litestream datastore and restore"
```

---

## Final verification

- [ ] `cd backend && .venv/bin/python -m pytest -q` — all green
- [ ] `cd backend && .venv/bin/ruff check .` — clean
- [ ] `grep -rn "duckdb" backend/app backend/tests` — no matches
- [ ] Production: login works; `litestream snapshots` shows replication; restore-check returns a valid DB
- [ ] Merge `sqlite-litestream-migration` → tag a release (e.g. `v0.2.0`) to deploy via CI
