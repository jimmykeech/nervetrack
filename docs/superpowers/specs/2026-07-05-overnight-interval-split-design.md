# Overnight interval splitting (per-day attribution)

**Date:** 2026-07-05
**Status:** Approved design, ready for implementation planning
**Area:** `backend/app` (timer + tingling services, reads/writes, one backfill) and a small `frontend/` display clamp

## Problem

A timer interval (`sit_stand_sessions` row; `tingling_sessions` likewise) stores
`started_at`, `ended_at`, `duration_seconds`, and a single **`entry_date`** — the
*local* calendar date, computed once at start time. Every posture-data consumer
groups by that one column and sums the full `duration_seconds`:

- `timer.posture_totals` / `timer.day` — timer page totals + timeline bar
- `entries.py` — the Today page (`timer_totals`, `timer_intervals`)
- `stats.py` — daily stats / history (`GROUP BY entry_date`)
- `weekly.py` — weekly summary (`SUM … WHERE entry_date IN week`)
- `ai_tools._posture_totals` — AI chat (`GROUP BY entry_date`, `ended_at IS NOT NULL`)

So an overnight interval — e.g. lying down at 22:00 and rising at 07:00 — has its
**entire 9h attributed to the start day** everywhere, and nothing to the next day.
Two concrete failures:

1. **Completed overnight interval:** all 9h counts on day 1; day 2's bar, totals,
   Today page, stats, weekly, and AI all show 0h for the morning sleep.
2. **Running overnight interval (still asleep, not yet stopped):** the live-totals
   SQL attributes *all* elapsed time (including the after-midnight part) to the
   start day, and today's timeline bar shows nothing — while the combined display
   up top *does* show it running (it is fetched day-independently). Before Stop is
   pressed, today looks empty and yesterday looks like a 9h+ sleep.

## Goals

- A completed interval that spans local midnight is attributed per day: each day
  shows exactly its portion in the bar, totals, Today page, stats, weekly, and AI.
- A running interval that has crossed midnight is attributed per day *live*, before
  it is stopped.
- Existing overnight rows (including imported history) are corrected once.
- Apply to **both** the posture and tingling timers.

## Non-goals

- No linkage between the pieces of a split interval (they become independent rows —
  see Decisions). No `split_group_id`.
- No new pro-rating logic inside `stats.py`, `weekly.py`, or `ai_tools.py` — they are
  deliberately left unchanged (see "What does not change").
- No change to how a *new* interval is created (`start` stays single-day at creation).
- No timezone-migration handling for historical data whose stored dates predate a
  timezone change (out of scope; the configured `NERVETRACK_TIMEZONE` is treated as
  stable).

## Decisions (locked with the user)

- **Approach A:** physically split *completed* intervals into per-day rows on write;
  clip the single *running* interval per day at read time. (Alternatives B "pure
  read-time clipping in all 5 consumers" and C "auto-split at midnight on read" were
  rejected — B is invasive and fragile, C mutates on GET.)
- Apply to **posture and tingling**.
- **Backfill** existing overnight rows once.
- Split pieces are **independent rows** (no linkage).
- On today's interval table, a running interval that started on a prior day displays
  its **start clamped to 00:00**.

## Architecture

One pure helper is the single source of the midnight math; every other change is a
thin caller of it.

```
day_segments(started_at, end, tz) -> list[DaySegment]
    DaySegment(entry_date, started_at, ended_at, duration_seconds)
```

- **Writes** (`stop`, `patch`, both timers): run the finalized span through
  `day_segments`; if it yields more than one day, replace the single row with N
  per-day rows in one transaction (the first piece reuses the original row id; the
  rest are inserted).
- **Reads** (the running interval only): `timer.day` / `timer.posture_totals` (and the
  tingling equivalents, and `entries.py`) include the running interval's clipped
  contribution for the queried day. Because only one interval is ever running per
  user per timer, this is a single, bounded clip.
- **Backfill:** a one-time idempotent pass splits pre-existing overnight rows using
  the same helper.

The frontend `timelineBar.ts` already clamps a segment to the viewed day, so the bar
needs no change; only the interval *table* gets a small start-time clamp.

## Components

### 1. `day_segments` helper — `app/services/interval_split.py` (new)

Pure, dependency-free (except `zoneinfo`), unit-tested.

```
DaySegment = NamedTuple(entry_date: date, started_at: datetime,
                        ended_at: datetime, duration_seconds: int)

def local_midnight_utc(d: date, tz: ZoneInfo) -> datetime   # local 00:00 of d -> naive UTC
def day_segments(started_at: datetime, end: datetime, tz: ZoneInfo) -> list[DaySegment]
```

`day_segments` walks local days from `local_date(started_at)` to `local_date(end)`;
for each local day `D` it clips the span to `[local_midnight_utc(D),
local_midnight_utc(D+1))`, and emits a `DaySegment` when the clip is non-empty.
`started_at`/`end` are naive UTC; results are naive UTC. `duration_seconds` is the
integer second count of the clip.

Edge behavior: single-day span → one segment (identity); exact-midnight start/end →
zero-length boundary piece skipped; N-day spans → N segments; sub-second clips →
`duration_seconds` floors to int. Local midnight is unambiguous under DST in the
supported zones (transitions occur at 02:00–03:00, not 00:00).

### 2. Posture write path — `app/services/timer.py`

- **`stop_running`:** inside a transaction, fetch the running row; compute
  `segs = day_segments(started_at, at, tz)`. Update the original row to `segs[0]`
  (`ended_at`, `duration_seconds`, `entry_date`); insert one row per `segs[1:]`
  (same `user_id`, `posture`, `label`). Return the final piece (the one containing
  `at`). If `segs` has one element, this reduces to today's behavior.
- **`patch_interval`:** after computing `new_start`/`new_end` and validating
  `new_end > new_start`, compute `day_segments(new_start, new_end, tz)`. One segment →
  the existing single-row update. More than one → update the row to `segs[0]` and
  insert the rest (same `posture`/`label`). Return `segs[0]` (API contract stays a
  single `Interval`; the frontend refetches the day). A patch that *removes* an
  overnight span (edited back within one day) naturally yields one segment.

`start` is unchanged.

### 3. Posture read path — `app/services/timer.py`

- **`posture_totals(entry_date)`:** SQL sums only **completed** rows
  (`ended_at IS NOT NULL`) `WHERE entry_date = ?` grouped by posture — these are split,
  so already correct. Then, in Python, if a running interval exists and
  `day_segments(running.started_at, now, tz)` contains `entry_date`, add that segment's
  seconds to `totals[running.posture]`. (The running row is excluded from the SQL sum
  because its stored `entry_date` would otherwise mis-attribute all elapsed time to the
  start day.)
- **`day(entry_date)`:** completed rows `WHERE entry_date = ?`; then, if the running
  interval overlaps `entry_date`, append the raw running row and set `running`. Sort
  intervals by `started_at`. Totals come from `posture_totals`. The frontend clamp
  renders the running row correctly per day.

### 4. Tingling parity — `app/services/tingling.py`

- **`stop`:** tingling has only start/stop/delete (no patch endpoint), so only `stop`
  needs split handling. Split the finalized span via `day_segments` exactly as posture,
  then call `_recompute_daily_tingling` for **each** affected `entry_date` (not only
  one). `delete` already recomputes its row's `entry_date` and is unchanged.
- **`day(entry_date)`:** include the running interval when it overlaps `entry_date`,
  as posture does.
- The `daily_entries` tingling aggregate (level, minutes) is recomputed per day from
  the now-split rows, which makes it correct for both days. A *running* overnight
  tingling interval does not update the aggregate until stopped (it has no
  `duration_seconds` yet) — consistent with how running time is excluded elsewhere.

### 5. Today page reuse — `app/services/entries.py`

`entries.py` currently fetches intervals via its own SQL plus
`timer_service.posture_totals`. Point it at the running-aware `timer_service.day`
(or shared helpers) so `timer_totals` and `timer_intervals` inherit the same per-day
attribution — no separate clip logic in `entries.py`.

### 6. Backfill — one-time idempotent pass

SQLite migrations here are plain `.sql` and cannot compute tz/DST-correct local
midnights, so the backfill is **Python**, invoked once after `migrate()` at startup
and guarded by a sentinel `version` inserted into `schema_migrations`
(e.g. `0009_backfill_overnight_split`) so it runs exactly once per database.

For each **completed** row in `sit_stand_sessions` and `tingling_sessions` whose
`local_date(started_at) != local_date(ended_at)`: compute `day_segments(started_at,
ended_at, tz)`, update the row to the first segment, insert the rest. After splitting
tingling rows, recompute `_recompute_daily_tingling` for every touched `entry_date`.
Running rows (`ended_at IS NULL`) are left alone — they are handled live by the read
path. The whole pass runs in a transaction.

### 7. No frontend change (running interval returned as a per-day clamped virtual)

Refined during planning: rather than a frontend clamp, `day` (and the tingling
equivalent) return the running interval as a **per-day clamped virtual** `Interval` —
`started_at` clamped to the queried day's local midnight; for the current day
`ended_at`/`duration_seconds` stay `null` (still running), for an earlier day within
the span they are clamped to the day end. Because the frontend computes its bar,
table, and client-side `liveTotals` from those `started_at`/`ended_at` values, all
three become correct and the table start shows `00:00` — with **no frontend change**.
The `timelineBar.ts` clamp remains a harmless no-op. Editing still acts on the real
stored running row (uncommon from a non-start day; accepted).

## Data flow

`day_segments` is the only place midnight boundaries are computed. Writes call it to
materialize per-day rows; reads call it to clip the lone running interval; the backfill
calls it to fix history. Every downstream aggregate (`posture_totals`, `stats`,
`weekly`, `ai_tools`, tingling daily fields) then works off rows that each belong to a
single `entry_date`, which is the invariant they already assume.

## What does not change (and why it is correct anyway)

- **`stats.py`, `weekly.py`, `ai_tools._posture_totals`, `_tingling_totals`:** unchanged.
  They read finalized `duration_seconds` grouped by `entry_date`. Once completed
  intervals are split, each contributes to exactly the right day. They ignore
  in-progress (running) time today and continue to — matching the product's existing
  behavior that unfinished intervals have no counted duration.
- **`timelineBar.ts` clamp:** kept as a harmless no-op for split rows and the mechanism
  that renders the running interval per day.
- **Combined display / `currentTimer`:** unchanged; it is day-independent and already
  correct.

## Edge cases

- **N-day span** (forgot to stop for days): `day_segments` yields one full-day segment
  per intermediate local day.
- **Exact-midnight boundaries:** zero-length boundary pieces are skipped.
- **DST-transition day:** `local_midnight_utc` uses `zoneinfo`, so a 23h/25h local day is
  bounded correctly; midnight is unambiguous in the supported zones.
- **Patch re-split / un-split:** editing an interval across or back within midnight is
  handled by re-running `day_segments` on patch.
- **Deleting one piece:** leaves the others (independent rows) — accepted.
- **Running interval spanning a viewed middle day:** included as a full-day segment.
- **Idempotent backfill:** guarded by the `schema_migrations` sentinel; safe to redeploy.

## Testing

- **`interval_split` unit tests:** single-day identity, 2-day, N-day, exact-midnight
  start and end, sub-minute, DST-transition day (spring-forward and fall-back),
  `local_midnight_utc` correctness.
- **Posture service tests:** `stop` splits an overnight span into per-day rows with
  correct durations/entry_dates; `patch` splits and un-splits; `posture_totals` and
  `day` clip a running overnight interval onto both days; a same-day interval is
  unaffected.
- **Tingling service tests:** `stop` split + `_recompute_daily_tingling` for each day;
  running-overlap read.
- **Backfill test:** a seeded overnight row is split and is idempotent on re-run;
  tingling daily aggregates recomputed.
- **Frontend:** existing `timelineBar` tests stay green; add a small check that the
  table start-time clamp renders `00:00` for a prior-day running interval.
- Commands: `cd backend && .venv/bin/pytest` and `.venv/bin/ruff check .`;
  `cd frontend && npm run test && npm run check && npm run lint`.

## Files touched (anticipated)

- `backend/app/services/interval_split.py` — new pure helper.
- `backend/tests/test_interval_split.py` — unit tests (new); service coverage extends
  `backend/tests/test_timer.py` and `test_tingling.py`; `test_backfill_overnight.py` (new).
- `backend/app/services/timer.py` — split on stop/patch; running-aware day/totals.
- `backend/app/services/tingling.py` — split on stop; per-day recompute; running-aware day.
- `backend/app/services/entries.py` — reuse running-aware timer reads.
- `backend/app/db.py` (or `main.py` startup) — invoke the idempotent backfill once.
- `backend/app/services/backfill_overnight.py` — new one-time backfill routine.
- Backend tests for the above.
- No frontend files change — the running interval is returned as a per-day clamped
  virtual (see §7), which the existing frontend renders correctly.

No changes to `stats.py`, `weekly.py`, or `ai_tools.py`.
