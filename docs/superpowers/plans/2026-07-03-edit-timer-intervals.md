# Edit Timer Intervals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users navigate to a past day on the Timer page and add/edit/clear an interval's label and edit its start/end times, with a validation guard that rejects end ≤ start.

**Architecture:** The backend `PATCH /timer/intervals/{id}` already edits label/posture/times and recomputes duration + entry_date; we add only an `end > start` guard. The frontend gains date navigation on the Timer page (reusing `TimerStore.load(date)`), a per-row label-edit action, and a client-side guard — built on two new pure helpers.

**Tech Stack:** FastAPI + Python (pytest, ruff) backend; SvelteKit (Svelte 5) + TypeScript (Vitest) frontend.

## Global Constraints

- Backend commands run from `backend/`; frontend from `frontend/`.
- Services signal bad input by raising `ValueError`; routers catch it and raise `HTTPException(400, str(exc))` (existing pattern, e.g. `backend/app/routers/sessions.py`).
- Keep the existing `prompt()`-based editing pattern (no inline-form redesign).
- Guard rule everywhere: an interval with a non-null end must satisfy `end > start`.
- Label normalisation: trimmed input; empty/whitespace becomes `null` (clears the label).
- No creating new intervals for past days; no overlap detection; no posture-edit UI.

---

### Task 1: Backend — reject end ≤ start on interval edits

**Files:**
- Modify: `backend/app/services/timer.py` (`patch_interval`)
- Modify: `backend/app/routers/timer.py` (`patch_interval` route)
- Test: `backend/tests/test_timer.py`

**Interfaces:**
- Consumes: existing `service.patch_interval(db, user_id, interval_id, posture, started_at, ended_at, label, label_set)`.
- Produces: `patch_interval` now raises `ValueError("End must be after start")` when the resulting `ended_at <= started_at`; the route returns HTTP 400 for that.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_timer.py` (add `import pytest` at the top if not present):

```python
def test_patch_rejects_end_not_after_start(db, user_id):
    interval = service.start(db, user_id, "sitting", None)
    with pytest.raises(ValueError):
        service.patch_interval(
            db,
            user_id,
            interval.id,
            posture=None,
            started_at=datetime(2026, 1, 1, 9, 0, 0),
            ended_at=datetime(2026, 1, 1, 9, 0, 0),  # equal -> invalid
            label=None,
            label_set=False,
        )


def test_patch_sets_and_clears_label(db, user_id):
    interval = service.start(db, user_id, "sitting", None)
    with_label = service.patch_interval(
        db, user_id, interval.id,
        posture=None, started_at=None, ended_at=None,
        label="focus", label_set=True,
    )
    assert with_label is not None and with_label.label == "focus"
    cleared = service.patch_interval(
        db, user_id, interval.id,
        posture=None, started_at=None, ended_at=None,
        label=None, label_set=True,
    )
    assert cleared is not None and cleared.label is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `backend/`:

```bash
pytest tests/test_timer.py::test_patch_rejects_end_not_after_start tests/test_timer.py::test_patch_sets_and_clears_label -q
```

Expected: `test_patch_rejects_end_not_after_start` FAILS (no exception raised); the label test likely passes already (label editing works) — that is fine, it locks in behaviour.

- [ ] **Step 3: Add the guard in the service**

In `backend/app/services/timer.py::patch_interval`, immediately after the `new_end = ...` line and before `new_label = ...`, insert:

```python
    if new_end is not None and new_end <= new_start:
        raise ValueError("End must be after start")
```

- [ ] **Step 4: Map the error to 400 in the route**

In `backend/app/routers/timer.py::patch_interval`, replace the service call block:

```python
    updated = service.patch_interval(
        db,
        user_id,
        interval_id,
        posture=data.posture,
        started_at=data.started_at,
        ended_at=data.ended_at,
        label=data.label,
        label_set="label" in fields,
    )
    if updated is None:
        raise HTTPException(404, "No such interval")
    return updated
```

with:

```python
    try:
        updated = service.patch_interval(
            db,
            user_id,
            interval_id,
            posture=data.posture,
            started_at=data.started_at,
            ended_at=data.ended_at,
            label=data.label,
            label_set="label" in fields,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, "No such interval")
    return updated
```

- [ ] **Step 5: Run tests to verify they pass**

Run from `backend/`:

```bash
pytest tests/test_timer.py -q
```

Expected: all timer tests pass (including the two new ones).

- [ ] **Step 6: Lint**

Run from `backend/`:

```bash
ruff check app/services/timer.py app/routers/timer.py tests/test_timer.py
```

Expected: clean (exit 0).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/timer.py backend/app/routers/timer.py backend/tests/test_timer.py
git commit -m "feat(timer): reject interval edits where end <= start"
```

---

### Task 2: Frontend — pure helpers `normalizeLabel` + `endsAfterStart`

**Files:**
- Modify: `frontend/src/lib/time.ts`
- Test: `frontend/src/lib/time.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalizeLabel(input: string | null | undefined): string | null` — trimmed input, or `null` if empty/whitespace.
  - `endsAfterStart(startIso: string, endIso: string): boolean` — `true` iff `endIso` is strictly later than `startIso`.

- [ ] **Step 1: Write failing tests**

Add to `frontend/src/lib/time.test.ts` (extend imports from `./time` to include the two new names):

```ts
import { normalizeLabel, endsAfterStart } from './time';

describe('normalizeLabel', () => {
  it('trims non-empty input', () => {
    expect(normalizeLabel('  work ')).toBe('work');
  });
  it('returns null for empty or whitespace', () => {
    expect(normalizeLabel('')).toBeNull();
    expect(normalizeLabel('   ')).toBeNull();
    expect(normalizeLabel(null)).toBeNull();
  });
});

describe('endsAfterStart', () => {
  it('is true when end is after start', () => {
    expect(endsAfterStart('2026-01-01T09:00:00', '2026-01-01T09:30:00')).toBe(true);
  });
  it('is false when end equals or precedes start', () => {
    expect(endsAfterStart('2026-01-01T09:00:00', '2026-01-01T09:00:00')).toBe(false);
    expect(endsAfterStart('2026-01-01T09:30:00', '2026-01-01T09:00:00')).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `frontend/`:

```bash
npm run test -- src/lib/time.test.ts
```

Expected: FAIL — `normalizeLabel`/`endsAfterStart` are not exported.

- [ ] **Step 3: Implement the helpers**

Append to `frontend/src/lib/time.ts`:

```ts
/** Trim a user-entered interval label; empty/whitespace becomes null (clears it). */
export function normalizeLabel(input: string | null | undefined): string | null {
  const s = (input ?? '').trim();
  return s === '' ? null : s;
}

/** True when an interval's end is strictly after its start (ISO datetime strings). */
export function endsAfterStart(startIso: string, endIso: string): boolean {
  return new Date(endIso).getTime() > new Date(startIso).getTime();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `frontend/`:

```bash
npm run test -- src/lib/time.test.ts
```

Expected: PASS (new suites plus the existing time tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/time.ts frontend/src/lib/time.test.ts
git commit -m "feat(timer): add normalizeLabel and endsAfterStart helpers"
```

---

### Task 3: Frontend — Timer page date nav, label editing, client guard

**Files:**
- Modify: `frontend/src/routes/timer/+page.svelte`

**Interfaces:**
- Consumes: `normalizeLabel`, `endsAfterStart` (Task 2); `shiftISODate`, `todayISO` (existing in `$lib/time`); `TimerStore.load`, `TimerStore.editInterval`, `TimerStore.deleteInterval` (existing).
- Produces: nothing (leaf UI).

- [ ] **Step 1: Update imports and add state/derived**

In `frontend/src/routes/timer/+page.svelte`, extend the `$lib/time` import to add `shiftISODate`, `todayISO`, `normalizeLabel`, `endsAfterStart`. After the existing `let label = $state('');` line, add:

```ts
  let editErr = $state('');
  const isToday = $derived(store.date === todayISO());
```

- [ ] **Step 2: Add the label-edit handler and extend the time guard**

Replace the existing `editTime` function with the version below and add `editLabel` right after it:

```ts
  async function editTime(id: string, field: 'started_at' | 'ended_at', current: string | null) {
    editErr = '';
    const iv = store.intervals.find((x) => x.id === id);
    const initial = current ? new Date(current + 'Z').toISOString().slice(0, 16) : '';
    const input = prompt(
      `New ${field === 'started_at' ? 'start' : 'end'} time (YYYY-MM-DDTHH:MM)`,
      initial
    );
    if (!input) return;
    const utc = new Date(input).toISOString().slice(0, 19);
    if (iv) {
      const start = field === 'started_at' ? utc : iv.started_at;
      const end = field === 'ended_at' ? utc : iv.ended_at;
      if (end && !endsAfterStart(start, end)) {
        editErr = 'End time must be after the start time.';
        return;
      }
    }
    await store.editInterval(id, { [field]: utc });
  }

  async function editLabel(id: string, current: string | null) {
    const input = prompt('Label for this interval (leave empty to clear)', current ?? '');
    if (input === null) return; // cancelled
    await store.editInterval(id, { label: normalizeLabel(input) });
  }
```

- [ ] **Step 3: Add the date-navigation bar**

Immediately below the closing `</script>` and above the `<div class="card display" ...>` line, insert:

```svelte
<div class="datebar card">
  <button onclick={() => store.load(shiftISODate(store.date, -1))} aria-label="previous day">‹</button>
  <div class="datepick">
    <input
      type="date"
      value={store.date}
      max={todayISO()}
      onchange={(e) => store.load((e.currentTarget as HTMLInputElement).value)}
    />
    {#if !isToday}<button class="today" onclick={() => store.load(todayISO())}>Today</button>{/if}
  </div>
  <button
    onclick={() => store.load(shiftISODate(store.date, 1))}
    aria-label="next day"
    disabled={store.date >= todayISO()}>›</button
  >
</div>
```

- [ ] **Step 4: Show live/start cards only for today**

Wrap the two "now" cards — the `<div class="card display" ...>...</div>` block AND the `<div class="card">` block that contains the label input + posture buttons (the `.postures` card) — in a single `{#if isToday}` … `{/if}`. The totals card and the timeline card remain outside the guard (always shown).

- [ ] **Step 5: Update the timeline heading, add the label action, and show the guard error**

In the timeline card, change the heading:

```svelte
  <h3 style="margin-top: 0">{isToday ? "Today's timeline" : `Timeline — ${store.date}`}</h3>
```

In the actions cell of each row, add a "label" button before the existing "delete" button:

```svelte
              <td>
                <button class="link" onclick={() => editLabel(iv.id, iv.label)}>label</button>
                <button class="link danger" onclick={() => store.deleteInterval(iv.id)}>delete</button>
              </td>
```

Directly under the timeline card's `<h3>` (before the `{#if store.intervals.length === 0}` block), add the guard-error line:

```svelte
  {#if editErr}<p class="error small">{editErr}</p>{/if}
```

- [ ] **Step 6: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0.

- [ ] **Step 7: Manual verification**

With `npm run dev` running (and backend up): on the Timer page, use `‹ / › / date picker / Today` to open a past day — confirm the live/start cards are hidden and the totals + timeline show. Click **label** on a row: set, change, and clear a label (empty clears it). Click a **Start/End** time and edit it; then attempt an edit that makes end ≤ start and confirm the inline error appears and nothing is saved. Switch back to today and confirm live tracking + posture buttons are unchanged.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/timer/+page.svelte
git commit -m "feat(timer): navigate past days and edit interval labels/times"
```

---

## Self-Review

**Spec coverage:**
- Backend end>start guard + 400 (spec §1) → Task 1.
- Timer-page date navigation + conditional cards on past days (spec §2) → Task 3 steps 3–4.
- Label editing with empty→null (spec §3) → Task 2 (`normalizeLabel`) + Task 3 steps 2, 5.
- Client-side time guard (spec §4) → Task 2 (`endsAfterStart`) + Task 3 step 2.
- Testing (spec) → Task 1 backend tests, Task 2 helper tests, Task 3 manual.
- Non-goals respected: no new-interval creation, no overlap detection, no posture-edit UI, prompt pattern kept.

Known behaviour (unchanged, noted for the reviewer, not a task): editing a start time that crosses midnight moves the interval to another day (`entry_date` recompute), so it leaves the current day's view — pre-existing backend behaviour, acceptable.

**Placeholder scan:** No TBD/TODO; all steps give concrete code and commands.

**Type consistency:** `normalizeLabel`/`endsAfterStart` signatures match between Task 2 (produced) and Task 3 (consumed). `editInterval(id, { label })` / `editInterval(id, { [field]: utc })` match the store's existing `editInterval(id: string, data: Partial<Interval>)`; `label: normalizeLabel(...)` yields `string | null`, matching `Interval.label`. Date helpers `shiftISODate`/`todayISO` are the same ones the Today page uses.
