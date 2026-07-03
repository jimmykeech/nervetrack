# Edit timer intervals — labels + times on past days

**Date:** 2026-07-03
**Status:** Draft — awaiting review

## Problem

Users want to go back to previous timer intervals and add/edit the **labels**
attached to them, and ideally adjust the **times** too. Today:

- The Timer page (`frontend/src/routes/timer/+page.svelte`) only ever loads
  **today** — there is no way to navigate to a past day's intervals.
- The timeline table **displays** an interval's label but offers no way to
  add/edit/clear it.
- Start/end **times are already editable** on the loaded day (the `editTime()`
  prompt → `PATCH /timer/intervals/{id}`), but this is only reachable for today.

## Investigation: what altering times already means

`PATCH /timer/intervals/{id}` (`backend/app/routers/timer.py`,
`backend/app/services/timer.py::patch_interval`) already accepts `posture`,
`started_at`, `ended_at`, and `label`. On edit it **recomputes**
`duration_seconds` and the interval's `entry_date` (from the new start's local
date). So time-editing functions end-to-end.

The only gap is **validation**: there is no check that `ended_at > started_at`,
so a mistyped time can produce a negative duration; there is also no overlap
detection. These are data-quality issues (skewed posture totals), not crashes.
Adding a simple `end > start` guard makes time-editing safe to expose.

**Conclusion:** enabling time-editing on past days is low-risk with a small
guard, so this design includes both labels and times.

## Goal

On the Timer page, let the user navigate to any past day and, in that day's
timeline, add/edit/clear an interval's label and edit its start/end times —
safely.

## Design

### 1. Backend — validation guard (`backend/app/services/timer.py`)

In `patch_interval`, after computing `new_start`/`new_end`, if `new_end is not
None and new_end <= new_start`, raise a `ValueError` (or domain error) that the
router maps to `HTTP 400 "End must be after start"`. The router
(`backend/app/routers/timer.py::patch_interval`) catches it and returns 400.
Label clearing already works: the endpoint distinguishes "label omitted" from
"label set to null" via `label_set`.

No other backend change. `start` (creating a new running interval) is
unaffected.

### 2. Frontend — date navigation on the Timer page

Add a date bar above the timeline mirroring the Today page's pattern
(`frontend/src/routes/+page.svelte` `.datebar`): `‹` previous day, a
`<input type="date">`, a "Today" button (shown when not on today), and `›` next
day (disabled when already at today). Changing the date calls the store's
existing `TimerStore.load(date)`.

Conditional display by viewed date (`store.date === todayISO()`):

- **Today:** unchanged — live-display card, posture start/stop card, totals,
  editable timeline.
- **Past day:** hide the live-display card and the posture start/stop card
  (starting a timer in the past is meaningless); show the totals card and the
  editable timeline. The heading changes from "Today's timeline" to the viewed
  date (e.g. "Timeline — 2026-06-30").

`store.totals` already reflects only the loaded day's intervals, so totals are
correct for past days.

### 3. Frontend — label editing

In the timeline table's actions cell, add a **"label"** `.link` button beside
the existing "delete" (same style as `editTime`/`delete`). It opens a
`prompt()` prefilled with the interval's current label; on submit it calls
`store.editInterval(id, { label })`.

Normalisation: a new pure helper `normalizeLabel(input: string | null):
string | null` trims the input and returns `null` for empty/whitespace (so
clearing the field removes the label), otherwise the trimmed string. This
matches the existing "whitespace label = empty" behaviour on start.

Start/End times keep their current click-to-edit (`editTime`), now reachable on
any loaded day.

### 4. Frontend — client-side time guard

In `editTime`, after parsing the new value, if the resulting interval would
have `end <= start` (compare against the interval's other endpoint), show an
inline error and do not submit — defense-in-depth alongside the backend guard.

## Non-goals (YAGNI)

- No creating brand-new intervals for past days (edit existing only).
- No overlap detection between intervals (pre-existing possibility; unchanged).
- No bulk editing, no posture editing UI (posture stays as-is; backend still
  supports it but no new control is added).
- No redesign of the prompt-based editing into inline forms (keep the existing
  `prompt()` pattern for consistency and minimal surface).

## Testing

- **Backend** (`backend/tests/test_timer.py`): add tests that
  `patch_interval` (a) rejects `ended_at <= started_at` with an error/400,
  (b) sets a label, (c) clears a label (empty → null), (d) recomputes
  `duration_seconds` and `entry_date` on a valid time edit.
- **Frontend**: unit-test the pure `normalizeLabel` helper (trims,
  empty/whitespace → null, keeps text). Date-navigation, conditional card
  display, and the label prompt are verified manually.
- Gate: `npm run check` / `lint` / `test` green; backend `pytest` + `ruff`
  green.
- Manual: on the Timer page, navigate to a past day, add/edit/clear a label,
  edit a start/end time, attempt an invalid (end ≤ start) edit and confirm it
  is rejected; confirm today's view is unchanged.
