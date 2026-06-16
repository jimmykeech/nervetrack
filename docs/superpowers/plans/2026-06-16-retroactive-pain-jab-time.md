# Retroactive Pain Jab Time — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user log a pain jab at a chosen time-of-day within the viewed day, defaulting to the current time, without breaking the existing "log now" path.

**Architecture:** The write path already accepts an optional `occurred_at` end to end. We (1) harden the backend to normalize an incoming timestamp to naive UTC before storage, and (2) add a collapsible time control to the jab form that sends a UTC ISO timestamp built from the viewed date + chosen local time.

**Tech Stack:** FastAPI + SQLite (Python 3.13, pytest, ruff) backend; SvelteKit (Svelte 5 runes, TypeScript, vitest) frontend.

**Spec:** `docs/superpowers/specs/2026-06-16-retroactive-pain-jab-time-design.md`

---

## File Structure

- `backend/app/services/entries.py` — modify `add_pain_event` to normalize `occurred_at` via the existing `to_utc_naive` helper (+ import).
- `backend/tests/test_entries.py` — new test asserting an aware timestamp is stored/returned as naive UTC.
- `frontend/src/lib/time.ts` — add two pure helpers: `defaultJabTime(dateISO, now?)` and `combineDateTimeToISO(dateISO, hhmm)`.
- `frontend/src/lib/time.test.ts` — unit tests for the two new helpers.
- `frontend/src/routes/+page.svelte` — add collapsible time control + wire `logJab` to send `occurred_at`.

---

## Task 1: Backend normalizes `occurred_at` to naive UTC

**Files:**
- Modify: `backend/app/services/entries.py` (import line ~19; `add_pain_event` ~122-139)
- Test: `backend/tests/test_entries.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_entries.py`:

```python
def test_pain_event_normalizes_aware_timestamp_to_naive_utc(db, user_id):
    from datetime import datetime, timezone, timedelta

    d = date(2026, 6, 13)
    # 22:30 at UTC+10 == 12:30 UTC. Stored value must be naive UTC.
    aware = datetime(2026, 6, 13, 22, 30, tzinfo=timezone(timedelta(hours=10)))
    ev = service.add_pain_event(db, user_id, d, aware, 4, None)
    assert ev.occurred_at == datetime(2026, 6, 13, 12, 30)
    assert ev.occurred_at.tzinfo is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_entries.py::test_pain_event_normalizes_aware_timestamp_to_naive_utc -v`
Expected: FAIL — returned `occurred_at` is timezone-aware / equals `22:30+10:00`, not naive `12:30`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/entries.py`, update the import line:

```python
from app.services.timeutil import now_utc, to_utc_naive
```

In `add_pain_event`, change the timestamp line from:

```python
        occurred = occurred_at or now_utc()
```

to:

```python
        occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_entries.py -v`
Expected: PASS — new test passes, existing pain-event tests still green.

- [ ] **Step 5: Lint**

Run: `cd backend && .venv/bin/ruff check app/services/entries.py tests/test_entries.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/entries.py backend/tests/test_entries.py
git commit -m "fix(entries): normalize pain-event occurred_at to naive UTC"
```

---

## Task 2: Time helpers in `time.ts`

**Files:**
- Modify: `frontend/src/lib/time.ts`
- Test: `frontend/src/lib/time.test.ts`

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/lib/time.test.ts` (and add `combineDateTimeToISO, defaultJabTime, todayISO` to the existing import from `'./time'`):

```typescript
describe('combineDateTimeToISO', () => {
  it('combines a local date and HH:MM into a UTC ISO string', () => {
    // Round-trips back to the same local wall-clock time.
    const iso = combineDateTimeToISO('2026-06-13', '14:30');
    const back = new Date(iso);
    expect(back.getFullYear()).toBe(2026);
    expect(back.getMonth()).toBe(5); // June (0-based)
    expect(back.getDate()).toBe(13);
    expect(back.getHours()).toBe(14);
    expect(back.getMinutes()).toBe(30);
    expect(iso.endsWith('Z')).toBe(true);
  });
});

describe('defaultJabTime', () => {
  it('returns 12:00 for a past day', () => {
    expect(defaultJabTime('2000-01-01')).toBe('12:00');
  });

  it("returns the current local HH:MM for today", () => {
    const now = new Date(2026, 5, 13, 9, 5); // 09:05 local
    expect(defaultJabTime(todayISO(), now)).toBe('09:05');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/time.test.ts`
Expected: FAIL — `combineDateTimeToISO` / `defaultJabTime` are not exported.

- [ ] **Step 3: Write minimal implementation**

Append to `frontend/src/lib/time.ts`:

```typescript
/** Combine a local YYYY-MM-DD date and HH:MM time into a UTC ISO string. */
export function combineDateTimeToISO(dateISO: string, hhmm: string): string {
  const [y, m, d] = dateISO.split('-').map(Number);
  const [hh, mm] = hhmm.split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm, 0, 0).toISOString();
}

/**
 * Default time for the jab picker on a given day: the current local time when
 * `dateISO` is today, otherwise noon (there is no "now" within a past day).
 */
export function defaultJabTime(dateISO: string, now: Date = new Date()): string {
  if (dateISO !== todayISO()) return '12:00';
  const hh = now.getHours().toString().padStart(2, '0');
  const mm = now.getMinutes().toString().padStart(2, '0');
  return `${hh}:${mm}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/time.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/time.ts frontend/src/lib/time.test.ts
git commit -m "feat(time): combineDateTimeToISO + defaultJabTime helpers"
```

---

## Task 3: Collapsible time control in the jab form

**Files:**
- Modify: `frontend/src/routes/+page.svelte` (script ~7, ~28-31, ~84-92; markup ~207-218; styles)

- [ ] **Step 1: Add the helper imports**

In `+page.svelte`, extend the existing import from `$lib/time` to include the two new helpers:

```typescript
  import {
    combineDateTimeToISO,
    defaultJabTime,
    formatMinutesLabel,
    parseDurationToMinutes,
    shiftISODate,
    todayISO
  } from '$lib/time';
```

- [ ] **Step 2: Add jab-time state**

Replace the existing pain-jab state block:

```typescript
  // Pain jab mini-form.
  let showJab = $state(false);
  let jabLevel = $state<number | null>(3);
  let jabContext = $state('');
```

with:

```typescript
  // Pain jab mini-form.
  let showJab = $state(false);
  let jabLevel = $state<number | null>(3);
  let jabContext = $state('');
  let jabTimeOpen = $state(false);
  let jabTime = $state('');
  const jabDefaultTime = $derived(defaultJabTime(date));
```

- [ ] **Step 3: Update `logJab` to send `occurred_at`**

Replace the existing `logJab`:

```typescript
  async function logJab() {
    await api.addPainEvent(date, {
      pain_level: jabLevel ?? undefined,
      context: jabContext || undefined
    });
    jabContext = '';
    showJab = false;
    await load(date);
  }
```

with:

```typescript
  async function logJab() {
    // Today + untouched picker → let the server stamp now() (full precision).
    // Past day, or an edited time → send the chosen wall-clock time.
    const sendTime = jabTimeOpen || date !== todayISO();
    const hhmm = jabTime || jabDefaultTime;
    await api.addPainEvent(date, {
      pain_level: jabLevel ?? undefined,
      context: jabContext || undefined,
      occurred_at: sendTime ? combineDateTimeToISO(date, hhmm) : undefined
    });
    jabContext = '';
    jabTimeOpen = false;
    jabTime = '';
    showJab = false;
    await load(date);
  }
```

- [ ] **Step 4: Add the time control to the markup**

Replace the jab-form block:

```svelte
  {#if showJab}
    <div class="jab-form">
      <div style="flex: 1; min-width: 8rem">
        <Stepper label="Level" bind:value={jabLevel} min={0} max={10} step={0.5} />
      </div>
      <div style="flex: 2; min-width: 10rem">
        <label>Context (optional)</label>
        <input bind:value={jabContext} placeholder="e.g. sitting at desk" />
      </div>
      <button class="status-G" style="align-self: flex-end" onclick={logJab}>Log</button>
    </div>
  {/if}
```

with:

```svelte
  {#if showJab}
    <div class="jab-form">
      <div style="flex: 1; min-width: 8rem">
        <Stepper label="Level" bind:value={jabLevel} min={0} max={10} step={0.5} />
      </div>
      <div style="flex: 2; min-width: 10rem">
        <label>Context (optional)</label>
        <input bind:value={jabContext} placeholder="e.g. sitting at desk" />
      </div>
      <button class="status-G" style="align-self: flex-end" onclick={logJab}>Log</button>
    </div>
    <div class="jab-time">
      {#if jabTimeOpen}
        <label for="jab-time-input">Time</label>
        <input id="jab-time-input" type="time" bind:value={jabTime} />
      {:else}
        <button
          class="link"
          onclick={() => {
            jabTime = jabDefaultTime;
            jabTimeOpen = true;
          }}
        >
          logged {jabDefaultTime} · change time
        </button>
      {/if}
    </div>
  {/if}
```

- [ ] **Step 5: Add styling for the time row**

Append to the `<style>` block (near `.jab-form`):

```css
  .jab-time {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .jab-time label {
    margin: 0;
  }
```

- [ ] **Step 6: Typecheck and build**

Run: `cd frontend && npm run check`
Expected: 0 errors, 0 warnings (or unchanged from baseline).

- [ ] **Step 7: Manual sanity check**

Run: `cd frontend && npm run build`
Expected: build succeeds. (Full UI verification happens via the verify skill after merge.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(today): retroactive time picker for pain jabs"
```

---

## Task 4: Full verification

- [ ] **Step 1: Backend suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 2: Frontend tests + check**

Run: `cd frontend && npm run test && npm run check`
Expected: all pass.

- [ ] **Step 3: Verify behaviour in the running app**

Use the `verify` skill (or `npm run dev` + backend) to confirm:
- On today's screen, "Log" without touching the time → event time ≈ now.
- "change time" → pick an earlier time → logged event shows that time.
- Navigate to a previous day, log a jab → event shows the picked (default 12:00) time on that day, not today's clock.

---

## Self-Review

- **Spec coverage:** backend normalization (Task 1) ✓; collapsible "change time" link defaulting to resolved time (Task 3) ✓; today-vs-past default + send logic (Task 3 `logJab`, Task 2 `defaultJabTime`) ✓; `combineDateTimeToISO` helper + tests (Task 2) ✓; backend aware-timestamp test (Task 1) ✓. Out-of-scope items (edit existing jab, full date+time) correctly excluded.
- **Type consistency:** `combineDateTimeToISO(dateISO, hhmm)` and `defaultJabTime(dateISO, now?)` signatures match between definition (Task 2) and use (Task 3). `api.addPainEvent` already accepts `{ pain_level?, context?, occurred_at? }`.
- **Placeholders:** none — every code step shows full content.
