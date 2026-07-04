# Overnight Interval Splitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute a timer interval that crosses local midnight to each day it covers — for completed intervals (physically split into per-day rows on write) and for a still-running interval (clipped per day at read time) — across posture and tingling, plus a one-time backfill of existing data.

**Architecture:** One pure helper `interval_split.day_segments()` computes per-local-day segments and is the single home for the midnight math. `stop`/`patch` rewrite a spanning interval into per-day rows; `day`/`posture_totals` include the lone running interval clipped to the queried day (returned as a per-day clamped virtual `Interval`, so the existing frontend needs no change); a guarded startup backfill splits historical rows. `stats.py`/`weekly.py`/`ai_tools.py` are untouched — they already group finalized `duration_seconds` by `entry_date`, which becomes correct once rows are split.

**Tech Stack:** Python 3.13, FastAPI, SQLite (raw SQL via `app.db.Database`), pytest, ruff. No frontend changes.

## Design refinement vs. spec

The spec described appending the *raw* running row in `day()` plus a small frontend table clamp. This plan instead returns a **per-day clamped virtual `Interval`** from `day()` (and the tingling equivalent): `started_at` clamped to the queried day's local midnight; for the current day `ended_at`/`duration_seconds` stay `null` (still running), for an earlier day within the span they are clamped to the day end. This makes the frontend's client-side `liveTotals`, the timeline bar, and the interval table all correct — and shows the table start as `00:00` — **with no frontend change**, satisfying the spec's intent server-side. `frontend/src/routes/timer/+page.svelte` is therefore NOT modified.

## Global Constraints

- All backend work is under `backend/`. No frontend changes in this plan.
- Timestamps are naive UTC in storage; local calendar dates are derived with the configured timezone via `app.services.timeutil` (`local_tz()`, `local_date()`, `now_utc()`, `to_utc_naive()`). Tests run under the default timezone **UTC** (no override in `conftest.py`); DST cases pass an explicit `ZoneInfo` to the pure helper.
- `day_segments(started_at, end, tz)` is the ONLY place midnight boundaries are computed; write-split, read-clip, and backfill all call it.
- A *new* interval (`start`) is unchanged — single-day at creation.
- Nested transactions are illegal (SQLite): a function that opens `with db.cursor()` must not call another that also opens one. Follow the existing pattern — a bare `_close_and_split` (no cursor) is called from inside `start`/`stop`'s cursor.
- Posture and tingling both get the behavior. `stats.py`, `weekly.py`, `ai_tools.py` are NOT modified.
- Split pieces are independent rows (no linkage / no `split_group_id`).
- Backfill is Python (SQLite SQL can't do tz/DST), invoked once from the app lifespan after `init_db`, guarded by a `schema_migrations` sentinel `0009_backfill_overnight_split`.
- Verification commands (run from `backend/`): `.venv/bin/pytest`, `.venv/bin/ruff check .`. Frontend must still pass (run from `frontend/`): `npm run test && npm run check && npm run lint` — no frontend files change, so this is a regression check only.

---

## File Structure

- **Create** `backend/app/services/interval_split.py` — `DaySegment`, `local_midnight_utc`, `day_segments`. Pure, tz-explicit, no DB.
- **Create** `backend/tests/test_interval_split.py` — unit tests for the helper.
- **Modify** `backend/app/services/timer.py` — write-split (`stop_running`, `start`, `patch_interval`) and read-clip (`day`, `posture_totals`); shared `_close_and_split`, `_rewrite_as_segments`, `_running_segment`.
- **Modify** `backend/tests/test_timer.py` — split + running-clip service tests.
- **Modify** `backend/app/services/tingling.py` — write-split on `stop`/`start`, per-day recompute, read-clip in `day`.
- **Modify** `backend/tests/test_tingling.py` — split + recompute + running-clip tests.
- **Modify** `backend/app/services/entries.py` — reuse running-aware `timer.day`.
- **Modify** `backend/tests/test_entries.py` — Today-page running-aware assertion.
- **Create** `backend/app/services/backfill_overnight.py` — one-time guarded backfill.
- **Create** `backend/tests/test_backfill_overnight.py` — backfill + idempotency tests.
- **Modify** `backend/app/main.py` — invoke backfill in lifespan.

---

## Task 1: Pure `interval_split` helper

**Files:**
- Create: `backend/app/services/interval_split.py`
- Test: `backend/tests/test_interval_split.py`

**Interfaces:**
- Consumes: stdlib only (`datetime`, `zoneinfo`).
- Produces:
  - `class DaySegment(NamedTuple): entry_date: date; started_at: datetime; ended_at: datetime; duration_seconds: int` (datetimes are naive UTC)
  - `local_midnight_utc(d: date, tz: ZoneInfo) -> datetime`
  - `day_segments(started_at: datetime, end: datetime, tz: ZoneInfo) -> list[DaySegment]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_interval_split.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.interval_split import DaySegment, day_segments, local_midnight_utc

UTC = ZoneInfo("UTC")
SYD = ZoneInfo("Australia/Sydney")


def test_local_midnight_utc_in_utc():
    assert local_midnight_utc(date(2026, 6, 13), UTC) == datetime(2026, 6, 13, 0, 0)


def test_local_midnight_utc_respects_dst_offsets():
    # Sydney midnight is UTC+10 (standard) on 4 Oct 2026 (before the 02:00 spring-forward)
    assert local_midnight_utc(date(2026, 10, 4), SYD) == datetime(2026, 10, 3, 14, 0)
    # and UTC+11 (daylight) on 5 Apr 2026 (before the 03:00 fall-back)
    assert local_midnight_utc(date(2026, 4, 5), SYD) == datetime(2026, 4, 4, 13, 0)


def test_single_day_span_is_identity():
    segs = day_segments(datetime(2026, 6, 13, 9, 0), datetime(2026, 6, 13, 10, 0), UTC)
    assert segs == [DaySegment(date(2026, 6, 13), datetime(2026, 6, 13, 9, 0),
                               datetime(2026, 6, 13, 10, 0), 3600)]


def test_overnight_span_splits_into_two_days():
    segs = day_segments(datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 7, 0), UTC)
    assert [s.entry_date for s in segs] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [s.duration_seconds for s in segs] == [7200, 25200]
    assert segs[0].ended_at == datetime(2026, 6, 14, 0, 0)
    assert segs[1].started_at == datetime(2026, 6, 14, 0, 0)


def test_multi_day_span_has_a_full_middle_day():
    segs = day_segments(datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 15, 3, 0), UTC)
    assert [s.entry_date for s in segs] == [date(2026, 6, 13), date(2026, 6, 14), date(2026, 6, 15)]
    assert [s.duration_seconds for s in segs] == [7200, 86400, 10800]


def test_exact_midnight_end_yields_one_segment():
    segs = day_segments(datetime(2026, 6, 13, 22, 0), datetime(2026, 6, 14, 0, 0), UTC)
    assert len(segs) == 1
    assert segs[0].entry_date == date(2026, 6, 13)


def test_empty_when_end_not_after_start():
    assert day_segments(datetime(2026, 6, 13, 10, 0), datetime(2026, 6, 13, 10, 0), UTC) == []


def test_split_at_local_midnight_under_dst():
    # 23:30–00:30 Sydney local across 3→4 Oct 2026; local midnight is 14:00 UTC that day.
    segs = day_segments(datetime(2026, 10, 3, 13, 30), datetime(2026, 10, 3, 14, 30), SYD)
    assert [s.entry_date for s in segs] == [date(2026, 10, 3), date(2026, 10, 4)]
    assert [s.duration_seconds for s in segs] == [1800, 1800]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_interval_split.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.interval_split'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/interval_split.py`:

```python
"""Split a UTC interval into per-local-day segments.

Timestamps are naive UTC (storage convention). Local calendar-day boundaries
are computed in the given timezone, so an interval crossing local midnight is
attributed to each day it covers. Pure and DB-free so the midnight math is
unit-testable in one place.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo


class DaySegment(NamedTuple):
    entry_date: date
    started_at: datetime  # naive UTC
    ended_at: datetime  # naive UTC
    duration_seconds: int


def local_midnight_utc(d: date, tz: ZoneInfo) -> datetime:
    """The naive-UTC instant of local 00:00 on ``d``."""
    return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC).replace(tzinfo=None)


def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.replace(tzinfo=UTC).astimezone(tz).date()


def day_segments(started_at: datetime, end: datetime, tz: ZoneInfo) -> list[DaySegment]:
    """Split ``[started_at, end)`` (naive UTC) into one segment per local day."""
    if end <= started_at:
        return []
    segments: list[DaySegment] = []
    d = _local_date(started_at, tz)
    last = _local_date(end, tz)
    while d <= last:
        day_start = local_midnight_utc(d, tz)
        day_end = local_midnight_utc(d + timedelta(days=1), tz)
        seg_start = max(started_at, day_start)
        seg_end = min(end, day_end)
        if seg_end > seg_start:
            segments.append(
                DaySegment(d, seg_start, seg_end, int((seg_end - seg_start).total_seconds()))
            )
        d += timedelta(days=1)
    return segments
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_interval_split.py -q`
Expected: PASS — 8 tests.

- [ ] **Step 5: Lint**

Run: `cd backend && .venv/bin/ruff check app/services/interval_split.py tests/test_interval_split.py`
Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/interval_split.py backend/tests/test_interval_split.py
git commit -m "feat(timer): pure day_segments helper for per-day interval splitting"
```

---

## Task 2: Posture write-path split (stop / start / patch)

**Files:**
- Modify: `backend/app/services/timer.py`
- Test: `backend/tests/test_timer.py`

**Interfaces:**
- Consumes: `day_segments`, `DaySegment` from `app.services.interval_split`; `local_tz`, `local_date`, `now_utc`, `to_utc_naive` from `app.services.timeutil`.
- Produces (used by Task 3): `_close_and_split(db, user_id, at) -> list[dict] | None`, `_rewrite_as_segments(db, user_id, interval_id, posture, label, segments) -> list[dict]`. `stop_running`, `start`, `patch_interval` keep their existing signatures.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_timer.py` (keep existing tests):

```python
from datetime import date  # add to existing imports


def _insert_running(db, user_id, posture, started_at, entry_date):
    return db.query_one(
        "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at) "
        "VALUES (?, ?, ?, ?) RETURNING *",
        [user_id, entry_date, posture, started_at],
    )


def test_stop_splits_overnight_interval_into_per_day_rows(db, user_id):
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    service.stop_running(db, user_id, at=datetime(2026, 6, 14, 7, 0))
    rows = db.query(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? ORDER BY started_at", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [7200, 25200]
    assert all(r["posture"] == "lying" for r in rows)
    assert service.current_interval(db, user_id) is None


def test_patch_splits_when_edited_across_midnight(db, user_id):
    iv = service.start(db, user_id, "lying", None)
    service.patch_interval(
        db, user_id, iv.id, posture=None,
        started_at=datetime(2026, 6, 13, 23, 0), ended_at=datetime(2026, 6, 14, 1, 30),
        label=None, label_set=False,
    )
    rows = db.query(
        "SELECT entry_date, duration_seconds FROM sit_stand_sessions WHERE user_id = ? "
        "ORDER BY entry_date", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [3600, 5400]


def test_start_splits_previous_overnight_interval(db, user_id):
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    # A new posture at 2026-06-14 07:00 would call start(); simulate its close time by
    # stopping first (start() closes via the same _close_and_split path).
    service.stop_running(db, user_id, at=datetime(2026, 6, 14, 7, 0))
    new_iv = service.start(db, user_id, "sitting", None)
    rows = db.query("SELECT posture, ended_at FROM sit_stand_sessions WHERE user_id = ?", [user_id])
    postures = sorted(r["posture"] for r in rows)
    assert postures == ["lying", "lying", "sitting"]
    assert service.current_interval(db, user_id).id == new_iv.id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_timer.py -q -k "split"`
Expected: FAIL — the overnight `stop`/`patch` still produce a single row (e.g. entry_dates `[date(2026, 6, 13)]`).

- [ ] **Step 3: Rewrite the write path in `timer.py`**

In `backend/app/services/timer.py`, update the imports and replace `stop_running`, `start`, and `patch_interval`. Add the imports:

```python
from app.services.interval_split import DaySegment, day_segments
from app.services.timeutil import local_date, local_tz, now_utc, to_utc_naive
```

Add these helpers (place them above `current_interval`):

```python
def _rewrite_as_segments(
    db: Database,
    user_id: UUID,
    interval_id: UUID,
    posture: str,
    label: str | None,
    segments: list[DaySegment],
) -> list[dict]:
    """Rewrite one row into per-day rows: the first reuses ``interval_id``, the rest
    are inserted. All resulting rows are completed (each within a single day)."""
    first = segments[0]
    rows = [
        db.query_one(
            "UPDATE sit_stand_sessions SET posture = ?, started_at = ?, ended_at = ?, "
            "duration_seconds = ?, label = ?, entry_date = ? WHERE id = ? AND user_id = ? "
            "RETURNING *",
            [posture, first.started_at, first.ended_at, first.duration_seconds, label,
             first.entry_date, interval_id, user_id],
        )
    ]
    for seg in segments[1:]:
        rows.append(
            db.query_one(
                "INSERT INTO sit_stand_sessions "
                "(user_id, entry_date, posture, started_at, ended_at, duration_seconds, label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
                [user_id, seg.entry_date, posture, seg.started_at, seg.ended_at,
                 seg.duration_seconds, label],
            )
        )
    return rows


def _close_and_split(db: Database, user_id: UUID, at: datetime) -> list[dict] | None:
    """Close the running interval at ``at``, splitting across local midnight. Bare
    (the caller owns the transaction). Returns the resulting rows, or None if nothing
    was running."""
    running = db.query_one(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    if running is None:
        return None
    segments = day_segments(running["started_at"], at, local_tz())
    return _rewrite_as_segments(db, user_id, running["id"], running["posture"], running["label"], segments)
```

Replace `stop_running`:

```python
def stop_running(db: Database, user_id: UUID, at: datetime | None = None) -> Interval | None:
    """End the user's running interval (if any), splitting it across midnight."""
    at = to_utc_naive(at) if at else now_utc()
    with db.cursor():
        rows = _close_and_split(db, user_id, at)
    return Interval(**rows[-1]) if rows else None
```

Replace `start` (use the bare close inside the existing cursor — no nesting):

```python
def start(db: Database, user_id: UUID, posture: str, label: str | None) -> Interval:
    """Stop the user's running interval (splitting it) and start a new one."""
    with db.cursor():
        now = now_utc()
        _close_and_split(db, user_id, now)
        row = db.query_one(
            "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at, label) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            [user_id, local_date(now), posture, now, label],
        )
    assert row is not None
    return Interval(**row)
```

Replace `patch_interval` (wrap in a transaction; split when the edited span crosses midnight):

```python
def patch_interval(
    db: Database,
    user_id: UUID,
    interval_id: UUID,
    posture: str | None,
    started_at: datetime | None,
    ended_at: datetime | None,
    label: str | None,
    label_set: bool,
) -> Interval | None:
    existing = db.query_one(
        "SELECT * FROM sit_stand_sessions WHERE id = ? AND user_id = ?",
        [interval_id, user_id],
    )
    if not existing:
        return None
    new_posture = posture or existing["posture"]
    new_start = to_utc_naive(started_at) if started_at else existing["started_at"]
    new_end = to_utc_naive(ended_at) if ended_at else existing["ended_at"]
    if new_end is not None and new_end <= new_start:
        raise ValueError("End must be after start")
    new_label = label if label_set else existing["label"]
    with db.cursor():
        if new_end is None:
            row = db.query_one(
                "UPDATE sit_stand_sessions SET posture = ?, started_at = ?, ended_at = NULL, "
                "duration_seconds = NULL, label = ?, entry_date = ? WHERE id = ? AND user_id = ? "
                "RETURNING *",
                [new_posture, new_start, new_label, local_date(new_start), interval_id, user_id],
            )
            return Interval(**row) if row else None
        segments = day_segments(new_start, new_end, local_tz())
        rows = _rewrite_as_segments(db, user_id, interval_id, new_posture, new_label, segments)
    return Interval(**rows[0])
```

Leave `current_interval`, `day`, `posture_totals`, `delete_interval`, and the `_LIVE_SECONDS` constant as they are for now (Task 3 revisits the reads). Remove the now-duplicate old `from app.services.timeutil import ...` line if one already exists — keep a single import line.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_timer.py -q`
Expected: PASS — new split tests plus all pre-existing timer tests (start/switch/stop/patch/delete) still green.

- [ ] **Step 5: Lint**

Run: `cd backend && .venv/bin/ruff check app/services/timer.py tests/test_timer.py`
Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/timer.py backend/tests/test_timer.py
git commit -m "feat(timer): split posture intervals across midnight on stop/start/patch"
```

---

## Task 3: Posture read-path running-clip (day / posture_totals)

**Files:**
- Modify: `backend/app/services/timer.py`
- Test: `backend/tests/test_timer.py`

**Interfaces:**
- Consumes: `_close_and_split`/`_rewrite_as_segments` unchanged; `current_interval`, `day_segments`, `now_utc`, `local_date`, `local_tz`.
- Produces: running-aware `day(db, user_id, entry_date) -> DayTimer` and `posture_totals(db, user_id, entry_date) -> dict[str, int]`; helper `_running_segment(db, user_id, entry_date) -> tuple[Interval, DaySegment] | None`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_timer.py`:

```python
def test_posture_totals_clip_running_overnight_to_each_day(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.timer.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    assert service.posture_totals(db, user_id, date(2026, 6, 13))["lying"] == 7200
    assert service.posture_totals(db, user_id, date(2026, 6, 14))["lying"] == 25200


def test_day_returns_running_overnight_clipped_per_day(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.timer.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    _insert_running(db, user_id, "lying", datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))

    today = service.day(db, user_id, date(2026, 6, 14))
    assert today.running is not None
    assert today.running.started_at == datetime(2026, 6, 14, 0, 0)  # clamped to midnight
    assert today.running.ended_at is None  # still running today
    assert today.totals.lying == 25200

    prev = service.day(db, user_id, date(2026, 6, 13))
    assert prev.running is None  # not the current day
    seg = next(i for i in prev.intervals if i.posture == "lying")
    assert seg.started_at == datetime(2026, 6, 13, 22, 0)
    assert seg.ended_at == datetime(2026, 6, 14, 0, 0)  # clamped to day end
    assert prev.totals.lying == 7200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_timer.py -q -k "running_overnight or clip"`
Expected: FAIL — today's totals show 0 (running row's `entry_date` is 2026-06-13) and `day` does not surface the running interval on 2026-06-14.

- [ ] **Step 3: Rewrite the reads in `timer.py`**

In `backend/app/services/timer.py`, delete the `_LIVE_SECONDS` constant (no longer used) and replace `day` and `posture_totals`. Add the helper first:

```python
def _running_segment(
    db: Database, user_id: UUID, entry_date: date
) -> tuple[Interval, DaySegment] | None:
    """The running interval and its segment for ``entry_date`` (or None)."""
    running = current_interval(db, user_id)
    if running is None:
        return None
    for seg in day_segments(running.started_at, now_utc(), local_tz()):
        if seg.entry_date == entry_date:
            return running, seg
    return None
```

Replace `posture_totals` (sum completed rows; add the running interval's clip):

```python
def posture_totals(db: Database, user_id: UUID, entry_date: date) -> dict[str, int]:
    rows = db.query(
        """
        SELECT posture, CAST(SUM(duration_seconds) AS INTEGER) AS secs
        FROM sit_stand_sessions
        WHERE user_id = ? AND entry_date = ? AND ended_at IS NOT NULL
        GROUP BY posture
        """,
        [user_id, entry_date],
    )
    totals = {"sitting": 0, "standing": 0, "lying": 0, "walking": 0}
    for r in rows:
        totals[r["posture"]] = int(r["secs"] or 0)
    running = _running_segment(db, user_id, entry_date)
    if running is not None:
        interval, seg = running
        totals[interval.posture] += seg.duration_seconds
    return totals
```

Replace `day` (completed rows for the day + the running interval as a per-day clamped virtual):

```python
def day(db: Database, user_id: UUID, entry_date: date) -> DayTimer:
    from app.models.postures import PostureTotals

    rows = db.query(
        "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND entry_date = ? "
        "AND ended_at IS NOT NULL ORDER BY started_at",
        [user_id, entry_date],
    )
    intervals = [Interval(**r) for r in rows]
    running_field: Interval | None = None
    seg_pair = _running_segment(db, user_id, entry_date)
    if seg_pair is not None:
        interval, seg = seg_pair
        is_current_day = seg.entry_date == local_date(now_utc())
        virtual = Interval(
            id=interval.id,
            entry_date=entry_date,
            posture=interval.posture,
            started_at=seg.started_at,
            ended_at=None if is_current_day else seg.ended_at,
            duration_seconds=None if is_current_day else seg.duration_seconds,
            label=interval.label,
        )
        intervals.append(virtual)
        if is_current_day:
            running_field = virtual
    intervals.sort(key=lambda i: i.started_at)
    totals = posture_totals(db, user_id, entry_date)
    return DayTimer(
        entry_date=entry_date,
        intervals=intervals,
        totals=PostureTotals(**totals),
        running=running_field,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_timer.py -q`
Expected: PASS — new running-clip tests plus all earlier timer tests (including `test_day_totals_aggregate_by_posture`, which uses a completed same-day interval).

- [ ] **Step 5: Lint**

Run: `cd backend && .venv/bin/ruff check app/services/timer.py tests/test_timer.py`
Expected: no issues (confirm the deleted `_LIVE_SECONDS` left no dangling reference).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/timer.py backend/tests/test_timer.py
git commit -m "feat(timer): clip running overnight interval per day in day/posture_totals"
```

---

## Task 4: Tingling parity (split + per-day recompute + running-clip)

**Files:**
- Modify: `backend/app/services/tingling.py`
- Test: `backend/tests/test_tingling.py`

**Interfaces:**
- Consumes: `day_segments`, `DaySegment` from `app.services.interval_split`; `local_tz`, `local_date`, `now_utc`, `to_utc_naive`; existing `_recompute_daily_tingling`, `ensure_entry`.
- Produces: running-aware `day`; split-on-`stop`/`start`; helpers `_rewrite_as_segments`, `_close_and_split`, `_running_segment` (tingling variants keyed on `level`).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_tingling.py` (follow the file's existing import style; it inserts rows directly and reads `daily_entries`). Add near the top if missing: `from datetime import date, datetime` and `from app.services import tingling as service` (reuse whatever alias the file already uses — inspect the file and match it):

```python
def _insert_running_tingling(db, user_id, level, started_at, entry_date):
    return db.query_one(
        "INSERT INTO tingling_sessions (user_id, entry_date, level, started_at) "
        "VALUES (?, ?, ?, ?) RETURNING *",
        [user_id, entry_date, level, started_at],
    )


def test_tingling_stop_splits_overnight_and_recomputes_each_day(db, user_id):
    _insert_running_tingling(db, user_id, 5, datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    service.stop(db, user_id, at=datetime(2026, 6, 14, 7, 0))
    rows = db.query(
        "SELECT entry_date, duration_seconds FROM tingling_sessions WHERE user_id = ? "
        "ORDER BY entry_date", [user_id]
    )
    assert [r["entry_date"] for r in rows] == [date(2026, 6, 13), date(2026, 6, 14)]
    assert [r["duration_seconds"] for r in rows] == [7200, 25200]
    d13 = db.query_one(
        "SELECT tingling_duration_minutes FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, date(2026, 6, 13)],
    )
    d14 = db.query_one(
        "SELECT tingling_duration_minutes FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, date(2026, 6, 14)],
    )
    assert d13["tingling_duration_minutes"] == 120  # 7200s
    assert d14["tingling_duration_minutes"] == 420  # 25200s


def test_tingling_day_clips_running_overnight(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.tingling.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    _insert_running_tingling(db, user_id, 5, datetime(2026, 6, 13, 22, 0), date(2026, 6, 13))
    today = service.day(db, user_id, date(2026, 6, 14))
    assert today.running is not None
    assert today.running.started_at == datetime(2026, 6, 14, 0, 0)
    assert today.running.ended_at is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_tingling.py -q -k "split or clips"`
Expected: FAIL — `stop` produces a single row on 2026-06-13; `day(2026-06-14)` has no running interval.

- [ ] **Step 3: Rewrite `tingling.py`**

In `backend/app/services/tingling.py`, add imports:

```python
from app.services.interval_split import DaySegment, day_segments
from app.services.timeutil import local_date, local_tz, now_utc, to_utc_naive
```

Add helpers (replace the existing `_close_running`):

```python
def _rewrite_as_segments(
    db: Database, user_id: UUID, interval_id: UUID, level, segments: list[DaySegment]
) -> list[dict]:
    first = segments[0]
    rows = [
        db.query_one(
            "UPDATE tingling_sessions SET level = ?, started_at = ?, ended_at = ?, "
            "duration_seconds = ?, entry_date = ? WHERE id = ? AND user_id = ? RETURNING *",
            [level, first.started_at, first.ended_at, first.duration_seconds,
             first.entry_date, interval_id, user_id],
        )
    ]
    for seg in segments[1:]:
        rows.append(
            db.query_one(
                "INSERT INTO tingling_sessions "
                "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
                [user_id, seg.entry_date, level, seg.started_at, seg.ended_at, seg.duration_seconds],
            )
        )
    return rows


def _close_and_split(db: Database, user_id: UUID, at: datetime) -> list[dict] | None:
    running = db.query_one(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        [user_id],
    )
    if running is None:
        return None
    segments = day_segments(running["started_at"], at, local_tz())
    return _rewrite_as_segments(db, user_id, running["id"], running["level"], segments)
```

Replace `stop` (recompute every affected day):

```python
def stop(db: Database, user_id: UUID, at: datetime | None = None) -> TinglingInterval | None:
    at = to_utc_naive(at) if at else now_utc()
    with db.cursor():
        rows = _close_and_split(db, user_id, at)
        if rows is None:
            return None
        for entry_date in {r["entry_date"] for r in rows}:
            _recompute_daily_tingling(db, user_id, entry_date)
    return TinglingInterval(**rows[-1])
```

Replace `start` (close+split the previous, recompute all affected days):

```python
def start(db: Database, user_id: UUID, level: Decimal) -> TinglingInterval:
    with db.cursor():
        now = now_utc()
        closed = _close_and_split(db, user_id, now)
        row = db.query_one(
            "INSERT INTO tingling_sessions (user_id, entry_date, level, started_at) "
            "VALUES (?, ?, ?, ?) RETURNING *",
            [user_id, local_date(now), level, now],
        )
        assert row is not None
        affected = {r["entry_date"] for r in (closed or [])} | {row["entry_date"]}
        for entry_date in affected:
            _recompute_daily_tingling(db, user_id, entry_date)
    return TinglingInterval(**row)
```

Add the running-clip helper and update `day`:

```python
def _running_segment(
    db: Database, user_id: UUID, entry_date: date
) -> tuple[TinglingInterval, DaySegment] | None:
    running = current_interval(db, user_id)
    if running is None:
        return None
    for seg in day_segments(running.started_at, now_utc(), local_tz()):
        if seg.entry_date == entry_date:
            return running, seg
    return None


def day(db: Database, user_id: UUID, entry_date: date) -> DayTingling:
    rows = db.query(
        "SELECT * FROM tingling_sessions WHERE user_id = ? AND entry_date = ? "
        "AND ended_at IS NOT NULL ORDER BY started_at",
        [user_id, entry_date],
    )
    intervals = [TinglingInterval(**r) for r in rows]
    running_field: TinglingInterval | None = None
    seg_pair = _running_segment(db, user_id, entry_date)
    if seg_pair is not None:
        interval, seg = seg_pair
        is_current_day = seg.entry_date == local_date(now_utc())
        virtual = TinglingInterval(
            id=interval.id,
            entry_date=entry_date,
            level=interval.level,
            started_at=seg.started_at,
            ended_at=None if is_current_day else seg.ended_at,
            duration_seconds=None if is_current_day else seg.duration_seconds,
        )
        intervals.append(virtual)
        if is_current_day:
            running_field = virtual
    intervals.sort(key=lambda i: i.started_at)
    return DayTingling(entry_date=entry_date, intervals=intervals, running=running_field)
```

Leave `delete_interval` and `_recompute_daily_tingling` unchanged. Confirm `TinglingInterval` fields match the constructor (`id`, `entry_date`, `level`, `started_at`, `ended_at`, `duration_seconds`) by checking `app/models/tingling.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_tingling.py -q`
Expected: PASS — new split/recompute/clip tests plus all pre-existing tingling tests.

- [ ] **Step 5: Lint**

Run: `cd backend && .venv/bin/ruff check app/services/tingling.py tests/test_tingling.py`
Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tingling.py backend/tests/test_tingling.py
git commit -m "feat(tingling): split overnight intervals, per-day recompute, running clip"
```

---

## Task 5: Today page reuses running-aware timer reads

**Files:**
- Modify: `backend/app/services/entries.py`
- Test: `backend/tests/test_entries.py`

**Interfaces:**
- Consumes: `timer_service.day(db, user_id, entry_date) -> DayTimer` (running-aware, from Task 3).
- Produces: `DailyEntry.timer_totals` and `.timer_intervals` reflect per-day attribution including a running overnight interval.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_entries.py` (match the file's fixtures/imports; it uses `db`, `user_id`, and `get_entry`/the entries service — inspect and match):

```python
from datetime import date, datetime  # ensure available


def test_today_entry_counts_running_overnight_interval(db, user_id, monkeypatch):
    monkeypatch.setattr("app.services.timer.now_utc", lambda: datetime(2026, 6, 14, 7, 0))
    db.execute(
        "INSERT INTO sit_stand_sessions (user_id, entry_date, posture, started_at) "
        "VALUES (?, ?, ?, ?)",
        [user_id, date(2026, 6, 13), "lying", datetime(2026, 6, 13, 22, 0)],
    )
    from app.services import entries as entries_service

    entry = entries_service.get_entry(db, user_id, date(2026, 6, 14))
    assert entry.timer_totals.lying == 25200
    assert any(i.started_at == datetime(2026, 6, 14, 0, 0) for i in entry.timer_intervals)
```

(If the entries service's read function is not named `get_entry`, use the actual name — check `backend/app/services/entries.py` and `backend/app/routers/daily_entries.py`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -q -k "running_overnight"`
Expected: FAIL — `timer_totals.lying` is 0 for 2026-06-14 and the interval list omits the running interval (current code queries `WHERE entry_date = ?` directly).

- [ ] **Step 3: Point entries at `timer_service.day`**

In `backend/app/services/entries.py`, replace the inline intervals query and `posture_totals` call (the block around lines 144–160) so both come from the running-aware `day`:

```python
    day_timer = timer_service.day(db, user_id, entry_date)
    session = sessions_service.get_session_for_entry(db, row["id"])
    return DailyEntry(
        **row,
        pain_events=events,
        notes=notes,
        session=session,
        timer_totals=day_timer.totals,
        timer_intervals=day_timer.intervals,
    )
```

Remove the now-unused local `intervals = [...]` block and the `totals = timer_service.posture_totals(...)` line. Then fix imports: if `Interval` and/or `PostureTotals` are no longer referenced anywhere else in `entries.py`, delete those imports (let `ruff` guide you).

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -q`
Expected: PASS — new test plus all existing entries tests.

- [ ] **Step 5: Lint**

Run: `cd backend && .venv/bin/ruff check app/services/entries.py tests/test_entries.py`
Expected: no issues (no unused imports).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/entries.py backend/tests/test_entries.py
git commit -m "feat(entries): Today page uses running-aware per-day timer reads"
```

---

## Task 6: One-time backfill of existing overnight rows

**Files:**
- Create: `backend/app/services/backfill_overnight.py`
- Create: `backend/tests/test_backfill_overnight.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `day_segments`, `_local_date` from `app.services.interval_split`; `local_tz`; `tingling._recompute_daily_tingling`.
- Produces: `backfill_overnight(db: Database) -> None` — idempotent, guarded by the `schema_migrations` sentinel `0009_backfill_overnight_split`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_backfill_overnight.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_backfill_overnight.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.backfill_overnight'`.

- [ ] **Step 3: Write the backfill**

Create `backend/app/services/backfill_overnight.py`:

```python
"""One-time backfill: split pre-existing overnight intervals into per-day rows.

SQLite migrations here are plain .sql and cannot compute tz/DST-correct local
midnights, so this runs in Python once, guarded by a schema_migrations sentinel.
"""

from __future__ import annotations

from app.db import Database
from app.services.interval_split import _local_date, day_segments
from app.services.timeutil import local_tz
from app.services.tingling import _recompute_daily_tingling

SENTINEL = "0009_backfill_overnight_split"


def _split_posture(db: Database, tz) -> None:
    rows = db.query("SELECT * FROM sit_stand_sessions WHERE ended_at IS NOT NULL")
    for r in rows:
        if _local_date(r["started_at"], tz) == _local_date(r["ended_at"], tz):
            continue
        segs = day_segments(r["started_at"], r["ended_at"], tz)
        first = segs[0]
        db.execute(
            "UPDATE sit_stand_sessions SET ended_at = ?, duration_seconds = ?, entry_date = ? "
            "WHERE id = ?",
            [first.ended_at, first.duration_seconds, first.entry_date, r["id"]],
        )
        for seg in segs[1:]:
            db.execute(
                "INSERT INTO sit_stand_sessions "
                "(user_id, entry_date, posture, started_at, ended_at, duration_seconds, label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [r["user_id"], seg.entry_date, r["posture"], seg.started_at, seg.ended_at,
                 seg.duration_seconds, r["label"]],
            )


def _split_tingling(db: Database, tz) -> set[tuple]:
    touched: set[tuple] = set()
    rows = db.query("SELECT * FROM tingling_sessions WHERE ended_at IS NOT NULL")
    for r in rows:
        if _local_date(r["started_at"], tz) == _local_date(r["ended_at"], tz):
            continue
        segs = day_segments(r["started_at"], r["ended_at"], tz)
        first = segs[0]
        db.execute(
            "UPDATE tingling_sessions SET ended_at = ?, duration_seconds = ?, entry_date = ? "
            "WHERE id = ?",
            [first.ended_at, first.duration_seconds, first.entry_date, r["id"]],
        )
        for seg in segs[1:]:
            db.execute(
                "INSERT INTO tingling_sessions "
                "(user_id, entry_date, level, started_at, ended_at, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [r["user_id"], seg.entry_date, r["level"], seg.started_at, seg.ended_at,
                 seg.duration_seconds],
            )
        for seg in segs:
            touched.add((r["user_id"], seg.entry_date))
    return touched


def backfill_overnight(db: Database) -> None:
    """Split existing overnight rows once. Safe to call on every startup."""
    if db.query_one("SELECT version FROM schema_migrations WHERE version = ?", [SENTINEL]):
        return
    tz = local_tz()
    with db.cursor():
        _split_posture(db, tz)
        for user_id, entry_date in _split_tingling(db, tz):
            _recompute_daily_tingling(db, user_id, entry_date)
        db.execute("INSERT INTO schema_migrations (version) VALUES (?)", [SENTINEL])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_backfill_overnight.py -q`
Expected: PASS — 4 tests.

- [ ] **Step 5: Wire it into startup**

In `backend/app/main.py`, update the lifespan to run the backfill after `init_db`:

```python
from app.services.backfill_overnight import backfill_overnight  # add near the other imports


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = init_db(settings.db_path)
    backfill_overnight(db)
    yield
```

- [ ] **Step 6: Run the whole backend suite + lint**

Run: `cd backend && .venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: entire suite green (all prior tests + the new ones); ruff clean.

- [ ] **Step 7: Regression-check the frontend (no files changed)**

Run: `cd frontend && npm run test && npm run check && npm run lint`
Expected: all green — confirms the backend-only change didn't break the client (types/contract unchanged: `DayTimer`/`Interval` shapes are identical).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/backfill_overnight.py backend/tests/test_backfill_overnight.py backend/app/main.py
git commit -m "feat(timer): one-time backfill splitting existing overnight intervals"
```

---

## Self-Review

**Spec coverage:**
- Completed overnight interval attributed per day → Task 2 (write-split) + Task 6 (backfill). ✓
- Running overnight interval attributed per day live → Task 3 (posture) + Task 4 (tingling). ✓
- Apply to posture and tingling → Tasks 2/3 (posture), Task 4 (tingling). ✓
- Backfill existing data → Task 6. ✓
- Independent rows (no linkage) → `_rewrite_as_segments` inserts plain rows; no group id. ✓
- Today's table shows 00:00 for a prior-day running interval → satisfied server-side by the clamped virtual in Task 3/4 (see "Design refinement"); no frontend change. ✓
- `stats.py`/`weekly.py`/`ai_tools.py` unchanged and correct → untouched; they read finalized `duration_seconds` grouped by `entry_date`, correct once rows are split. ✓
- N-day, exact-midnight, DST, patch re-split edge cases → covered by Task 1 tests and Task 2 patch test. ✓
- Nested-transaction safety → `_close_and_split` is bare; `start` calls it inside its own cursor (Global Constraints + Tasks 2/4). ✓

**Placeholder scan:** No TBD/TODO; every code step contains complete code; each has an exact command and expected result. Task 4/5 note "match the file's existing imports/fixtures" and name the concrete symbols to verify (`TinglingInterval` fields, entries read-function name) — these are verification directions, not missing code.

**Type/name consistency:** `day_segments`/`DaySegment`/`local_midnight_utc`/`_local_date` (Task 1) are used verbatim in Tasks 2–6. `_close_and_split`/`_rewrite_as_segments`/`_running_segment` are defined per-service (posture in Task 2/3, tingling in Task 4) with matching signatures. The clamped-virtual `Interval`/`TinglingInterval` construction matches their model fields. `SENTINEL` is defined once in Task 6 and imported by its test. `backfill_overnight` name matches between Task 6 module, test, and `main.py`.
