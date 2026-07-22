# View & Edit Logged Sessions on the Exercise Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user view every strengthening session logged on the selected day, edit any of them, and delete any of them, from the exercise page.

**Architecture:** Two new backend endpoints (list sessions for a date; delete a session) plus the existing `PUT /sessions/{id}` for edits. The frontend gains a "Logged sessions" card that reactively fetches the day's sessions, and the existing "Log session" box gains a create-vs-edit mode.

**Tech Stack:** FastAPI + SQLite (backend, pytest), SvelteKit + Svelte 5 runes + TypeScript (frontend, svelte-check).

## Global Constraints

- Backend endpoints are user-scoped: session ownership is verified by joining `daily_entries.user_id` (use the existing `_owned_session` helper). Never trust a session/entry id without this check.
- Follow existing service patterns: mutations run inside `with db.cursor():`; SQL uses `?` placeholders; sessions are hydrated with the existing `_hydrate`.
- Router modules expose a module-level `router`; they are already auto-registered in `app/main.py` under the API prefix. No registration change is needed — `sessions.py` is already included.
- Frontend: Svelte 5 runes (`$state`, `$derived`, `$effect`). The `request` helper already maps HTTP 204 → `undefined`.
- `performed_at` is stored UTC-naive; convert to local for display with `utcNaiveToLocalInput` from `$lib/time`.

---

### Task 1: Backend — list sessions for a date

**Files:**
- Modify: `backend/app/services/sessions.py` (add `list_sessions_for_date`)
- Modify: `backend/app/routers/sessions.py` (add `GET /entries/{date}/sessions`)
- Test: `backend/tests/test_sessions.py`

**Interfaces:**
- Consumes: existing `_hydrate(db, session_row)`, `Database.query`, `Database.query_one`.
- Produces:
  - `service.list_sessions_for_date(db: Database, user_id: UUID, entry_date: date) -> list[SessionDetail]`
  - Route `GET /entries/{entry_date}/sessions` → `list[SessionDetail]`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_sessions.py`:

```python
from datetime import UTC, datetime


def test_list_sessions_for_date_empty_when_no_entry(db, user_id):
    assert service.list_sessions_for_date(db, user_id, date(2026, 6, 13)) == []


def test_list_sessions_for_date_orders_by_performed_at(db, user_id):
    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    service.create_session(
        db, user_id, entry_id,
        SessionIn(performed_at=datetime(2026, 6, 13, 18, 0, tzinfo=UTC), intensity=4),
    )
    service.create_session(
        db, user_id, entry_id,
        SessionIn(performed_at=datetime(2026, 6, 13, 9, 0, tzinfo=UTC), intensity=6),
    )
    result = service.list_sessions_for_date(db, user_id, date(2026, 6, 13))
    assert [float(s.intensity) for s in result] == [6.0, 4.0]  # 09:00 before 18:00


def test_list_sessions_for_date_is_user_scoped(db, user_id, make_user):
    other = make_user()
    other_entry = entries_service.ensure_entry(db, other, date(2026, 6, 13))
    service.create_session(db, other, other_entry, SessionIn(intensity=5))
    assert service.list_sessions_for_date(db, user_id, date(2026, 6, 13)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_sessions.py -k list_sessions_for_date -v`
Expected: FAIL with `AttributeError: module 'app.services.sessions' has no attribute 'list_sessions_for_date'`

- [ ] **Step 3: Write the service function**

Add to `backend/app/services/sessions.py` (after `get_session_for_entry`). Note `date` must be importable — add `from datetime import date` to the imports if absent:

```python
def list_sessions_for_date(
    db: Database, user_id: UUID, entry_date: date
) -> list[SessionDetail]:
    """All of the user's sessions on ``entry_date``, oldest first. Empty if none."""
    entry = db.query_one(
        "SELECT id FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, entry_date],
    )
    if not entry:
        return []
    rows = db.query(
        "SELECT * FROM strength_sessions WHERE daily_entry_id = ? ORDER BY performed_at",
        [entry["id"]],
    )
    return [_hydrate(db, row) for row in rows]
```

- [ ] **Step 4: Add the route**

Add to `backend/app/routers/sessions.py`:

```python
@router.get("/entries/{entry_date}/sessions", response_model=list[SessionDetail])
def list_sessions(
    entry_date: date,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.list_sessions_for_date(db, user_id, entry_date)
```

- [ ] **Step 5: Write a router-level test**

Add to `backend/tests/test_sessions.py`:

```python
def test_list_sessions_endpoint(auth_client, db, user_id):
    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    service.create_session(db, user_id, entry_id, SessionIn(intensity=5))
    resp = auth_client.get("/api/v1/entries/2026-06-13/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["intensity"] == "5"

    empty = auth_client.get("/api/v1/entries/2026-06-14/sessions")
    assert empty.status_code == 200
    assert empty.json() == []
```

Note: the API prefix is `/api/v1` (confirmed in `tests/test_entries.py`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_sessions.py -v`
Expected: PASS (all, including the new list tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/sessions.py backend/app/routers/sessions.py backend/tests/test_sessions.py
git commit -m "feat(sessions): list sessions for a date endpoint"
```

---

### Task 2: Backend — delete a session with daily-entry mirror re-sync

**Files:**
- Modify: `backend/app/services/sessions.py` (add `delete_session`)
- Modify: `backend/app/routers/sessions.py` (add `DELETE /sessions/{session_id}`)
- Test: `backend/tests/test_sessions.py`

**Interfaces:**
- Consumes: existing `_owned_session(db, user_id, session_id)`, `now_utc()` (already imported in the service).
- Produces:
  - `service.delete_session(db: Database, user_id: UUID, session_id: UUID) -> bool` (True if deleted, False if not found/owned).
  - Route `DELETE /sessions/{session_id}` → 204, 404 when missing.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_sessions.py`:

```python
def _entry_flags(db, entry_id):
    row = db.query_one(
        "SELECT strengthening_done, session_intensity FROM daily_entries WHERE id = ?",
        [entry_id],
    )
    return row["strengthening_done"], row["session_intensity"]


def test_delete_session_last_one_clears_mirror(db, user_id):
    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    created = service.create_session(db, user_id, entry_id, SessionIn(intensity=5))
    assert service.delete_session(db, user_id, created.id) is True
    assert service.get_session(db, user_id, created.id) is None
    done, intensity = _entry_flags(db, entry_id)
    assert done is False
    assert intensity is None


def test_delete_session_keeps_mirror_when_others_remain(db, user_id):
    from datetime import UTC, datetime

    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    first = service.create_session(
        db, user_id, entry_id,
        SessionIn(performed_at=datetime(2026, 6, 13, 9, 0, tzinfo=UTC), intensity=6),
    )
    service.create_session(
        db, user_id, entry_id,
        SessionIn(performed_at=datetime(2026, 6, 13, 18, 0, tzinfo=UTC), intensity=4),
    )
    assert service.delete_session(db, user_id, first.id) is True
    done, intensity = _entry_flags(db, entry_id)
    assert done is True
    assert float(intensity) == 4.0  # latest remaining session's intensity


def test_delete_session_rejects_unowned(db, user_id, make_user):
    other = make_user()
    other_entry = entries_service.ensure_entry(db, other, date(2026, 6, 13))
    created = service.create_session(db, other, other_entry, SessionIn(intensity=5))
    assert service.delete_session(db, user_id, created.id) is False
    # still there for its real owner
    assert service.get_session(db, other, created.id) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_sessions.py -k delete_session -v`
Expected: FAIL with `AttributeError: ... has no attribute 'delete_session'`

- [ ] **Step 3: Write the service function**

Add to `backend/app/services/sessions.py`:

```python
def delete_session(db: Database, user_id: UUID, session_id: UUID) -> bool:
    """Delete one of the user's sessions and re-sync the daily-entry mirror."""
    existing = _owned_session(db, user_id, session_id)
    if not existing:
        return False
    entry_id = existing["daily_entry_id"]
    with db.cursor():
        db.execute("DELETE FROM session_instances WHERE session_id = ?", [session_id])
        db.execute("DELETE FROM exercise_logs WHERE session_id = ?", [session_id])
        db.execute("DELETE FROM strength_sessions WHERE id = ?", [session_id])
        latest = db.query_one(
            "SELECT intensity FROM strength_sessions "
            "WHERE daily_entry_id = ? ORDER BY performed_at DESC LIMIT 1",
            [entry_id],
        )
        if latest:
            db.execute(
                "UPDATE daily_entries SET session_intensity = ?, updated_at = ? WHERE id = ?",
                [latest["intensity"], now_utc(), entry_id],
            )
        else:
            db.execute(
                "UPDATE daily_entries SET strengthening_done = FALSE, "
                "session_intensity = NULL, updated_at = ? WHERE id = ?",
                [now_utc(), entry_id],
            )
    return True
```

- [ ] **Step 4: Add the route**

Add to `backend/app/routers/sessions.py`:

```python
@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: UUID,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    if not service.delete_session(db, user_id, session_id):
        raise HTTPException(404, "No such session")
```

- [ ] **Step 5: Add a router-level test**

Add to `backend/tests/test_sessions.py`:

```python
def test_delete_session_endpoint(auth_client, db, user_id):
    from uuid import uuid4

    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    created = service.create_session(db, user_id, entry_id, SessionIn(intensity=5))
    resp = auth_client.delete(f"/api/v1/sessions/{created.id}")
    assert resp.status_code == 204
    assert service.get_session(db, user_id, created.id) is None

    missing = auth_client.delete(f"/api/v1/sessions/{uuid4()}")
    assert missing.status_code == 404
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_sessions.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/sessions.py backend/app/routers/sessions.py backend/tests/test_sessions.py
git commit -m "feat(sessions): delete session endpoint with entry mirror re-sync"
```

---

### Task 3: Frontend — API client methods

**Files:**
- Modify: `frontend/src/lib/api.ts:130` (after `updateSession`, in the "Exercises & sessions" block)

**Interfaces:**
- Consumes: existing `request<T>` helper, `SessionDetail` type (already imported).
- Produces:
  - `api.sessionsForDate(date: string) => Promise<SessionDetail[]>`
  - `api.deleteSession(id: string) => Promise<void>`

- [ ] **Step 1: Add the methods**

In `frontend/src/lib/api.ts`, immediately after the `updateSession` line:

```typescript
  sessionsForDate: (date: string) =>
    request<SessionDetail[]>(`/entries/${date}/sessions`),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: 'DELETE' }),
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run check`
Expected: no new errors referencing `api.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(exercises): api client for listing and deleting sessions"
```

---

### Task 4: Frontend — "Logged sessions" card with reactive fetch

**Files:**
- Modify: `frontend/src/routes/exercises/+page.svelte`

**Interfaces:**
- Consumes: `api.sessionsForDate`, `SessionDetail`, `utcNaiveToLocalInput` from `$lib/time`, existing `date` state.
- Produces: `loggedSessions` state and a `loadSessions()` function that Task 5 reuses after edits/deletes.

- [ ] **Step 1: Add state, import, and loader**

In `frontend/src/routes/exercises/+page.svelte`:

Extend the `$lib/time` import (line 5) to include the converter:

```typescript
  import { todayISO, utcNaiveToLocalInput } from '$lib/time';
```

Add state near the other session state (after `sessionInstanceIds`, ~line 19):

```typescript
  let loggedSessions = $state<SessionDetail[]>([]);
```

Add a loader and a reactive effect after the `load()` function (after ~line 56):

```typescript
  async function loadSessions() {
    loggedSessions = await api.sessionsForDate(date);
  }

  $effect(() => {
    // Re-fetch whenever the selected day changes (and on first run).
    date;
    loadSessions();
  });
```

Add a small display helper alongside `exerciseName` (~line 79):

```typescript
  function sessionTime(s: SessionDetail): string {
    return utcNaiveToLocalInput(s.performed_at).slice(11, 16); // HH:MM, local
  }

  function sessionExercises(s: SessionDetail): string {
    return s.logs.map((l) => l.exercise_name).filter(Boolean).join(', ');
  }
```

- [ ] **Step 2: Add the card markup**

Insert this card immediately after the session-meta card (after its closing `</div>`, before the `<div class="card">` that holds `<h3>Log session</h3>`, ~line 149):

```svelte
{#if loggedSessions.length}
  <div class="card">
    <h3 style="margin-top: 0">Logged sessions</h3>
    {#each loggedSessions as s (s.id)}
      <div class="logged">
        <div class="logged-head">
          <span class="logged-when">{sessionTime(s)}{#if s.intensity} · intensity {s.intensity}{/if}</span>
          <span class="logged-actions">
            <button class="link" onclick={() => editSession(s)}>Edit</button>
            <button class="link danger" onclick={() => removeSession(s)}>Delete</button>
          </span>
        </div>
        {#if sessionExercises(s)}<div class="muted small">{sessionExercises(s)}</div>{/if}
        {#if s.notes}<div class="muted small logged-notes">"{s.notes}"</div>{/if}
      </div>
    {/each}
  </div>
{/if}
```

`editSession` and `removeSession` are defined in Task 5; this step will not typecheck cleanly on its own — that is expected, Task 5 completes it. (If executing tasks strictly independently, add temporary stubs `function editSession(_s: SessionDetail) {}` and `function removeSession(_s: SessionDetail) {}` and replace them in Task 5.)

- [ ] **Step 3: Add styles**

Add to the `<style>` block (before the closing `</style>`):

```css
  .logged {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
  }
  .logged-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .logged-when {
    font-weight: 600;
    color: var(--text);
  }
  .logged-actions {
    display: flex;
    gap: 0.75rem;
  }
  .logged-notes {
    font-style: italic;
  }
  .link.danger {
    color: var(--danger, #c0392b);
  }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/exercises/+page.svelte
git commit -m "feat(exercises): logged-sessions card for the selected day"
```

---

### Task 5: Frontend — edit mode and delete wiring

**Files:**
- Modify: `frontend/src/routes/exercises/+page.svelte`

**Interfaces:**
- Consumes: `api.updateSession`, `api.deleteSession`, `loadSessions`, `loggedSessions`, `blankRow`, existing session-form state (`rows`, `added`, `intensity`, `sessionNotes`, `sessionInstanceIds`, `saved`, `message`).
- Produces: `editSession(s)`, `removeSession(s)`, `cancelEdit()`, `editingId` state; a branched `saveSession()`.

- [ ] **Step 1: Add editing state**

Add after `loggedSessions` (Task 4 state):

```typescript
  let editingId = $state<string | null>(null);
```

- [ ] **Step 2: Add edit / cancel / delete functions**

Add near `saveSession` (~line 92):

```typescript
  function editSession(s: SessionDetail) {
    editingId = s.id;
    added = s.logs.map((l) => l.exercise_id);
    rows = Object.fromEntries(
      s.logs.map((l) => [
        l.exercise_id,
        {
          exercise_id: l.exercise_id,
          sets: l.sets,
          reps: l.reps,
          hold_seconds: l.hold_seconds,
          weight_kg: l.weight_kg,
          difficulty: l.difficulty,
          nerve_response: l.nerve_response,
          modification: l.modification
        }
      ])
    );
    intensity = s.intensity;
    sessionNotes = s.notes ?? '';
    sessionInstanceIds = [...s.instance_ids];
    message = '';
  }

  function cancelEdit() {
    editingId = null;
    rows = {};
    added = [];
    intensity = null;
    sessionNotes = '';
    sessionInstanceIds = [];
    message = '';
  }

  async function removeSession(s: SessionDetail) {
    if (!confirm('Delete this logged session?')) return;
    await api.deleteSession(s.id);
    if (editingId === s.id) cancelEdit();
    await loadSessions();
  }
```

- [ ] **Step 3: Branch `saveSession` on edit mode**

Replace the existing `saveSession` body (~lines 83-92) with:

```typescript
  async function saveSession() {
    const logs = added.map((id) => rows[id]);
    const payload = {
      intensity,
      notes: sessionNotes || null,
      logs,
      instance_ids: sessionInstanceIds
    };
    if (editingId) {
      saved = await api.updateSession(editingId, payload);
      message = `Updated session with ${saved.logs.length} exercises.`;
    } else {
      saved = await api.createSession(date, payload);
      message = `Saved session with ${saved.logs.length} exercises.`;
    }
    editingId = null;
    rows = {};
    added = [];
    intensity = null;
    sessionNotes = '';
    sessionInstanceIds = [];
    await loadSessions();
  }
```

- [ ] **Step 4: Apply edit-mode affordances to the Log session box**

In the Log session card (`<div class="card">` containing `<h3>Log session</h3>`, ~line 150):

Add the edit-mode class to the card open tag:

```svelte
<div class="card" class:editing={editingId}>
```

Change the heading line to reflect mode and offer cancel:

```svelte
  <h3 style="margin-top: 0">
    {editingId ? 'Edit session' : 'Log session'}
    {#if editingId}<button class="link" onclick={cancelEdit} style="margin-left: 0.5rem">Cancel edit</button>{/if}
  </h3>
```

Change the save button label (~line 239):

```svelte
  <button class="status-G" onclick={saveSession}>{editingId ? 'Update session' : 'Save session'}</button>
```

- [ ] **Step 5: Add the editing accent style**

Add to the `<style>` block:

```css
  .card.editing {
    border: 1px solid var(--accent);
  }
```

If `.card` has no `border` normally and this looks off, use `outline: 1px solid var(--accent)` instead — verify visually in Step 7.

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npm run check`
Expected: no errors in `+page.svelte`.

- [ ] **Step 7: Manual verification**

Run the app (`docker-compose.dev.yml` or the project's usual dev command — check README) and verify against the running app:
1. Log a session for today → it appears in "Logged sessions".
2. Log a second session same day → both appear, ordered by time.
3. Click **Edit** on one → the box shows "Edit session", accent border, "Update session" button, prefilled rows/intensity/notes/tags. Change a value, **Update session** → the list reflects the change; box resets to create mode.
4. **Cancel edit** → box returns to a fresh create state.
5. Change the date picker to a day with no sessions → the card disappears; a day with sessions → it shows them.
6. **Delete** a session (confirm) → it disappears from the list.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/exercises/+page.svelte
git commit -m "feat(exercises): edit and delete logged sessions from the day view"
```

---

## Self-Review Notes

- **Spec coverage:** `GET /entries/{date}/sessions` (Task 1), `DELETE /sessions/{id}` + mirror re-sync (Task 2), reused `PUT` (Task 5 `saveSession`), Logged-sessions card + reactive fetch (Task 4), edit mode with heading/button/accent/cancel affordances (Task 5), delete with confirm (Task 5), API client methods (Task 3). All spec sections map to a task.
- **Type consistency:** `loadSessions`, `loggedSessions`, `editingId`, `editSession`, `removeSession`, `cancelEdit`, `sessionTime`, `sessionExercises` are used consistently across Tasks 4–5. Backend `list_sessions_for_date` / `delete_session` names match between service, router, and tests.
- **Cross-task note:** Task 4's card references `editSession`/`removeSession` defined in Task 5; if executing tasks in strict isolation, add the temporary stubs noted in Task 4 Step 2. When executing sequentially (recommended), do Task 4 then Task 5 and skip the stubs.
