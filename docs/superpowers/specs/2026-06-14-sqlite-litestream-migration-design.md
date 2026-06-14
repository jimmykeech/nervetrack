# Design: Migrate backend datastore from DuckDB to SQLite + Litestream on Fly.io

**Date:** 2026-06-14
**Status:** Approved (design)

## Goal

Replace the backend's DuckDB datastore with **SQLite**, and add **Litestream**
continuous replication to **Tigris** (Fly's S3-compatible object storage), to make
the data resilient to Fly host/volume loss. DuckDB's resilience tooling on Fly is
weak (no Litestream support, single-copy host-pinned volume), it is OLAP-first for
what is really a transactional CRUD workload, and we have already hit one of its
OLTP limitations (the FK-update restriction that broke returning logins).

## Outcomes / success criteria

- App behaviour is unchanged for users; only the storage engine changes.
- The SQLite DB is continuously replicated off-host to Tigris (~seconds RPO).
- A host/volume loss is recoverable by redeploying to a new machine, which
  restores the DB from Tigris on boot (minutes RTO). No data conversion needed.
- Running cost stays ~$3–5/mo (volume within Fly's free 10GB; replica within
  Tigris's free 5GB; Litestream is free OSS).

## Decisions (from brainstorming)

- **Start fresh** — do NOT migrate existing DuckDB rows. Current production data is
  setup/test data; the new SQLite DB starts empty and re-seeds on first login.
- **Recovery model = manual/scripted restore**, not automatic failover. Litestream
  gives durability + point-in-time restore, not HA. Automatic zero-downtime
  failover (Postgres territory, ~$20–30/mo) is explicitly out of scope.
- **Keep the Fly volume.** SQLite lives on the existing `/data` volume (durable
  local copy) AND replicates to Tigris (off-host copy + PITR). Volumeless
  restore-on-boot was rejected: no cost saving (volume is free) and it makes
  restore-on-boot a single point of failure for normal restarts.
- **Single backend machine**, `immediate` deploy strategy — unchanged.
- **Thread-local SQLite connections** (not a single global connection + lock). Each
  worker thread gets its own connection so WAL's multi-reader concurrency is used;
  `busy_timeout` handles the rare writer contention. The idiomatic SQLite model, and
  cheap to land now since we're already rewriting `db.py`.

## Out of scope

- High availability / automatic failover; Postgres or any managed DB.
- Migrating existing DuckDB data.
- Frontend changes (none required).

## Architecture

### 1. Container & Litestream topology, boot/restore

The backend Dockerfile adds the Litestream binary (pinned version) and a
`litestream.yml`. The container entrypoint becomes:

```sh
# Rebuild the DB from Tigris if the volume has none (fresh / host-replaced machine).
litestream restore -if-db-not-exists -config /etc/litestream.yml /data/nervetrack.db
# Run the app under Litestream so the WAL streams to Tigris continuously.
exec litestream replicate -config /etc/litestream.yml \
  -exec "uvicorn app.main:app --host :: --port 8000"
```

- `litestream.yml` declares one DB (`/data/nervetrack.db`) with one S3 replica
  pointed at the Tigris bucket; credentials come from env (see Config).
- App `init_db()`/`migrate()` still runs on startup (after restore) to apply schema
  migrations to the restored-or-fresh DB.
- `/healthz` unchanged. Litestream `-exec` passes signals/exit through, so a uvicorn
  crash exits the container and Fly restarts it.
- Host-loss recovery is the `restore -if-db-not-exists` path, automated into boot.

### 2. SQLite driver & concurrency

Stdlib `sqlite3`, preserving `db.py`'s public interface
(`cursor/execute/query/query_one/migrate`) so the service layer and tests don't
change — only `db.py`'s internals do.

- **Thread-local connections:** each worker thread lazily opens its own
  `sqlite3.Connection` (via `threading.local()`). No global lock — WAL gives multiple
  concurrent readers, and SQLite's single-writer rule is handled by `busy_timeout`
  (writers wait rather than erroring with `SQLITE_BUSY`). Each connection is used by
  exactly one thread, so `check_same_thread` is not relaxed. FastAPI sync endpoints
  run in anyio's threadpool, so a bounded set of connections is created and reused.
- **PRAGMAs applied per connection** on open (they are connection-scoped, not
  database-scoped): `busy_timeout=5000`, `synchronous=NORMAL`, and
  **`foreign_keys=ON`** (SQLite enforces FKs per-connection; the schema depends on
  them). `journal_mode=WAL` is database-level (persists), set once at init.
- **Atomic multi-statement units** (the migration runner; any future "do N writes as
  one") use an explicit transaction on the calling thread's connection via the
  `cursor()` contextmanager. `migrate()` runs on the startup thread's connection.
- Type handling: register `sqlite3` adapters so `uuid.UUID` params serialise to TEXT
  and `datetime` to ISO strings; UUIDs/timestamps stored as TEXT, Pydantic parses
  them back. Dict `row_factory` as today.
- Litestream owns checkpointing; the app issues no manual `wal_checkpoint`.

### 3. SQLite dialect translation

Schema (`migrations/0001_initial.sql`) and a few service queries.

Schema:
- `UUID` → `TEXT`, `TIMESTAMP` → `TEXT`, `BOOLEAN` → `INTEGER` (`TRUE`/`FALSE`
  literals supported; `DEFAULT FALSE` works).
- `DEFAULT gen_random_uuid()` → `DEFAULT (lower(hex(randomblob(16))))`. SQLite can't
  call functions in a DDL default, but `randomblob` is allowed; 32 random hex chars
  parse cleanly as a UUID. Keeps existing INSERTs that rely on the default working.
- `DEFAULT now()` → a `strftime` default that matches `now_utc()`'s format:
  `DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))`. NOT `CURRENT_TIMESTAMP`, which
  emits a different format (`YYYY-MM-DD HH:MM:SS`, no `T`, no fractional seconds) and
  would break the single-format rule below.

Connection-registered function: register `gen_random_uuid()` as a Python function
returning a UUID string, so `seed.py`'s inline `gen_random_uuid()` in INSERTs (DML,
which SQLite allows) keeps working unchanged.

Query changes:
- `date_part('epoch', now() - started_at)` (timer durations, `timer.py`) →
  `CAST((julianday('now') - julianday(started_at)) * 86400 AS INTEGER)`. Highest-risk
  change; `julianday()` is format-sensitive.
- `RETURNING *` (`sessions.py`, `timer.py`) → supported in SQLite ≥ 3.35. **Risk to
  confirm early:** verify `sqlite3.sqlite_version` in `python:3.12-slim` is ≥ 3.35
  (expected ~3.40+); if not, pin a newer SQLite.
- `ON CONFLICT … DO UPDATE SET x = excluded.x` (`weekly.py`, `seed.py`) → already
  SQLite-compatible, no change.

Cross-cutting correctness risk — **timestamp format.** DuckDB returns `datetime`
objects; SQLite returns strings, and `julianday()`/comparisons need a *consistent*
format. The design standardises on **one canonical format everywhere: naive ISO-8601 UTC**
— exactly what `now_utc()` produces (`datetime.now(UTC).replace(tzinfo=None)` →
`'YYYY-MM-DDTHH:MM:SS.ffffff'`). A registered `sqlite3` adapter serialises `datetime`
params via `.isoformat()`, and the DB-side defaults use the matching `strftime`
expression above. `julianday()` accepts this format (naive = UTC), so the timer math
works. Focused tests around timer-duration math and timestamp round-tripping lock it
in.

### 4. Config & secrets (Tigris)

- `fly storage create` provisions a Tigris bucket and injects secrets into the
  backend app: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `BUCKET_NAME`,
  `AWS_ENDPOINT_URL_S3`, `AWS_REGION`. `litestream.yml` reads these via env; no
  credentials in the repo.
- `config.py`: `db_path` default `/data/nervetrack.db` (was `.duckdb`).
- `pyproject.toml`: drop `duckdb`; add nothing (stdlib `sqlite3`). Litestream is a
  baked-in binary, not a pip dep.
- `.gitignore`: add `*.db`, `*.db-wal`, `*.db-shm`; remove `*.duckdb` lines.
- `docker-compose.yml` (local dev): no Litestream — run plain uvicorn against a local
  SQLite file so dev stays simple and offline. Litestream only wraps the app in the
  Fly image.

### 5. Testing

- The existing 31 tests are the regression net (same `Database` interface). A green
  full suite on SQLite is the migration's correctness gate.
- **Test DB must be file-backed, not `:memory:`.** Thread-local connections to plain
  `:memory:` each get a *separate* database, so a TestClient request (handled on a
  threadpool thread) would see an empty DB the test fixture never populated. The `db`
  fixture therefore creates the SQLite DB at a `tmp_path` file (WAL works on a file);
  thread-local connections all open the same file and see the same data. (Shared-cache
  `file::memory:?cache=shared` is the alternative; tmp-file is simpler and chosen.)
- New focused tests for behaviour-sensitive changes: timer-duration math (the
  `julianday` arithmetic), timestamp round-tripping (write via `now_utc()`, read back,
  compare), and a concurrency smoke test that interleaved reads/writes across threads
  succeed under `busy_timeout` (validates the thread-local model).
- Litestream itself is validated operationally (Section 6), not unit-tested.
- CI backend job unchanged (`ruff` + `pytest`); deploy smoke test still asserts the
  live `401`.

### 6. Cutover & rollback

- Cutover (clean, start-fresh): `fly storage create` → set `db_path` → deploy backend
  (`immediate`). New SQLite DB starts empty; first login re-seeds. The old `.duckdb`
  file is left on the volume, ignored (deletable later).
- Verify after deploy: (1) login works + `/auth/me` returns 401 unauthenticated;
  (2) Litestream is replicating — `litestream snapshots` shows objects in the Tigris
  bucket; (3) prove a restore — restore the replica to a scratch path and confirm it
  opens. A backup you haven't restored isn't a backup.
- Rollback: low-risk (data is throwaway) — redeploy the previous (DuckDB) tag; its
  `.duckdb` file is still on the volume. Delete the old file only once the SQLite
  version is confirmed healthy.

## Key risks

1. **Timestamp format consistency** (Section 3) — mitigated by a single canonical
   ISO-8601 UTC format + targeted tests.
2. **SQLite version ≥ 3.35 for `RETURNING`** — confirm in the slim image early; pin
   newer SQLite if needed.
3. **Restore-on-boot correctness** — verified operationally by an actual restore test
   during cutover, not assumed.
4. **Thread-local connection model** — two consequences to handle: (a) writer
   contention surfaces as `SQLITE_BUSY`, mitigated by `busy_timeout` and covered by
   the concurrency test; (b) the test DB must be file-backed, since thread-local
   connections to `:memory:` would each get a separate database (Section 5).
