# Retroactive time for pain jabs — design

**Date:** 2026-06-16
**Status:** Approved (pending spec review)

## Problem

On the Today main screen, logging a pain jab always stamps it with the current
time (`now_utc()`). The user wants to log jabs that happened earlier — e.g. when
they did not have the app to hand — by choosing the time after the fact. The
current time must remain the default; selecting another time is opt-in.

## Scope decisions (agreed)

- **Time scope:** time-of-day *within the currently viewed day*. The day a jab
  belongs to is already selectable via the existing date bar (‹ › arrows + date
  picker). The new control only sets the time-of-day. Logging a jab for a
  different day means navigating to that day first, then logging — no full
  date+time picker in the form.
- **Field UX:** the time control is hidden by default behind a "change time"
  link, so the form stays minimal. The link shows the default time that will be
  used, so it is never a mystery.

## Key finding: backend already supports this, plus a latent timezone bug

The write path is already wired end to end for an optional timestamp:

- `PainEventIn.occurred_at: datetime | None = None` (model)
- `add_pain_event(...)` does `occurred = occurred_at or now_utc()` (service)
- `api.addPainEvent(date, { ..., occurred_at?: string })` (frontend client)

The only missing piece is UI: the jab form never sends `occurred_at`.

**However**, there is a latent timezone bug that this feature would trigger:

- Timestamps are stored as **naive UTC** (`timeutil.now_utc()` returns naive
  UTC; the `pain_events.occurred_at` column is `TIMESTAMP`).
- The frontend displays them by appending `Z`: `new Date(iso + 'Z')` in
  `fmtTime`, i.e. it assumes the stored value is naive UTC.
- The pain-event router passes `data.occurred_at` straight into the INSERT
  **without normalizing**, even though a `to_utc_naive()` helper already exists
  in `timeutil` for exactly this purpose.

Today nothing exercises this path (`occurred_at` is always null →
`now_utc()`), so the bug is dormant. The moment the frontend sends a real
timestamp carrying a `Z`/offset, it would be stored *with* an offset and then
**double-converted** on display (offset applied once by Python's ISO parse, then
`Z` appended again by the frontend). So the design includes a one-line backend
hardening to normalize before storage.

## Design

### 1. Backend hardening (`backend/app/services/entries.py`)

In `add_pain_event`, normalize the incoming timestamp to naive UTC before
storage using the existing helper:

```python
occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
```

No schema change, no API-shape change. `now_utc()` remains the default when the
client sends nothing.

### 2. Frontend jab form (`frontend/src/routes/+page.svelte`)

New component state:

- `jabTimeOpen: boolean` — default `false`; whether the picker is revealed.
- `jabTime: string` — an `HH:MM` value bound to `<input type="time">`.

Default-time resolution (a pure helper, so it is testable):

- If the viewed `date` is **today** → default to the current clock time.
- If the viewed `date` is a **past day** → default to `12:00` (there is no
  "now" within a past day).

UI, placed under the existing Level / Context row in the jab form:

- A small link reading **"logged {default} · change time"** where `{default}`
  is the resolved default time. Tapping it sets `jabTimeOpen = true` and shows a
  native `<input type="time">` bound to `jabTime` (seeded with the default).

`logJab()` behaviour:

- Build the `occurred_at` to send:
  - If the viewed day is **today** and the user never opened the picker
    (`!jabTimeOpen`) → send nothing (`occurred_at` undefined), letting the
    backend stamp `now_utc()` with full seconds precision.
  - Otherwise (picker opened, or viewing a **past day**) → combine the viewed
    `date` and the chosen/default `HH:MM` into a local `Date` and send
    `.toISOString()` (UTC, with `Z`). On a past day this always sends a time so
    the event is not mis-stamped with today's clock.
- After logging, reset `jabTimeOpen = false` and clear/re-seed `jabTime`, in the
  same place the existing code clears `jabContext`.

Round-trip correctness: frontend sends UTC ISO (`Z`) → backend `to_utc_naive`
strips to naive UTC → stored → read back as naive → serialized without offset →
frontend appends `Z` → correct local display. The existing "log now" path
(no `occurred_at`) is unchanged.

### 3. Time helper (`frontend/src/lib/time.ts`)

Add a pure function, unit-tested alongside the existing `time.test.ts`:

- `combineDateTimeToISO(dateISO: string, hhmm: string): string` — combine a
  `YYYY-MM-DD` date and an `HH:MM` local time into a UTC ISO string.
- A small helper for the default time given a date (today → current `HH:MM`,
  past → `"12:00"`) — or compute inline in the component; whichever keeps the
  component clean. Prefer the helper so it can be unit-tested.

## Out of scope (YAGNI)

- Editing the time of an already-logged jab (remove + re-add covers it).
- A full date+time picker in the form (day is chosen via navigation).
- Changing how jabs are bucketed into daily entries.

## Testing

- **Backend:** new test — POST a pain event with an aware timestamp (e.g.
  `...+10:00` or `Z`) and assert the stored/returned `occurred_at` is the
  correct naive UTC value. Existing pain-event tests stay green.
- **Frontend:** unit tests for `combineDateTimeToISO` (and the default-time
  helper if extracted) in `time.test.ts`.

## Files touched

- `backend/app/services/entries.py` — normalize `occurred_at` (+ import).
- `backend/tests/test_entries.py` — new normalization test.
- `frontend/src/routes/+page.svelte` — time link + picker + `logJab` change.
- `frontend/src/lib/time.ts` — `combineDateTimeToISO` (+ default-time helper).
- `frontend/src/lib/time.test.ts` — unit tests.
