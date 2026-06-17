# Today Notes Log + Day Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Today page's single notes textarea with a streamlined timestamped note log, and add a combined day timeline (timer intervals, pain jabs, checkbox completions, notes).

**Architecture:** A new `notes` table (child of `daily_entries`, mirroring `pain_events`) makes notes discrete and queryable for Phase 2. Four nullable `*_at` columns on `daily_entries` stamp checkbox completions. The `DailyEntry` API response is enriched with `notes`, `timer_intervals`, and the checkbox timestamps; the frontend builds the timeline from that payload with a pure, unit-tested `buildTimeline()` function rendered as a vertical "rail".

**Tech Stack:** FastAPI + SQLite (backend, pytest), SvelteKit 5 + TypeScript (frontend, vitest).

**Spec:** `docs/superpowers/specs/2026-06-17-today-notes-log-and-timeline-design.md`

---

## File structure

**Backend**
- `backend/app/migrations/0002_notes_log_and_checkbox_times.sql` — create `notes`, add `*_at` columns, backfill, drop `notes` column.
- `backend/app/models/notes.py` — `NoteIn`, `NoteUpdate`, `Note`.
- `backend/app/models/entries.py` — drop legacy `notes: str`; add `notes`, `timer_intervals`, four `*_at` fields to `DailyEntry`.
- `backend/app/services/entries.py` — note CRUD + checkbox stamping + enriched `get_entry`.
- `backend/app/routers/daily_entries.py` — note endpoints.
- `backend/app/services/xlsx_import.py` — write imported notes into the `notes` table.
- `backend/tests/test_entries.py` — updated + new tests.

**Frontend**
- `frontend/src/lib/types.ts` — `Note` interface; updated `DailyEntry`.
- `frontend/src/lib/api.ts` — `addNote`, `updateNote`, `deleteNote`.
- `frontend/src/lib/timeline.ts` + `frontend/src/lib/timeline.test.ts` — `buildTimeline()`.
- `frontend/src/lib/components/NoteComposer.svelte` — composer.
- `frontend/src/lib/components/Timeline.svelte` — rail view.
- `frontend/src/routes/+page.svelte` — wire composer + timeline, remove old textarea.

---

## Task 1: Schema migration + retire legacy `notes` column

This is one atomic data-model change: after it, the backend test suite must be green again. It creates the `notes` table, adds checkbox timestamp columns, migrates existing note text, drops the old column, and updates every backend reference to that column.

**Files:**
- Create: `backend/app/migrations/0002_notes_log_and_checkbox_times.sql`
- Create: `backend/app/models/notes.py`
- Modify: `backend/app/models/entries.py`
- Modify: `backend/app/services/entries.py:21-36` (`_UPSERT_COLUMNS`), `:98-119` (`get_entry`)
- Modify: `backend/app/services/xlsx_import.py`
- Modify: `backend/tests/test_entries.py:12-22`
- Test: `backend/tests/test_entries.py`

- [ ] **Step 1: Write the migration file**

Create `backend/app/migrations/0002_notes_log_and_checkbox_times.sql`. The UUID default expression is copied verbatim from `0001_initial.sql` (other tables use the same one):

```sql
-- Timestamped note log + checkbox completion times.
-- Timestamps are naive UTC ISO-8601 text, matching the rest of the schema.

CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    occurred_at TIMESTAMP NOT NULL,
    body TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

ALTER TABLE daily_entries ADD COLUMN strengthening_done_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN stretches_morning_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN stretches_night_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN iced_at TIMESTAMP;

INSERT INTO notes (daily_entry_id, occurred_at, body, source)
SELECT id, updated_at, notes, NULL
FROM daily_entries
WHERE notes IS NOT NULL AND trim(notes) <> '';

ALTER TABLE daily_entries DROP COLUMN notes;
```

- [ ] **Step 2: Write the note models**

Create `backend/app/models/notes.py`:

```python
"""Note log schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    body: str = Field(min_length=1)
    occurred_at: datetime | None = None


class NoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1)
    occurred_at: datetime | None = None


class Note(BaseModel):
    id: UUID
    daily_entry_id: UUID
    occurred_at: datetime
    body: str
    source: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 3: Update `DailyEntry` / `DailyEntryUpsert` models**

In `backend/app/models/entries.py`:

Remove the `notes: str | None = None` line from **both** `DailyEntryUpsert` (line 41) and `DailyEntry` (line 78).

Add these fields to `DailyEntry` (after `iced: bool = False`):

```python
    strengthening_done_at: datetime | None = None
    stretches_morning_at: datetime | None = None
    stretches_night_at: datetime | None = None
    iced_at: datetime | None = None
```

And replace the trailing imports / rebuild block (currently lines 81-88) so `notes`, `timer_intervals`, and `session` all resolve. The file already has `from __future__ import annotations`, so string annotations resolve at `model_rebuild()`:

```python
    pain_events: list[PainEvent] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)
    session: SessionDetail | None = None
    timer_totals: PostureTotals = Field(default_factory=PostureTotals)
    timer_intervals: list[Interval] = Field(default_factory=list)


from app.models.notes import Note  # noqa: E402
from app.models.sessions import SessionDetail  # noqa: E402
from app.models.timer import Interval  # noqa: E402

DailyEntry.model_rebuild()
```

- [ ] **Step 4: Drop `notes` from the upsert path and enrich `get_entry`**

In `backend/app/services/entries.py`, remove `"notes",` from the `_UPSERT_COLUMNS` tuple (line 35).

Add imports near the top (`Note` and `Interval`):

```python
from app.models.entries import (
    DailyEntry,
    DailyEntrySummary,
    DailyEntryUpsert,
    Note,
    PainEvent,
    PostureTotals,
)
from app.models.timer import Interval
```

(`Note` is re-exported through `app.models.entries` after Step 3's import; importing it from there avoids a second module path. If your linter prefers, `from app.models.notes import Note` is equivalent.)

In `get_entry`, after the `events = [...]` block and before `session = ...`, add note and interval loading, and pass them to the `DailyEntry(...)` constructor:

```python
    notes = [
        Note(**n)
        for n in db.query(
            "SELECT * FROM notes WHERE daily_entry_id = ? ORDER BY occurred_at",
            [row["id"]],
        )
    ]
    intervals = [
        Interval(**i)
        for i in db.query(
            "SELECT * FROM sit_stand_sessions WHERE user_id = ? AND entry_date = ? "
            "ORDER BY started_at",
            [user_id, entry_date],
        )
    ]
    session = sessions_service.get_session_for_entry(db, row["id"])
    totals = timer_service.posture_totals(db, user_id, entry_date)
    return DailyEntry(
        **row,
        pain_events=events,
        notes=notes,
        session=session,
        timer_totals=PostureTotals(**totals),
        timer_intervals=intervals,
    )
```

- [ ] **Step 5: Update the xlsx importer to write into `notes`**

In `backend/app/services/xlsx_import.py`:

Ensure `datetime` is imported (add to the existing `from datetime import ...` line if absent): `from datetime import date, datetime`.

Remove `notes` from the INSERT column list, the `ON CONFLICT ... DO UPDATE SET` list, and the values list (the `notes,` value passed positionally). Specifically: delete `notes,` from line 159's column list, delete `notes = excluded.notes,` from the conflict block, and delete the `notes,` entry from the values list (around line 190).

Then, immediately after the existing `with db.cursor():` upsert block (after `db.execute(...)` for the entry), add:

```python
        if notes:
            entry_row = db.query_one(
                "SELECT id FROM daily_entries WHERE user_id = ? AND entry_date = ?",
                [user_id, d],
            )
            with db.cursor():
                db.execute(
                    "DELETE FROM notes WHERE daily_entry_id = ? AND source = 'import'",
                    [entry_row["id"]],
                )
                db.execute(
                    "INSERT INTO notes (daily_entry_id, occurred_at, body, source) "
                    "VALUES (?, ?, ?, 'import')",
                    [entry_row["id"], datetime(d.year, d.month, d.day, 12, 0), notes],
                )
```

- [ ] **Step 6: Fix the existing test that references `notes`**

In `backend/tests/test_entries.py`, update `test_upsert_creates_then_updates` (lines 12-22) to stop using the removed field:

```python
def test_upsert_creates_then_updates(db, user_id):
    d = date(2026, 6, 13)
    first = service.upsert_entry(db, user_id, d, DailyEntryUpsert(status="G", iced=True))
    assert first.status == "G"
    assert first.iced is True

    # A partial update leaves unspecified fields untouched.
    second = service.upsert_entry(db, user_id, d, DailyEntryUpsert(tingling_level=3))
    assert second.status == "G"
    assert second.tingling_level == Decimal("3")
    assert second.iced is True

    rows = db.query("SELECT * FROM daily_entries WHERE entry_date = ?", [d])
    assert len(rows) == 1
```

- [ ] **Step 7: Run the backend suite to verify green**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (all existing tests, including timer/import, still pass; no reference to `daily_entries.notes` remains).

- [ ] **Step 8: Commit**

```bash
git add backend/app/migrations/0002_notes_log_and_checkbox_times.sql backend/app/models/notes.py backend/app/models/entries.py backend/app/services/entries.py backend/app/services/xlsx_import.py backend/tests/test_entries.py
git commit -m "feat(notes): notes table + checkbox timestamps; retire legacy notes column"
```

---

## Task 2: Note CRUD service + endpoints

**Files:**
- Modify: `backend/app/services/entries.py` (add `add_note`, `update_note`, `delete_note`)
- Modify: `backend/app/routers/daily_entries.py`
- Test: `backend/tests/test_entries.py`

- [ ] **Step 1: Write failing service tests**

Append to `backend/tests/test_entries.py`:

```python
def test_add_note_and_list_ordering(db, user_id):
    d = date(2026, 6, 13)
    service.add_note(db, user_id, d, datetime(2026, 6, 13, 14, 0), "second")
    service.add_note(db, user_id, d, datetime(2026, 6, 13, 9, 0), "first")
    entry = service.get_entry(db, user_id, d)
    assert [n.body for n in entry.notes] == ["first", "second"]
    assert entry.notes[0].occurred_at == datetime(2026, 6, 13, 9, 0)


def test_add_note_defaults_timestamp_to_now(db, user_id):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, None, "stamp me")
    assert note.occurred_at is not None
    assert note.occurred_at.tzinfo is None


def test_update_note_body_and_time(db, user_id):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, datetime(2026, 6, 13, 9, 0), "old")
    updated = service.update_note(
        db, user_id, note.id, "new body", datetime(2026, 6, 13, 10, 30)
    )
    assert updated.body == "new body"
    assert updated.occurred_at == datetime(2026, 6, 13, 10, 30)


def test_delete_note(db, user_id):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, None, "bye")
    assert service.delete_note(db, user_id, note.id) is True
    entry = service.get_entry(db, user_id, d)
    assert entry.notes == []


def test_note_ownership_isolated(db, user_id, make_user):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, None, "mine")
    other = make_user()
    assert service.update_note(db, other, note.id, "hijack", None) is None
    assert service.delete_note(db, other, note.id) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -q -k note`
Expected: FAIL with `AttributeError: module ... has no attribute 'add_note'`.

- [ ] **Step 3: Implement the note service functions**

Append to `backend/app/services/entries.py` (reusing `ensure_entry`, `now_utc`, `to_utc_naive` already imported):

```python
def add_note(db: Database, user_id: UUID, entry_date: date, occurred_at, body: str) -> Note:
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
        created = db.query_one(
            "INSERT INTO notes (daily_entry_id, occurred_at, body) "
            "VALUES (?, ?, ?) RETURNING *",
            [entry_id, occurred, body],
        )
    assert created is not None
    return Note(**created)


def update_note(
    db: Database, user_id: UUID, note_id: UUID, body, occurred_at
) -> Note | None:
    owned = db.query_one(
        """
        SELECT n.id
        FROM notes n
        JOIN daily_entries d ON d.id = n.daily_entry_id
        WHERE n.id = ? AND d.user_id = ?
        """,
        [note_id, user_id],
    )
    if not owned:
        return None
    sets: list[str] = []
    params: list[Any] = []
    if body is not None:
        sets.append("body = ?")
        params.append(body)
    if occurred_at is not None:
        sets.append("occurred_at = ?")
        params.append(to_utc_naive(occurred_at))
    sets.append("updated_at = ?")
    params.append(now_utc())
    updated = db.query_one(
        f"UPDATE notes SET {', '.join(sets)} WHERE id = ? RETURNING *",
        [*params, note_id],
    )
    return Note(**updated) if updated else None


def delete_note(db: Database, user_id: UUID, note_id: UUID) -> bool:
    owned = db.query_one(
        """
        SELECT n.id
        FROM notes n
        JOIN daily_entries d ON d.id = n.daily_entry_id
        WHERE n.id = ? AND d.user_id = ?
        """,
        [note_id, user_id],
    )
    if not owned:
        return False
    db.execute("DELETE FROM notes WHERE id = ?", [note_id])
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -q -k note`
Expected: PASS.

- [ ] **Step 5: Write a failing API test for the endpoints**

Append to `backend/tests/test_entries.py`:

```python
def test_api_note_crud(auth_client):
    created = auth_client.post(
        "/api/v1/entries/2026-06-13/notes", json={"body": "felt tightness"}
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    entry = auth_client.get("/api/v1/entries/2026-06-13").json()
    assert [n["body"] for n in entry["notes"]] == ["felt tightness"]

    patched = auth_client.patch(f"/api/v1/notes/{note_id}", json={"body": "eased"})
    assert patched.status_code == 200
    assert patched.json()["body"] == "eased"

    assert auth_client.delete(f"/api/v1/notes/{note_id}").status_code == 204

    blank = auth_client.post("/api/v1/entries/2026-06-13/notes", json={"body": ""})
    assert blank.status_code == 422
```

- [ ] **Step 6: Run it to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py::test_api_note_crud -q`
Expected: FAIL with 404/405 (routes not defined).

- [ ] **Step 7: Add the router endpoints**

In `backend/app/routers/daily_entries.py`, extend the imports:

```python
from app.models.notes import Note, NoteIn, NoteUpdate
```

Add after the existing pain-event endpoints:

```python
@router.post("/entries/{entry_date}/notes", response_model=Note, status_code=201)
def add_note(
    entry_date: date,
    data: NoteIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.add_note(db, user_id, entry_date, data.occurred_at, data.body)


@router.patch("/notes/{note_id}", response_model=Note)
def update_note(
    note_id: UUID,
    data: NoteUpdate,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    note = service.update_note(db, user_id, note_id, data.body, data.occurred_at)
    if note is None:
        raise HTTPException(404, "No such note")
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not service.delete_note(db, user_id, note_id):
        raise HTTPException(404, "No such note")
```

- [ ] **Step 8: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/entries.py backend/app/routers/daily_entries.py backend/tests/test_entries.py
git commit -m "feat(notes): note CRUD service and endpoints"
```

---

## Task 3: Stamp checkbox completion times on upsert

**Files:**
- Modify: `backend/app/services/entries.py` (`upsert_entry` and a new constant)
- Test: `backend/tests/test_entries.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_entries.py`:

```python
def test_checkbox_tick_stamps_time(db, user_id):
    d = date(2026, 6, 13)
    entry = service.upsert_entry(db, user_id, d, DailyEntryUpsert(iced=True))
    assert entry.iced_at is not None
    assert entry.iced_at.tzinfo is None


def test_checkbox_untick_clears_time(db, user_id):
    d = date(2026, 6, 13)
    service.upsert_entry(db, user_id, d, DailyEntryUpsert(strengthening_done=True))
    entry = service.upsert_entry(db, user_id, d, DailyEntryUpsert(strengthening_done=False))
    assert entry.strengthening_done_at is None


def test_checkbox_restamp_not_overwritten_when_unchanged(db, user_id):
    d = date(2026, 6, 13)
    first = service.upsert_entry(db, user_id, d, DailyEntryUpsert(iced=True))
    # An unrelated field changes; iced stays true and its stamp is preserved.
    second = service.upsert_entry(db, user_id, d, DailyEntryUpsert(iced=True, status="A"))
    assert second.iced_at == first.iced_at
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -q -k checkbox`
Expected: FAIL (`iced_at` is None because nothing stamps it).

- [ ] **Step 3: Implement stamping in `upsert_entry`**

In `backend/app/services/entries.py`, add a module-level constant near `_UPSERT_COLUMNS`:

```python
# Checkbox column -> its completion-timestamp column.
_CHECKBOX_AT = {
    "strengthening_done": "strengthening_done_at",
    "stretches_morning": "stretches_morning_at",
    "stretches_night": "stretches_night_at",
    "iced": "iced_at",
}
```

Replace the body of `upsert_entry` with:

```python
def upsert_entry(
    db: Database, user_id: UUID, entry_date: date, data: DailyEntryUpsert
) -> DailyEntry:
    fields = data.model_dump(exclude_unset=True)
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        existing = db.query_one("SELECT * FROM daily_entries WHERE id = ?", [entry_id])
        assert existing is not None
        now = now_utc()
        assignments: list[str] = []
        params: list[Any] = []
        for col in fields:
            if col in _UPSERT_COLUMNS:
                assignments.append(f"{col} = ?")
                params.append(fields[col])
        for col, at_col in _CHECKBOX_AT.items():
            if col in fields:
                if fields[col] and not existing[col]:
                    assignments.append(f"{at_col} = ?")
                    params.append(now)
                elif not fields[col]:
                    assignments.append(f"{at_col} = ?")
                    params.append(None)
        if assignments:
            db.execute(
                f"UPDATE daily_entries SET {', '.join(assignments)}, updated_at = ? "
                "WHERE id = ?",
                [*params, now, entry_id],
            )
    detail = get_entry(db, user_id, entry_date)
    assert detail is not None
    return detail
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -q -k checkbox`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/entries.py backend/tests/test_entries.py
git commit -m "feat(entries): stamp checkbox completion times on upsert"
```

---

## Task 4: Frontend types + API methods

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add the `Note` type and update `DailyEntry`**

In `frontend/src/lib/types.ts`, add after the `PainEvent` interface:

```typescript
export interface Note {
  id: string;
  daily_entry_id: string;
  occurred_at: string;
  body: string;
  source: string | null;
  created_at: string | null;
  updated_at: string | null;
}
```

In the `DailyEntry` interface, remove `notes: string | null;` and replace with:

```typescript
  strengthening_done_at: string | null;
  stretches_morning_at: string | null;
  stretches_night_at: string | null;
  iced_at: string | null;
  pain_events: PainEvent[];
  notes: Note[];
  session: SessionDetail | null;
  timer_totals: PostureTotals;
  timer_intervals: Interval[];
```

(Leave `SessionDetail.notes` untouched — that is strength-session notes, unrelated.)

- [ ] **Step 2: Add API methods and import the `Note` type**

In `frontend/src/lib/api.ts`, add `Note` to the type import block at the top, then add to the `api` object after `deletePainEvent`:

```typescript
  addNote: (date: string, data: { body: string; occurred_at?: string }) =>
    request<Note>(`/entries/${date}/notes`, { method: 'POST', body: JSON.stringify(data) }),
  updateNote: (id: string, data: { body?: string; occurred_at?: string }) =>
    request<Note>(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteNote: (id: string) => request(`/notes/${id}`, { method: 'DELETE' }),
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npm run check`
Expected: PASS (no type errors). Note: `+page.svelte` still references the removed `notes` string field — it is fixed in Task 8. If `check` reports errors only in `+page.svelte` about `notes`, that is expected at this point; proceed. (To keep this task self-contained green, you may run `npm run check` again after Task 8.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(api): Note type and note CRUD client methods"
```

---

## Task 5: `buildTimeline` pure function

**Files:**
- Create: `frontend/src/lib/timeline.ts`
- Test: `frontend/src/lib/timeline.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/timeline.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { buildTimeline } from './timeline';
import type { DailyEntry } from './types';

function entry(overrides: Partial<DailyEntry>): DailyEntry {
  return {
    id: 'e1',
    entry_date: '2026-06-13',
    status: null,
    strengthening_done: false,
    session_intensity: null,
    sharp_pain_episodes: 0,
    worst_pain: null,
    tingling_level: null,
    tingling_duration_minutes: null,
    stretches_morning: false,
    stretches_night: false,
    sitting_breaks: null,
    sleep_quality: null,
    iced: false,
    strengthening_done_at: null,
    stretches_morning_at: null,
    stretches_night_at: null,
    iced_at: null,
    pain_events: [],
    notes: [],
    session: null,
    timer_totals: { sitting: 0, standing: 0, lying: 0, walking: 0 },
    timer_intervals: [],
    ...overrides
  };
}

describe('buildTimeline', () => {
  it('returns [] for an empty day', () => {
    expect(buildTimeline(entry({}))).toEqual([]);
  });

  it('merges and sorts all sources ascending by time', () => {
    const events = buildTimeline(
      entry({
        stretches_morning_at: '2026-06-13T07:45:00',
        iced_at: '2026-06-13T20:00:00',
        pain_events: [
          { id: 'p1', daily_entry_id: 'e1', occurred_at: '2026-06-13T11:15:00', pain_level: 4, context: 'desk' }
        ],
        notes: [
          { id: 'n1', daily_entry_id: 'e1', occurred_at: '2026-06-13T14:20:00', body: 'tightness', source: null, created_at: null, updated_at: null }
        ],
        timer_intervals: [
          { id: 'i1', entry_date: '2026-06-13', posture: 'sitting', started_at: '2026-06-13T09:02:00', ended_at: '2026-06-13T10:20:00', duration_seconds: 4680, label: null }
        ]
      })
    );
    expect(events.map((e) => e.kind)).toEqual(['check', 'timer', 'pain', 'note', 'check']);
    expect(events.map((e) => e.at)).toEqual([
      '2026-06-13T07:45:00',
      '2026-06-13T09:02:00',
      '2026-06-13T11:15:00',
      '2026-06-13T14:20:00',
      '2026-06-13T20:00:00'
    ]);
  });

  it('flags a running interval and excludes null checkbox times', () => {
    const events = buildTimeline(
      entry({
        timer_intervals: [
          { id: 'i1', entry_date: '2026-06-13', posture: 'standing', started_at: '2026-06-13T09:00:00', ended_at: null, duration_seconds: null, label: null }
        ]
      })
    );
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ kind: 'timer', running: true });
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/lib/timeline.test.ts`
Expected: FAIL (`buildTimeline` not found).

- [ ] **Step 3: Implement `buildTimeline`**

Create `frontend/src/lib/timeline.ts`:

```typescript
// Flattens a DailyEntry's four event sources into a single chronological list.
// Pure and dependency-free so it is unit-testable. Timestamps are naive UTC
// ISO strings of uniform format, so lexical comparison orders them correctly.

import type { DailyEntry, Posture } from './types';

export type TimelineEvent =
  | { kind: 'timer'; at: string; posture: Posture; durationSeconds: number | null; running: boolean }
  | { kind: 'pain'; at: string; level: number | null; context: string | null }
  | { kind: 'check'; at: string; label: string }
  | { kind: 'note'; at: string; id: string; body: string };

const CHECKBOX_FIELDS: [keyof DailyEntry, string][] = [
  ['strengthening_done_at', 'Strengthening session'],
  ['stretches_morning_at', 'Stretches — morning'],
  ['stretches_night_at', 'Stretches — night'],
  ['iced_at', 'Iced piriformis']
];

export function buildTimeline(entry: DailyEntry): TimelineEvent[] {
  const events: TimelineEvent[] = [];

  for (const iv of entry.timer_intervals) {
    events.push({
      kind: 'timer',
      at: iv.started_at,
      posture: iv.posture,
      durationSeconds: iv.duration_seconds,
      running: iv.ended_at == null
    });
  }

  for (const p of entry.pain_events) {
    events.push({ kind: 'pain', at: p.occurred_at, level: p.pain_level, context: p.context });
  }

  for (const [field, label] of CHECKBOX_FIELDS) {
    const at = entry[field] as string | null;
    if (at) events.push({ kind: 'check', at, label });
  }

  for (const n of entry.notes) {
    events.push({ kind: 'note', at: n.occurred_at, id: n.id, body: n.body });
  }

  return events.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/lib/timeline.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/timeline.ts frontend/src/lib/timeline.test.ts
git commit -m "feat(timeline): buildTimeline merges day events chronologically"
```

---

## Task 6: NoteComposer component

**Files:**
- Create: `frontend/src/lib/components/NoteComposer.svelte`

- [ ] **Step 1: Write the component**

Create `frontend/src/lib/components/NoteComposer.svelte`. It mirrors the pain-jab time pattern (`defaultJabTime` / `combineDateTimeToISO`) and calls back to the parent to reload after submit:

```svelte
<script lang="ts">
  import { api } from '$lib/api';
  import { combineDateTimeToISO, defaultJabTime, todayISO } from '$lib/time';

  let { date, onAdded }: { date: string; onAdded: () => void } = $props();

  let body = $state('');
  let timeOpen = $state(false);
  let time = $state('');
  let submitting = $state(false);
  const defaultTime = $derived(defaultJabTime(date));

  async function submit() {
    const text = body.trim();
    if (!text || submitting) return;
    submitting = true;
    try {
      const sendTime = timeOpen || date !== todayISO();
      const hhmm = time || defaultTime;
      await api.addNote(date, {
        body: text,
        occurred_at: sendTime ? combineDateTimeToISO(date, hhmm) : undefined
      });
      body = '';
      time = '';
      timeOpen = false;
      onAdded();
    } finally {
      submitting = false;
    }
  }
</script>

<div class="card">
  <label for="note-body">Add a note</label>
  <textarea
    id="note-body"
    bind:value={body}
    placeholder="What's happening? Pain, activity, what helped…"
    rows="3"
  ></textarea>
  <div class="note-actions">
    {#if timeOpen}
      <span class="time">
        <label for="note-time">Time</label>
        <input id="note-time" type="time" bind:value={time} />
      </span>
    {:else}
      <button
        class="link"
        onclick={() => {
          time = defaultTime;
          timeOpen = true;
        }}>🕑 {defaultTime} · change time</button
      >
    {/if}
    <button class="status-G" onclick={submit} disabled={!body.trim() || submitting}>
      Add note
    </button>
  </div>
</div>

<style>
  textarea {
    width: 100%;
    box-sizing: border-box;
    margin-top: 0.4rem;
  }
  .note-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-top: 0.6rem;
  }
  .time {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .time label {
    margin: 0;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
</style>
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run check`
Expected: no new errors in `NoteComposer.svelte` (pre-existing `+page.svelte` notes error still allowed until Task 8).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/NoteComposer.svelte
git commit -m "feat(notes): NoteComposer component"
```

---

## Task 7: Timeline component

**Files:**
- Create: `frontend/src/lib/components/Timeline.svelte`

- [ ] **Step 1: Write the component**

Create `frontend/src/lib/components/Timeline.svelte`. It renders `buildTimeline(entry)` as the rail; note rows support inline edit + remove:

```svelte
<script lang="ts">
  import { api } from '$lib/api';
  import { buildTimeline, type TimelineEvent } from '$lib/timeline';
  import { combineDateTimeToISO, formatMinutesish, POSTURE_LABEL } from '$lib/time';
  import type { DailyEntry } from '$lib/types';

  let { entry, date, onChanged }: { entry: DailyEntry; date: string; onChanged: () => void } =
    $props();

  const events = $derived(buildTimeline(entry));

  let editingId = $state<string | null>(null);
  let editBody = $state('');
  let editTime = $state('');

  function fmtTime(iso: string): string {
    return new Date(iso + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  const POSTURE_ICON: Record<string, string> = {
    sitting: '🪑',
    standing: '🧍',
    lying: '🛏️',
    walking: '🚶'
  };

  function dotClass(kind: TimelineEvent['kind']): string {
    return `dot-${kind}`;
  }

  function startEdit(ev: Extract<TimelineEvent, { kind: 'note' }>) {
    editingId = ev.id;
    editBody = ev.body;
    const d = new Date(ev.at + 'Z');
    editTime = `${d.getHours().toString().padStart(2, '0')}:${d
      .getMinutes()
      .toString()
      .padStart(2, '0')}`;
  }

  async function saveEdit(id: string) {
    await api.updateNote(id, {
      body: editBody.trim(),
      occurred_at: combineDateTimeToISO(date, editTime)
    });
    editingId = null;
    onChanged();
  }

  async function removeNote(id: string) {
    await api.deleteNote(id);
    onChanged();
  }
</script>

<div class="card">
  <h3 class="tl-title">Timeline</h3>
  {#if events.length === 0}
    <p class="muted small">Nothing logged yet today.</p>
  {:else}
    <div class="rail">
      {#each events as ev}
        <div class="rail-item">
          <span class="rail-dot {dotClass(ev.kind)}"></span>
          <div class="rail-card">
            {#if ev.kind === 'timer'}
              <div class="rail-top">
                <span>{POSTURE_ICON[ev.posture]} {POSTURE_LABEL[ev.posture]}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
              <div class="rail-sub">
                {ev.running ? 'ongoing' : formatMinutesish(ev.durationSeconds ?? 0)}
              </div>
            {:else if ev.kind === 'pain'}
              <div class="rail-top">
                <span>⚡ Pain jab{ev.level != null ? ` · level ${ev.level}` : ''}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
              {#if ev.context}<div class="rail-sub">{ev.context}</div>{/if}
            {:else if ev.kind === 'check'}
              <div class="rail-top">
                <span>✓ {ev.label}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
            {:else if ev.kind === 'note'}
              {#if editingId === ev.id}
                <textarea bind:value={editBody} rows="2"></textarea>
                <div class="edit-row">
                  <input type="time" bind:value={editTime} />
                  <span>
                    <button class="link" onclick={() => (editingId = null)}>cancel</button>
                    <button class="link" onclick={() => saveEdit(ev.id)}>save</button>
                  </span>
                </div>
              {:else}
                <div class="rail-top">
                  <span>✎ Note</span>
                  <span class="rail-time">{fmtTime(ev.at)}</span>
                </div>
                <div class="rail-sub">{ev.body}</div>
                <div class="note-edit">
                  <button class="link" onclick={() => startEdit(ev)}>edit</button>
                  <button class="link" onclick={() => removeNote(ev.id)}>remove</button>
                </div>
              {/if}
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tl-title {
    margin: 0 0 0.9rem;
    font-size: 1rem;
  }
  .rail {
    position: relative;
    padding-left: 1.4rem;
  }
  .rail::before {
    content: '';
    position: absolute;
    left: 0.42rem;
    top: 0.3rem;
    bottom: 0.3rem;
    width: 2px;
    background: var(--border);
  }
  .rail-item {
    position: relative;
    padding: 0.4rem 0 0.55rem;
  }
  .rail-dot {
    position: absolute;
    left: -1.16rem;
    top: 0.6rem;
    width: 0.62rem;
    height: 0.62rem;
    border-radius: 50%;
    border: 2px solid var(--bg, #fff);
  }
  .dot-timer {
    background: #5b8fb0;
  }
  .dot-pain {
    background: #c0563f;
  }
  .dot-check {
    background: #6a9a5b;
  }
  .dot-note {
    background: #9a7bb5;
  }
  .rail-card {
    background: var(--card-inner, #fff);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 0.5rem 0.65rem;
  }
  .rail-top {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    font-size: 0.85rem;
  }
  .rail-time {
    color: var(--text-muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .rail-sub {
    color: var(--text-muted);
    font-size: 0.8rem;
    margin-top: 0.15rem;
  }
  .note-edit,
  .edit-row {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 0.35rem;
  }
  .edit-row {
    justify-content: space-between;
    align-items: center;
  }
  textarea {
    width: 100%;
    box-sizing: border-box;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.8rem;
  }
</style>
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run check`
Expected: no new errors in `Timeline.svelte`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/Timeline.svelte
git commit -m "feat(timeline): Timeline rail component with inline note edit/remove"
```

---

## Task 8: Wire composer + timeline into the Today page

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Remove the legacy notes state and payload**

In `frontend/src/routes/+page.svelte`:

- Delete `let notes = $state('');` (line 33).
- Delete `notes = entry?.notes ?? '';` in `load()` (line 59).
- Delete `notes: notes || null` from the `save()` payload object (line 88) — also remove the trailing comma on the preceding `sitting_breaks` line so the object stays valid.

- [ ] **Step 2: Import the new components**

Add to the import block near the top:

```typescript
  import NoteComposer from '$lib/components/NoteComposer.svelte';
  import Timeline from '$lib/components/Timeline.svelte';
```

- [ ] **Step 3: Replace the notes card and add the timeline**

Replace the notes `<div class="card">` block (lines 273-281, the `<label>Notes</label>` + `<textarea>`) with:

```svelte
<NoteComposer {date} onAdded={() => load(date)} />
```

Then, after the totals card (the last `<div class="card totals">...</div>`), add:

```svelte
{#if entry}
  <Timeline {entry} {date} onChanged={() => load(date)} />
{/if}
```

- [ ] **Step 4: Type-check and run the full frontend test + lint**

Run: `cd frontend && npm run check && npx vitest run`
Expected: PASS, no type errors (the earlier `+page.svelte` notes error is now resolved).

- [ ] **Step 5: Manual verification**

Start backend and frontend (per repo README / docker-compose dev), then:
- Type a note, click **Add note** → it clears and appears in the timeline at the current time.
- Tick **Iced piriformis** → a green checkbox event appears on the timeline.
- Log a pain jab and run a timer interval → both appear, sorted by time.
- Edit and remove a note from the timeline → changes persist after a reload.
- Switch to a previous date → its stored events render; the composer's "change time" defaults to 12:00.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(today): replace notes textarea with note log + day timeline"
```

---

## Self-review notes (for the implementer)

- **Spec coverage:** notes table (T1), checkbox `_at` (T1/T3), migration + backfill + drop (T1), note CRUD + endpoints (T2), enriched `DailyEntry` (T1/T4), importer rewrite (T1), timeline builder (T5), composer (T6), rail with edit/remove + back-date (T6/T7), page wiring (T8), tests (T1/T2/T3/T5/T8). All spec sections map to a task.
- **Type consistency:** `buildTimeline` / `TimelineEvent` are defined in T5 and consumed unchanged in T7; `Note` fields match between backend model (T1) and frontend type (T4); `add_note(db, user_id, entry_date, occurred_at, body)` argument order is identical in service (T2), tests (T2), and router (T2).
- **Known limitation (documented in spec):** ticking a checkbox while viewing a past date stamps the current time; acceptable edge case, no back-date UI for checkboxes.
