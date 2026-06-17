# Today page: timestamped note log + day timeline

**Date:** 2026-06-17
**Status:** Approved (design)

## Problem

The Today page captures the day's tracking, but two parts are weak:

1. **Notes** is a single freeform textarea per day, autosaved with a debounce. There is
   no record of *when* a note was written, and everything is mashed into one blob. This
   makes it useless for Phase 2 (the Claude live-chat assistant), which will need to
   reason over discrete, timestamped observations for weekly and ad-hoc discussion.
2. There is **no chronological view** of the day. Timer intervals, pain jabs, checkbox
   completions, and notes all exist but are scattered across separate cards, so you
   cannot see how the day actually unfolded.

## Goals

- Replace the single notes textarea with a **streamlined note logger**: type a note, hit
  submit, it is appended with a timestamp and the box clears, ready for the next one.
- Notes are stored as **discrete, timestamped, queryable rows** so Phase 2 can read them.
- Add a **combined day timeline** at the bottom of the Today page showing, in
  chronological order: timer intervals, pain jabs, checkbox completions, and notes — for
  whichever date is selected.

## Non-goals

- No Phase 2 chat/LLM work here. We only ensure the data model supports it.
- No changes to the timer, exercises, or weekly pages beyond what the shared data model
  forces (the importer; see below).
- No live second-by-second updating of the timeline (the running interval shows as
  "ongoing"; totals already live elsewhere).

## Decisions (from brainstorming)

- **Checkbox timing:** stamp the moment a box is ticked; unticking clears the stamp. One
  timestamp per box per day. No back-date picker for checkboxes (keeps it a single tap).
- **Existing notes:** migrate each day's existing `notes` text into one timestamped note
  (stamped at the entry's `updated_at`), then retire the old column.
- **Timeline style:** vertical "rail" — a line with colour-coded dots and small cards.
- **Note behaviour:** notes are editable, removable, and back-datable, mirroring the
  existing pain-jab pattern.
- **Composer placement:** the note composer replaces the old textarea; it does not sit
  alongside a freeform field.

## Data model

### New table: `notes`

Mirrors `pain_events` (per-entry, timestamped, child of `daily_entries`).

```sql
CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT (<randomblob uuid expr, same as other tables>),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    occurred_at TIMESTAMP NOT NULL,
    body TEXT NOT NULL,
    source TEXT,                 -- NULL = user-entered, 'import' = from xlsx import
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);
```

- `occurred_at` is naive UTC text (matches the project's timestamp convention).
- `body` is required and non-empty (composer disables submit on blank).
- `source` lets Phase 2 and the importer distinguish provenance and keeps re-import
  idempotent (see Importer below).

### Checkbox timestamps on `daily_entries`

Four nullable columns, one per checkbox:

```sql
ALTER TABLE daily_entries ADD COLUMN strengthening_done_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN stretches_morning_at  TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN stretches_night_at    TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN iced_at               TIMESTAMP;
```

On upsert, the service compares old vs new for each of the four booleans:
- `false → true`: set the matching `_at` to `now_utc()` (only if currently NULL).
- `→ false`: clear the matching `_at` to NULL.

**Known limitation:** ticking a box while viewing a *past* date stamps the current
wall-clock time, so its position on that past day's timeline is approximate. This is an
accepted edge case — boxes are nearly always ticked on the current day, and we keep the
interaction to a single tap rather than adding a time picker.

### Migration `0002_notes_log_and_checkbox_times.sql`

1. `CREATE TABLE notes (...)`.
2. Add the four `_at` columns.
3. Backfill notes from the legacy column:
   ```sql
   INSERT INTO notes (daily_entry_id, occurred_at, body, source)
   SELECT id, updated_at, notes, NULL
   FROM daily_entries
   WHERE notes IS NOT NULL AND trim(notes) <> '';
   ```
4. `ALTER TABLE daily_entries DROP COLUMN notes;` (SQLite 3.49 supports it; the column
   has no index/constraint).

Backfill of existing checkbox `_at` values is intentionally skipped — historical ticks
have no known time, so they simply won't appear on past timelines (they still show as
ticked in the checkbox card).

## Backend

### Models (`app/models/notes.py`)

- `NoteIn { body: str; occurred_at: datetime | None }`
- `NoteUpdate { body: str | None; occurred_at: datetime | None }`
- `Note { id, daily_entry_id, occurred_at, body, source, created_at, updated_at }`

### `DailyEntry` response (`app/models/entries.py`)

- **Remove** `notes: str | None` from `DailyEntry` and `DailyEntryUpsert`.
- **Add** to `DailyEntry`:
  - `strengthening_done_at`, `stretches_morning_at`, `stretches_night_at`, `iced_at`
    (`datetime | None`) — read straight from the row.
  - `notes: list[Note]` (ordered by `occurred_at`).
  - `timer_intervals: list[Interval]` (the day's intervals, for the timeline).
- `DailyEntrySummary` is unchanged (it never carried notes).

### Service (`app/services/notes.py` or extend `entries.py`)

- `add_note(db, user_id, entry_date, occurred_at, body) -> Note` — ensures the entry
  exists (reuse `ensure_entry`), stamps `now_utc()` when `occurred_at` is None, else
  `to_utc_naive(occurred_at)`. Mirrors `add_pain_event`.
- `update_note(db, user_id, note_id, body?, occurred_at?) -> Note | None` — ownership
  checked via the parent entry's `user_id` (same join pattern as `delete_pain_event`).
- `delete_note(db, user_id, note_id) -> bool`.

`get_entry` is extended to also load `notes` (ordered by `occurred_at`) and
`timer_intervals` (via `timer_service.day(...).intervals`, or an equivalent query), and
to surface the four `_at` columns (already returned by `SELECT *`).

`upsert_entry` gains the checkbox-stamping logic described above.

### Router (`app/routers/daily_entries.py`)

- `POST   /entries/{entry_date}/notes`  → `Note` (201)
- `PATCH  /notes/{note_id}`             → `Note`
- `DELETE /notes/{note_id}`             → 204

Patterns mirror the existing pain-event endpoints.

### Importer (`app/services/xlsx_import.py`)

The importer currently writes `daily_entries.notes`. After the column is dropped it must
write to the `notes` table instead:

- After upserting the day's entry, if there is parsed note text:
  - `DELETE FROM notes WHERE daily_entry_id = ? AND source = 'import'` (idempotent
    re-import), then
  - `INSERT` one note with `body = <parsed text>`, `source = 'import'`,
    `occurred_at = <entry_date at 12:00 UTC>` (a stable midday stamp; the source row has
    no real time).
- The `[tingling duration: ...]` tag behaviour is preserved inside that note body.

## Frontend

### API (`src/lib/api.ts`)

- `addNote(date, { body, occurred_at? })`
- `updateNote(id, { body?, occurred_at? })`
- `deleteNote(id)`

### Types (`src/lib/types.ts`)

- New `Note` interface mirroring the backend model.
- `DailyEntry`: drop `notes: string`; add `notes: Note[]`, `timer_intervals: Interval[]`,
  and the four nullable `*_at` string fields.

### Timeline builder (`src/lib/timeline.ts` + `timeline.test.ts`)

A pure function `buildTimeline(entry: DailyEntry): TimelineEvent[]` that flattens the four
sources into a single list sorted ascending by time:

```ts
type TimelineEvent =
  | { kind: 'timer'; at: string; posture: Posture; durationSeconds: number | null; running: boolean }
  | { kind: 'pain';  at: string; level: number | null; context: string | null }
  | { kind: 'check'; at: string; label: string }     // one per non-null *_at
  | { kind: 'note';  at: string; id: string; body: string };
```

Keeping this as a pure, unit-tested function fits the existing `lib` test culture
(`ratio.test.ts`, `time.test.ts`). Edge cases to test: empty day, null `_at`s excluded,
running interval flagged, stable sort on equal timestamps.

### Components

- **`NoteComposer.svelte`** — a textarea + "Add note" button. Submit calls `addNote`,
  clears the textarea, and reloads the entry. Includes a "🕑 now · change time" link that
  reveals a `<time>` input for back-dating, reusing `combineDateTimeToISO` /
  `defaultJabTime` exactly as the pain-jab form does. Submit is disabled when the body is
  blank.
- **`Timeline.svelte`** — renders `buildTimeline(entry)` as the rail (vertical line,
  colour-coded dots, cards). Colour map: timer = blue, pain = red, checkbox = green,
  note = purple. Note cards show inline **edit** (body + time → `updateNote`) and
  **remove** (`deleteNote`); other kinds are read-only. Timer rows show posture + duration
  (or "ongoing").

### `+page.svelte`

- Remove the `notes` state, the notes textarea, and `notes` from the `save()` payload.
- Render `<NoteComposer>` where the old notes card was, and `<Timeline {entry}>` as the
  final section of the page.
- Checkboxes keep their current `bind:checked` + `scheduleSave` wiring; the timestamps are
  handled server-side, and the timeline reads them from the reloaded entry.

## Data flow

1. User types a note → `NoteComposer` → `POST /entries/{date}/notes` → row inserted →
   entry reloaded → `Timeline` re-renders with the new note in place.
2. User ticks a checkbox → existing debounced `PUT /entries/{date}` → service stamps the
   `_at` → entry reloaded → checkbox event appears on the timeline.
3. Timeline always reflects the **selected** date (the page is date-navigable); past days
   render their stored intervals, jabs, notes, and any checkbox stamps.

## Error handling

- Note CRUD reuses the existing `request()` wrapper (401 → login bounce, errors thrown).
- Blank-body submit is prevented client-side; the backend also rejects empty `body`.
- Ownership on PATCH/DELETE is enforced via the parent-entry `user_id` join; a miss
  returns 404 (mirrors pain events).

## Testing

- **Backend:** extend `test_entries.py` — note create/list-ordering/update/delete,
  ownership isolation, checkbox `_at` set-on-tick and clear-on-untick, and the migration
  backfill (legacy note → one `notes` row; `notes` column gone). Importer test: imported
  note lands in `notes` with `source='import'` and re-import stays idempotent.
- **Frontend:** `timeline.test.ts` for `buildTimeline` (ordering, exclusions, running
  flag, empty day).

## Out-of-scope / future

- Phase 2 will query `notes`, `pain_events`, and `sit_stand_sessions` directly; no
  timeline API endpoint is needed for it.
- Per-checkbox back-dating, and backfilling historical checkbox times, are deliberately
  deferred.
