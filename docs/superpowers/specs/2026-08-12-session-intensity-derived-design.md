# Session intensity belongs to the session (issue #25)

**Issue:** [#25](https://github.com/jimmykeech/nervetrack/issues/25) — "Unable to update session intensity level after the fact."

## Problem

The issue proposes moving intensity "into the session log". It is already there:
`strength_sessions.intensity` exists (`backend/app/migrations/0001_initial.sql:63`),
`SessionIn`/`SessionDetail` carry it (`backend/app/models/sessions.py:31,41`), and the
exercises page sends it on save (`frontend/src/routes/exercises/+page.svelte:149`).

No schema change is needed. Three real defects produce the reported symptom:

1. **The input is visually detached from the session.** It sits in the top "session meta"
   card next to *Session date* (`exercises/+page.svelte:219-222`), not in the
   "Log session / Edit session" card. Clicking *Edit* on a logged session leaves the
   intensity field in a different card further up the page, so it does not read as part
   of the session being edited.
2. **`daily_entries.session_intensity` is a second, independently writable copy.** The
   Today page writes it directly (`routes/+page.svelte:93,211`) through
   `DailyEntryUpsert` (`models/entries.py:35`) and `_UPSERT_COLUMNS`
   (`services/entries.py:26`). Editing it there silently diverges from the session.
3. **The day-level mirror is last-write-wins.** `create_session` and `update_session`
   stamp the day row with whatever session was just saved
   (`services/sessions.py:152,177`), so with two sessions in a day the stored value can
   reflect the older one. Only `delete_session` re-derives (`sessions.py:193`).

## Design

`strength_sessions.intensity` is the single source of truth.
`daily_entries.session_intensity` becomes a **derived cache**: `MAX(intensity)` over that
day's sessions, recomputed on every session write, never directly writable by a client.

Max, not average or latest: peak load is what correlates with next-day symptoms in a pain
tracker, and averaging a 9 with a 3 hides the 9.

### Backend

**`services/sessions.py` — one resync helper.** Add:

```python
def _resync_entry_intensity(db: Database, daily_entry_id: UUID) -> None:
    """Recompute the daily-entry mirror from the day's sessions.

    ``session_intensity`` is derived, never written directly: it is the peak
    intensity across the day's sessions. With no sessions left, the day is no
    longer a strengthening day.
    """
```

It replaces all three ad-hoc `UPDATE daily_entries` blocks (lines 152, 177, 193-208).
Behaviour:

- Day has one or more sessions → `strengthening_done = TRUE`,
  `session_intensity = MAX(intensity)` across them (`NULL` if every session's intensity
  is `NULL`), `updated_at = now_utc()`.
- Day has no sessions → `strengthening_done = FALSE`, `session_intensity = NULL`,
  `updated_at = now_utc()`.

`create_session`, `update_session` and `delete_session` each call it once inside their
existing transaction. They cannot drift apart again.

**`models/entries.py` — make the field output-only.** Remove `session_intensity` from
`DailyEntryUpsert` (line 35). Keep it on `DailyEntry` (line 64) and `DailyEntrySummary`
(line 51) — it is still read by Today, history, stats and the AI context.

**`services/entries.py` — remove `"session_intensity"` from `_UPSERT_COLUMNS`** (line 26).

Pydantic ignores unknown fields by default, so a stale client sending
`session_intensity` gets a silent no-op rather than a 422. That is the intended
behaviour; do not add an explicit rejection.

**Migration `0009_session_intensity_derived.sql`.** Two statements, in this order:

1. **Backfill.** Where a day has exactly one session whose `intensity IS NULL` and the
   day row has a non-null `session_intensity`, copy the day value onto that session.
   This is exactly the shape the xlsx importer produces (one session per imported day,
   created with no intensity), so imported history becomes real per-session data.
2. **Recompute.** Set `daily_entries.session_intensity = MAX(s.intensity)` for every day
   that has **at least one session with a non-null intensity**.

The guard on statement 2 matters: days holding an intensity with no session to attribute
it to (or with only null-intensity sessions) keep their value rather than being blanked.
Preserving that data was an explicit decision — do not "simplify" it into an
unconditional recompute.

Follow the existing migration-runner conventions; check how `0007`/`0008` are registered
and discovered before writing the file.

**`services/xlsx_import.py` — stop recreating the split.** The importer writes day-level
`session_intensity` at line 156 but creates sessions with no intensity at line 336. Set
the created session's intensity from the day row's `session_intensity` so re-imports
land in the new model. Verify the import ordering first: if the sessions sheet is
imported before the daily sheet, read the value after both have run or re-resync at the
end of the import.

### Frontend

**Today (`routes/+page.svelte`).**

- Remove the `session_intensity` `Stepper` (lines 207-218) and the `session_intensity`
  key from the `save()` payload (line 93). Keep the `strengthening_done` checkbox — it
  is still a directly meaningful daily flag, and session writes only ever turn it on.
- Add a **Sessions** card for the day: one row per session showing time (local, via
  `utcNaiveToLocalInput` as `exercises/+page.svelte:71-73` does), intensity, exercise
  names, and notes. Each row links to `/exercises` for that date. Show a quiet empty
  state when the day has no sessions.
- Data comes from the existing `api.sessionsForDate(date)`
  (`lib/api.ts:130` → `GET /entries/{date}/sessions`). No new endpoint.

**Exercises (`routes/exercises/+page.svelte`).** Move the intensity field (lines 219-222)
out of the top `session-meta` card and into the "Log session / Edit session" card,
beside the session notes input. The top card keeps only *Session date*. Move the
`.f-intensity` style (line 488) with it. This is the direct fix for the reported
complaint: the field becomes visibly part of the session being edited.

**History (`routes/history/+page.svelte:45`).** Relabel the series to
`Peak session intensity` — the number now means the hardest session of the day.

**Types (`lib/types.ts`).** `upsertEntry` takes `Partial<DailyEntry>` (`api.ts:99`), so
no type change is required; the field simply stops being sent. Leave
`session_intensity` on the read interfaces.

## Testing

- `backend/tests/test_sessions.py`: two sessions in a day with intensities 4 and 8 →
  day value 8 regardless of insertion order; lowering the 8 to 5 by update → day value 5;
  deleting the 8 → day value 4; deleting the last session → `NULL` and
  `strengthening_done = FALSE`; a day whose sessions all have null intensity → day value
  `NULL`.
- `backend/tests/test_entries.py`: `PUT /entries/{date}` with `session_intensity` does
  not change the stored value.
- `backend/tests/test_import.py`: an imported session carries the day's intensity.
- New migration test following the `test_records_migration.py` pattern: covers both the
  single-session backfill **and** the orphan-preservation case (day value, zero sessions
  → value survives).
- Frontend: extend existing `*.test.ts` coverage where it already exists for these pages.

## Out of scope

Plotting individual sessions on the history chart; changing the `DECIMAL(3,1)` column
type; any change to `strengthening_done` semantics.
