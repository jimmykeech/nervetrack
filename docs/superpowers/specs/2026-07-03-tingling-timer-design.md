# Tingling timer — design

**Date:** 2026-07-03
**Status:** Draft — awaiting review

## Problem

The app tracks tingling as two manually-entered daily fields (`tingling_level`,
`tingling_duration_minutes` on the daily entry). The user wants a **timer** for
tingling episodes — analogous to the existing sit/stand posture timer — that
records duration and level per episode, runs **independently** of the posture
timer, and **auto-populates** the daily tingling fields (summed duration,
highest level). The LLM should be able to review tingling alongside posture.

## Goal

Add an independent tingling timer that records level-tagged tingling intervals,
automatically maintains the day's `tingling_level` (max) and
`tingling_duration_minutes` (sum), exposes tingling to the LLM, and makes the
Today page's tingling fields read-only (timer-driven).

## Decisions (settled)

- Ships as its **own branch/PR** (`feat/tingling-timer`, off `main`), separate
  from the posture-interval-editing PR.
- Daily tingling fields are **fully timer-driven / read-only** on Today; the
  manual inputs are removed.
- The tingling timer is a **second section on the Timer page**, independent of
  the posture timer.
- Level range **0–10** in 0.5 steps (matches the existing `tingling_level`
  field); a level is **required** to start an interval.

## Design

### 1. Backend — `tingling_sessions` table (migration `0008_tingling.sql`)

Mirror `sit_stand_sessions`, with a required `level` instead of `posture` and
no label:

```sql
CREATE TABLE tingling_sessions (
    id UUID PRIMARY KEY DEFAULT (<same uuid default expr as sit_stand_sessions>),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    level NUMERIC NOT NULL CHECK (level >= 0 AND level <= 10),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER
);
```

### 2. Backend — models (`app/models/tingling.py`)

- `TinglingStart { level: Decimal (ge=0, le=10) }` — required (no default).
- `TinglingInterval { id, entry_date, level, started_at, ended_at, duration_seconds }`.
- `DayTingling { entry_date, intervals: list[TinglingInterval], running: TinglingInterval | None }`.

### 3. Backend — service (`app/services/tingling.py`)

Mirror `services/timer.py`:

- `start(db, user_id, level)` — closes any running tingling interval (single
  running interval at a time), inserts a new one at `now`, then recomputes the
  day. Rejects a null level (also enforced by the model + DB CHECK).
- `stop(db, user_id)` — closes the running interval, sets `duration_seconds`,
  recomputes the day.
- `current_interval(db, user_id)` — the running interval or None.
- `day(db, user_id, entry_date)` — intervals for the day + running.
- `delete_interval(db, user_id, id)` — delete (ownership-scoped), recompute the
  interval's day.
- `_recompute_daily_tingling(db, user_id, entry_date)` — the aggregation
  (below).

**Aggregation** (`_recompute_daily_tingling`), following the
`_recompute_pain_summary` pattern:

```
agg = SELECT MAX(level) AS lvl,
             ROUND(COALESCE(SUM(duration_seconds), 0) / 60.0) AS mins
      FROM tingling_sessions WHERE user_id = ? AND entry_date = ?
if no intervals for the day:
    set daily_entries.tingling_level = NULL, tingling_duration_minutes = NULL
else:
    ensure_entry(user_id, entry_date)
    set daily_entries.tingling_level = agg.lvl,
        tingling_duration_minutes = int(agg.mins), updated_at = now
```

Notes: the running interval's `level` counts toward the max immediately (level
is known at start); its duration counts only once the interval is stopped
(`duration_seconds` is null while running). Recompute runs after every mutation
for that interval's `entry_date`.

### 4. Backend — router (`app/routers/tingling.py`) + registration

Endpoints mirroring the timer router:

- `POST /tingling/start` (body `TinglingStart`) → `TinglingInterval`
- `POST /tingling/stop` → `TinglingInterval | null`
- `GET /tingling/current` → `TinglingInterval | null`
- `GET /tingling/day/{entry_date}` → `DayTingling`
- `DELETE /tingling/intervals/{id}` → 204 (404 if not found)

Register the router in the FastAPI app alongside the existing routers.

### 5. Frontend — tingling timer store + API

- `frontend/src/lib/types.ts`: `TinglingInterval`, `DayTingling`.
- `frontend/src/lib/api.ts`: `startTingling(level)`, `stopTingling()`,
  `currentTingling()`, `tinglingDay(date)`, `deleteTinglingInterval(id)`.
- `frontend/src/lib/stores/tingling.svelte.ts`: a `TinglingTimerStore`
  mirroring `TimerStore` (running, intervals, live tick for elapsed,
  `load`/`start(level)`/`stop`/`remove`). Independent of `TimerStore`.

### 6. Frontend — tingling section on the Timer page

Add a section below the posture timer in `frontend/src/routes/timer/+page.svelte`:

- Live display: current tingling level + elapsed, or "not tracking".
- A **required level selector** (number input or stepper, 0–10, step 0.5) and a
  **Start** button that is **disabled until a level is chosen** (this enforces
  the level). A **Stop** button while running.
- Today's tingling timeline: a small table (Level / Start / End / Duration /
  delete).

The section uses its own `TinglingTimerStore` and does not affect the posture
timer. (This branch is off `main`, which does not yet have the posture-timer
date navigation from the other PR; the tingling section shows today. Past-day
tingling viewing/editing is out of scope here.)

### 7. Frontend — Today page read-only tingling fields

In `frontend/src/routes/+page.svelte`:

- Remove the manual `tingling_level` input and the `tingling_duration` text
  input (and their save wiring in the upsert payload).
- Display `tingling_level` and `tingling_duration_minutes` from the loaded entry
  **read-only**, with a hint (e.g. "From the tingling timer"). Existing stored
  values still display until a day's timer recomputes them.

### 8. LLM — expose tingling (`app/services/ai_tools.py`)

Add a `get_tingling_totals` tool (per-day **max level** and **total minutes**
over a date range), mirroring `get_posture_totals`, registered in the `TOOLS`
list and handled in `dispatch`. `tingling_level` already flows into
`get_stats`; this adds duration and explicit tingling access so chat and weekly
reviews can consider both timers. No change to the weekly service is required
(it reads stats, which include `tingling_level`).

## Non-goals (YAGNI)

- No past-day tingling viewing/editing, no editing of tingling interval
  times/levels (the posture-interval editing feature can be extended to
  tingling later).
- No tingling labels.
- No overlap detection.
- No backfill/migration of existing manual tingling values (they remain until a
  day's timer recomputes them).

## Testing

- **Backend** (`backend/tests/test_tingling.py`): start creates a running
  interval with the given level; a second start closes the first
  (single-running); stop sets duration; **aggregation** writes
  `tingling_level = max` and `tingling_duration_minutes = round(sum/60)` to the
  daily entry; deleting the last interval clears both daily fields to null;
  a null/invalid level is rejected (model validation). Plus a migration test
  that the `tingling_sessions` table exists (mirroring existing migration
  tests if present).
- **Backend** (`backend/tests/` ai tools): `get_tingling_totals` appears in the
  schema and dispatches, alongside the existing tool tests.
- **Frontend**: unit-test any pure helper added for the store; the timer
  section + read-only Today verified manually.
- Gate: backend `pytest` + `ruff`; frontend `npm run check` / `lint` / `test`.
- Manual: start a tingling interval (Start disabled until a level is set), stop
  it, confirm the Today page shows the summed duration + max level read-only;
  run two intervals with different levels and confirm max + sum; delete all and
  confirm the daily fields clear; ask the chat about tingling and confirm it can
  read the data.
