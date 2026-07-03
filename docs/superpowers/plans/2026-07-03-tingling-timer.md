# Tingling Timer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent tingling timer that records level-tagged tingling intervals, auto-populates the daily entry's `tingling_level` (max) and `tingling_duration_minutes` (sum), exposes tingling to the LLM, and makes the Today page's tingling fields read-only.

**Architecture:** A new `tingling_sessions` table + service/router mirror the existing sit/stand posture timer, but with a required `level` instead of `posture`. After every mutation the service recomputes the day's daily-entry tingling fields (max level, summed minutes). The frontend adds an independent `TinglingTimerStore` and a tingling section on the Timer page; the Today page shows the (now timer-owned) tingling fields read-only.

**Tech Stack:** FastAPI + Python (pytest, ruff), SQLite; SvelteKit (Svelte 5) + TypeScript (Vitest).

## Global Constraints

- Backend commands run from `backend/` (use `.venv/bin/pytest` and `.venv/bin/ruff` if not on PATH); frontend from `frontend/`.
- Mirror the posture timer patterns: `app/services/timer.py`, `app/routers/timer.py`, `app/models/timer.py`.
- Level range is **0–10**; a level is **required** to start a tingling interval (model `Field(ge=0, le=10)` with no default; DB `CHECK (level >= 0 AND level <= 10) NOT NULL`).
- One tingling interval runs at a time per user (mirrors posture).
- Timestamps stored UTC-naive via `now_utc()`/`to_utc_naive()`; `entry_date` via `local_date()` (from `app/services/timeutil.py`).
- Daily tingling fields are timer-owned: aggregation is `tingling_level = MAX(level)`, `tingling_duration_minutes = round(SUM(duration_seconds)/60)`; when a day has no intervals, both are cleared to NULL.
- This branch is off `main` (no posture-timer date-nav); the tingling section shows today. No past-day tingling editing, no tingling labels, no overlap detection (YAGNI).

---

### Task 1: Backend — `tingling_sessions` table + models

**Files:**
- Create: `backend/app/migrations/0008_tingling.sql`
- Create: `backend/app/models/tingling.py`
- Test: `backend/tests/test_tingling.py`

**Interfaces:**
- Produces: table `tingling_sessions(id, user_id, entry_date, level, started_at, ended_at, duration_seconds)`; models `TinglingStart{level: Decimal}`, `TinglingInterval{id, entry_date, level, started_at, ended_at, duration_seconds}`, `DayTingling{entry_date, intervals, running}`.

- [ ] **Step 1: Write the migration**

Create `backend/app/migrations/0008_tingling.sql`. Copy the `id` column's `DEFAULT (...)` UUID expression **verbatim** from the `sit_stand_sessions` table in `backend/app/migrations/0001_initial.sql`:

```sql
CREATE TABLE tingling_sessions (
    id UUID PRIMARY KEY DEFAULT (<copy the exact expression from sit_stand_sessions.id>),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    level NUMERIC NOT NULL CHECK (level >= 0 AND level <= 10),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER
);
```

- [ ] **Step 2: Write the models**

Create `backend/app/models/tingling.py`:

```python
"""Tingling timer schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TinglingStart(BaseModel):
    level: Decimal = Field(ge=0, le=10)


class TinglingInterval(BaseModel):
    id: UUID
    entry_date: date
    level: Decimal
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None


class DayTingling(BaseModel):
    entry_date: date
    intervals: list[TinglingInterval] = Field(default_factory=list)
    running: TinglingInterval | None = None
```

- [ ] **Step 3: Write failing tests**

Create `backend/tests/test_tingling.py`:

```python
"""Tingling timer table, models, service, and aggregation."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.tingling import TinglingStart


def test_tingling_table_exists(db, user_id):
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "tingling_sessions" in tables


def test_tingling_start_requires_level():
    with pytest.raises(ValidationError):
        TinglingStart()  # no level
    with pytest.raises(ValidationError):
        TinglingStart(level=11)  # out of range
```

- [ ] **Step 4: Run tests to verify**

Run from `backend/`:

```bash
.venv/bin/pytest tests/test_tingling.py -q
```

Expected: `test_tingling_table_exists` and both `TinglingStart` cases pass once the migration + model exist (RED first if you run before creating them). If they fail on import/missing table, finish steps 1–2, then green.

- [ ] **Step 5: Lint**

```bash
.venv/bin/ruff check app/models/tingling.py tests/test_tingling.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/0008_tingling.sql backend/app/models/tingling.py backend/tests/test_tingling.py
git commit -m "feat(tingling): add tingling_sessions table and models"
```

---

### Task 2: Backend — tingling service + daily aggregation

**Files:**
- Create: `backend/app/services/tingling.py`
- Test: `backend/tests/test_tingling.py` (extend)

**Interfaces:**
- Consumes: models from Task 1; `ensure_entry` from `app/services/entries.py`; `now_utc, to_utc_naive, local_date` from `app/services/timeutil.py`.
- Produces:
  - `current_interval(db, user_id) -> TinglingInterval | None`
  - `stop(db, user_id, at: datetime | None = None) -> TinglingInterval | None`
  - `start(db, user_id, level) -> TinglingInterval`
  - `day(db, user_id, entry_date) -> DayTingling`
  - `delete_interval(db, user_id, interval_id) -> bool`
  - `_recompute_daily_tingling(db, user_id, entry_date) -> None`

- [ ] **Step 1: Write failing tests (extend `test_tingling.py`)**

```python
def test_start_creates_running_interval_with_level(db, user_id):
    from app.services import tingling
    iv = tingling.start(db, user_id, 4)
    assert iv.ended_at is None
    assert iv.level == 4
    cur = tingling.current_interval(db, user_id)
    assert cur is not None and cur.id == iv.id


def test_second_start_closes_the_first(db, user_id):
    from app.services import tingling
    first = tingling.start(db, user_id, 3)
    tingling.start(db, user_id, 6)
    closed = db.query_one("SELECT * FROM tingling_sessions WHERE id = ?", [first.id])
    assert closed["ended_at"] is not None


def test_recompute_writes_max_level_and_summed_minutes(db, user_id):
    from app.services import tingling
    from app.services.entries import get_entry
    d = date(2026, 6, 20)
    # Two completed intervals: levels 3 and 7; 600s (10m) and 1200s (20m) => 30m, max 7.
    for level, secs in ((3, 600), (7, 1200)):
        db.execute(
            "INSERT INTO tingling_sessions "
            "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
            "VALUES (?, ?, ?, '2026-06-20T09:00:00', '2026-06-20T09:10:00', ?)",
            [user_id, d, level, secs],
        )
    tingling._recompute_daily_tingling(db, user_id, d)
    entry = get_entry(db, user_id, d)
    assert entry is not None
    assert int(entry.tingling_level) == 7
    assert entry.tingling_duration_minutes == 30


def test_delete_last_interval_clears_daily_fields(db, user_id):
    from app.services import tingling
    from app.services.entries import get_entry
    iv = tingling.start(db, user_id, 5)
    tingling.stop(db, user_id)
    tingling.delete_interval(db, user_id, iv.id)
    entry = get_entry(db, user_id, iv.entry_date)
    # entry may exist but tingling fields cleared
    if entry is not None:
        assert entry.tingling_level is None
        assert entry.tingling_duration_minutes is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest tests/test_tingling.py -q
```

Expected: FAIL (no `app.services.tingling`).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/tingling.py`:

```python
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
```

Note the `delete_interval` uses `DELETE ... RETURNING entry_date` — confirm the delete pattern in `app/services/timer.py::delete_interval` and match its style if it differs (both should be ownership-scoped by `user_id`).

- [ ] **Step 4: Run to verify green**

```bash
.venv/bin/pytest tests/test_tingling.py -q
```

Expected: all pass.

- [ ] **Step 5: Lint**

```bash
.venv/bin/ruff check app/services/tingling.py tests/test_tingling.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tingling.py backend/tests/test_tingling.py
git commit -m "feat(tingling): service + daily aggregation (max level, summed minutes)"
```

---

### Task 3: Backend — tingling router + registration

**Files:**
- Create: `backend/app/routers/tingling.py`
- Modify: `backend/app/main.py` (register router in both the import block and the include loop)
- Test: `backend/tests/test_tingling.py` (extend, using `auth_client`)

**Interfaces:**
- Consumes: `service` = `app/services/tingling.py` (Task 2); models (Task 1).
- Produces: endpoints `POST /tingling/start`, `POST /tingling/stop`, `GET /tingling/current`, `GET /tingling/day/{entry_date}`, `DELETE /tingling/intervals/{id}` (all under the `/api/v1` prefix).

- [ ] **Step 1: Write failing endpoint tests (extend `test_tingling.py`)**

```python
def test_tingling_endpoints_flow(auth_client):
    r = auth_client.post("/api/v1/tingling/start", json={"level": 4})
    assert r.status_code == 200
    assert r.json()["ended_at"] is None
    r = auth_client.post("/api/v1/tingling/stop")
    assert r.status_code == 200
    assert auth_client.get("/api/v1/tingling/current").json() is None


def test_tingling_start_rejects_missing_level(auth_client):
    r = auth_client.post("/api/v1/tingling/start", json={})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest tests/test_tingling.py -q
```

Expected: FAIL (404s — endpoints not registered).

- [ ] **Step 3: Write the router**

Create `backend/app/routers/tingling.py`:

```python
"""Tingling timer endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import current_user
from app.deps import db_dep
from app.models.tingling import DayTingling, TinglingInterval, TinglingStart
from app.services import tingling as service

router = APIRouter(tags=["tingling"])


@router.post("/tingling/start", response_model=TinglingInterval)
def start_tingling(data: TinglingStart, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.start(db, user_id, data.level)


@router.post("/tingling/stop", response_model=TinglingInterval | None)
def stop_tingling(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.stop(db, user_id)


@router.get("/tingling/current", response_model=TinglingInterval | None)
def current_tingling(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.current_interval(db, user_id)


@router.get("/tingling/day/{entry_date}", response_model=DayTingling)
def tingling_day(entry_date: date, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.day(db, user_id, entry_date)


@router.delete("/tingling/intervals/{interval_id}", status_code=204)
def delete_tingling_interval(
    interval_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not service.delete_interval(db, user_id, interval_id):
        raise HTTPException(404, "No such interval")
    return Response(status_code=204)
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Add `tingling` to the `from app.routers import (...)` import block (keep alphabetical-ish ordering consistent with the file), AND add `tingling` to the module tuple iterated by the `for module in (...)` include loop inside `create_app`.

- [ ] **Step 5: Run to verify green + full suite**

```bash
.venv/bin/pytest tests/test_tingling.py -q && .venv/bin/pytest -q
```

Expected: tingling tests pass; full backend suite green.

- [ ] **Step 6: Lint**

```bash
.venv/bin/ruff check app/routers/tingling.py app/main.py
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/tingling.py backend/app/main.py backend/tests/test_tingling.py
git commit -m "feat(tingling): endpoints + router registration"
```

---

### Task 4: Backend — LLM `get_tingling_totals` tool

**Files:**
- Modify: `backend/app/services/ai_tools.py`
- Test: the existing ai-tools test file (find it via `grep -rl get_posture_totals backend/tests`) — extend it.

**Interfaces:**
- Consumes: `tingling_sessions` table (Task 1).
- Produces: a `get_tingling_totals` tool (range params) returning per-day `{entry_date, max_level, minutes}`.

- [ ] **Step 1: Write a failing test**

In the ai-tools test file (the one that references `get_posture_totals`), add:

```python
def test_get_tingling_totals_registered_and_dispatches(db, user_id):
    from app.services import ai_tools
    names = {t["function"]["name"] for t in ai_tools.TOOLS}
    assert "get_tingling_totals" in names
    # dispatch returns a list (empty is fine) without error
    out = ai_tools.dispatch(db, user_id, "get_tingling_totals", {"from": "2026-06-01", "to": "2026-06-30"})
    assert isinstance(out, list)
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/pytest <that test file>::test_get_tingling_totals_registered_and_dispatches -q
```

Expected: FAIL (tool not registered).

- [ ] **Step 3: Implement**

In `backend/app/services/ai_tools.py`:

(a) Add to the `TOOLS` list (next to `get_posture_totals`):

```python
    {"type": "function", "function": {
        "name": "get_tingling_totals",
        "description": "Per-day tingling: highest level and total minutes over a date range.",
        "parameters": _RANGE,
    }},
```

(b) Add a dispatch branch in `dispatch` (next to the `get_posture_totals` branch):

```python
    if name == "get_tingling_totals":
        return _tingling_totals(db, user_id, _d(a["from"]), _d(a["to"]))
```

(c) Add the helper (next to `_posture_totals`):

```python
def _tingling_totals(db: Database, user_id: UUID, lo: date, hi: date) -> list[dict]:
    return db.query(
        """
        SELECT entry_date,
               MAX(level) AS max_level,
               CAST(SUM(duration_seconds) / 60 AS INTEGER) AS minutes
        FROM tingling_sessions
        WHERE user_id = ? AND entry_date >= ? AND entry_date <= ? AND ended_at IS NOT NULL
        GROUP BY entry_date
        ORDER BY entry_date
        """,
        [user_id, lo, hi],
    )
```

- [ ] **Step 4: Run to verify green**

```bash
.venv/bin/pytest <that test file> -q
```

Expected: pass.

- [ ] **Step 5: Lint**

```bash
.venv/bin/ruff check app/services/ai_tools.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ai_tools.py backend/tests/<that test file>
git commit -m "feat(tingling): expose get_tingling_totals to the LLM"
```

---

### Task 5: Frontend — types, api, `TinglingTimerStore`

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/stores/tingling.svelte.ts`

**Interfaces:**
- Consumes: the `/tingling/*` endpoints (Task 3).
- Produces:
  - types `TinglingInterval { id; entry_date; level; started_at; ended_at; duration_seconds }`, `DayTingling { entry_date; intervals; running }`.
  - api `startTingling(level)`, `stopTingling()`, `currentTingling()`, `tinglingDay(date)`, `deleteTinglingInterval(id)`.
  - `TinglingTimerStore` with `running`, `intervals`, `date`, `now`, `elapsed` getter, `startTicking()`, `stopTicking()`, `load(date?)`, `start(level)`, `stop()`, `remove(id)`.

- [ ] **Step 1: Add types**

Append to `frontend/src/lib/types.ts`:

```ts
export interface TinglingInterval {
  id: string;
  entry_date: string;
  level: number;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
}

export interface DayTingling {
  entry_date: string;
  intervals: TinglingInterval[];
  running: TinglingInterval | null;
}
```

- [ ] **Step 2: Add api methods**

In `frontend/src/lib/api.ts`, after the `deleteInterval` line (end of the Timer group), add (and add `TinglingInterval`, `DayTingling` to the `import type` from `$lib/types` at the top of the file):

```ts
  // Tingling timer
  startTingling: (level: number) =>
    request<TinglingInterval>('/tingling/start', {
      method: 'POST',
      body: JSON.stringify({ level })
    }),
  stopTingling: () => request<TinglingInterval | null>('/tingling/stop', { method: 'POST' }),
  currentTingling: () => request<TinglingInterval | null>('/tingling/current'),
  tinglingDay: (date: string) => request<DayTingling>(`/tingling/day/${date}`),
  deleteTinglingInterval: (id: string) =>
    request(`/tingling/intervals/${id}`, { method: 'DELETE' }),
```

- [ ] **Step 3: Create the store**

Create `frontend/src/lib/stores/tingling.svelte.ts` (mirrors `stores/timer.svelte.ts`, independent, no totals):

```ts
// Independent tingling timer store: the running interval lives on the backend;
// this restores it on load and keeps a live tick for the elapsed display.
import { api } from '$lib/api';
import { intervalSeconds } from '$lib/time';
import type { DayTingling, TinglingInterval } from '$lib/types';
import { todayISO } from '$lib/time';

export class TinglingTimerStore {
  running = $state<TinglingInterval | null>(null);
  intervals = $state<TinglingInterval[]>([]);
  date = $state<string>(todayISO());
  now = $state<number>(Date.now());

  private ticker: ReturnType<typeof setInterval> | null = null;

  get elapsed(): number {
    return this.running ? intervalSeconds(this.running, this.now) : 0;
  }

  startTicking() {
    if (this.ticker) return;
    this.ticker = setInterval(() => (this.now = Date.now()), 1000);
  }
  stopTicking() {
    if (this.ticker) clearInterval(this.ticker);
    this.ticker = null;
  }

  async load(date: string = todayISO()) {
    this.date = date;
    const day = await api.tinglingDay(date);
    this.intervals = day.intervals;
    this.running = await api.currentTingling();
    this.now = Date.now();
  }

  async start(level: number) {
    this.running = await api.startTingling(level);
    await this.refresh();
  }

  async stop() {
    await api.stopTingling();
    this.running = null;
    await this.refresh();
  }

  async remove(id: string) {
    await api.deleteTinglingInterval(id);
    await this.refresh();
    this.running = await api.currentTingling();
  }

  private async refresh() {
    const day = await api.tinglingDay(this.date);
    this.intervals = day.intervals;
    this.now = Date.now();
  }
}
```

Note: `intervalSeconds(interval, now)` is the existing helper used by `TimerStore`; confirm its signature in `frontend/src/lib/time.ts` and pass `this.running` and `this.now` the same way `TimerStore.elapsed` does.

- [ ] **Step 4: Verify**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0 (no runtime tests for the store; check/lint confirm types).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/lib/stores/tingling.svelte.ts
git commit -m "feat(tingling): frontend types, api, and TinglingTimerStore"
```

---

### Task 6: Frontend — tingling section on the Timer page

**Files:**
- Modify: `frontend/src/routes/timer/+page.svelte`

**Interfaces:**
- Consumes: `TinglingTimerStore` (Task 5); `formatDuration`, `formatMinutesish` (existing in `$lib/time`).
- Produces: nothing (leaf UI).

- [ ] **Step 1: Wire the store**

In `frontend/src/routes/timer/+page.svelte` `<script>`: import the store and helpers, instantiate it, load + tick on mount, and add a level state:

```ts
  import { TinglingTimerStore } from '$lib/stores/tingling.svelte';
```

Add near the existing `const store = new TimerStore();`:

```ts
  const tingle = new TinglingTimerStore();
  let tingleLevel = $state<number | null>(null);
```

In the existing `onMount(...)` add `tingle.load(); tingle.startTicking();`, and in `onDestroy(...)` add `tingle.stopTicking();`. Add handlers:

```ts
  async function startTingle() {
    if (tingleLevel === null) return;
    await tingle.start(tingleLevel);
  }
  async function stopTingle() {
    await tingle.stop();
  }
```

- [ ] **Step 2: Add the tingling section markup**

Add a new section after the posture `<div class="card totals">` block (and before or after the timeline card — place it after the totals card). Use the same `fmtTime` helper already in the file for times:

```svelte
<div class="card">
  <h3 style="margin-top: 0">Tingling timer</h3>
  <div class="card display" class:running={!!tingle.running} style="margin-bottom: 0.75rem">
    {#if tingle.running}
      <div class="posture">Tingling · level {tingle.running.level}</div>
      <div class="clock">{formatDuration(tingle.elapsed)}</div>
    {:else}
      <div class="posture muted">Not tracking</div>
      <div class="clock muted">00s</div>
    {/if}
  </div>
  <div class="row" style="align-items: flex-end; gap: 0.75rem">
    <div class="field" style="margin: 0; max-width: 10rem">
      <label>Tingling level (0–10)</label>
      <input type="number" min="0" max="10" step="0.5" bind:value={tingleLevel} />
    </div>
    <button class="btn-primary" onclick={startTingle} disabled={tingleLevel === null || !!tingle.running}
      >Start</button
    >
    <button onclick={stopTingle} disabled={!tingle.running}>Stop</button>
  </div>
  {#if tingle.intervals.length > 0}
    <div class="table-scroll" style="margin-top: 0.75rem">
      <table>
        <thead>
          <tr><th>Level</th><th>Start</th><th>End</th><th>Duration</th><th></th></tr>
        </thead>
        <tbody>
          {#each tingle.intervals as iv}
            <tr>
              <td>{iv.level}</td>
              <td>{fmtTime(iv.started_at)}</td>
              <td>{iv.ended_at ? fmtTime(iv.ended_at) : 'running'}</td>
              <td>{iv.duration_seconds != null ? formatMinutesish(iv.duration_seconds) : '—'}</td>
              <td
                ><button class="link danger" onclick={() => tingle.remove(iv.id)}>delete</button></td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
```

(`btn-primary`, `.table-scroll`, `.field`, `.display`, `.clock`, `.posture`, `.link` are existing global/component styles; the `.display`/`.clock`/`.posture` are already styled in this component.)

- [ ] **Step 3: Verify**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0.

- [ ] **Step 4: Manual check**

With backend + `npm run dev`: enter a level, confirm Start is disabled until a level is set; start → live counter runs; stop → interval appears in the tingling table; delete works; the posture timer is unaffected.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/timer/+page.svelte
git commit -m "feat(tingling): tingling timer section on the Timer page"
```

---

### Task 7: Frontend — Today page read-only tingling fields

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing (leaf UI).

- [ ] **Step 1: Make the fields timer-owned (read-only), pass-through on save**

In `frontend/src/routes/+page.svelte`:

- Replace the `tingling_text` state with `let tingling_duration_minutes = $state<number | null>(null);` and in the load function set `tingling_duration_minutes = entry?.tingling_duration_minutes ?? null;` (keep setting `tingling_level = entry?.tingling_level ?? null;`).
- In `save()`, change the payload line `tingling_duration_minutes: parseDurationToMinutes(tingling_text),` to `tingling_duration_minutes,` and keep `tingling_level,` (now a pass-through of the loaded, timer-computed values — Today no longer edits them, but echoing the loaded values back avoids clobbering).
- Remove the now-unused `parseDurationToMinutes` import (leave `formatMinutesLabel`, used below); `npm run lint`/`check` will confirm whether it's still referenced.

- [ ] **Step 2: Replace the two editable inputs with read-only display**

Remove the tingling-level `<Stepper .../>` block and the "Tingling duration" `<input .../>` block, and add a read-only display in their place:

```svelte
    <div>
      <label>Tingling (from the tingling timer)</label>
      <p class="muted" style="margin: 0.25rem 0 0">
        Level {tingling_level ?? '—'} · {formatMinutesLabel(tingling_duration_minutes)}
      </p>
    </div>
```

(`formatMinutesLabel(null)` already renders an empty/blank string per its existing behaviour — verify and keep the display sensible; if it returns '' show a dash: `{formatMinutesLabel(tingling_duration_minutes) || '—'}`.)

- [ ] **Step 3: Verify**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0 (fix any unused-import lint error surfaced by removing the tingling inputs).

- [ ] **Step 4: Manual check**

With backend + `npm run dev`: the Today page shows tingling level + duration read-only (no inputs); after running a tingling interval on the Timer page, reload Today and confirm the values reflect the timer (max level, summed minutes); editing other Today fields and saving does not wipe the tingling values.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(tingling): Today page shows tingling fields read-only (timer-owned)"
```

---

## Self-Review

**Spec coverage:**
- `tingling_sessions` table + models (spec §1–2) → Task 1.
- Service start/stop/current/day/delete + aggregation (spec §3) → Task 2.
- Router + registration (spec §4) → Task 3.
- LLM `get_tingling_totals` (spec §8) → Task 4.
- Frontend types/api/store (spec §5) → Task 5.
- Timer-page tingling section, required level enforced (spec §6) → Task 6.
- Today read-only tingling (spec §7) → Task 7.
- Testing (spec) → Tasks 1–4 backend tests; Tasks 5–7 verified via check/lint + manual.
- Non-goals respected: no past-day editing, no labels, no overlap detection, no backfill.

**Placeholder scan:** No TBD/TODO. Two deliberate "copy the exact expression / find the test file" instructions reference concrete existing code (the `sit_stand_sessions.id` DEFAULT, the ai-tools test file that already contains `get_posture_totals`); these are lookups, not undefined content.

**Type consistency:** Backend `start(db, user_id, level)`, `stop`, `current_interval`, `day`, `delete_interval`, `_recompute_daily_tingling` names match between Task 2 (produced) and Task 3 (consumed). Models `TinglingStart.level`, `TinglingInterval`, `DayTingling` consistent across Tasks 1/2/3. Frontend `startTingling(level)`/`stopTingling`/`currentTingling`/`tinglingDay`/`deleteTinglingInterval` match between Task 5 (api) and the store; `TinglingTimerStore` members (`running`, `intervals`, `elapsed`, `load`, `start`, `stop`, `remove`) match between Task 5 (produced) and Task 6 (consumed). `level: number` (frontend) ↔ `Decimal` (backend) serialize as JSON numbers.
