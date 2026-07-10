# Exercises Add-Flow & Weekly Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the exercises page build a session by adding exercises one at a time (prefilled from each exercise's last log), and render AI-drafted markdown on the weekly page's Key observations & Next steps fields.

**Architecture:** Backend adds one fan-out endpoint returning the most recent log per exercise. The exercises Svelte page starts empty and grows an ordered "added" list via a dropdown+Add picker. The weekly Svelte page shows each notes field as rendered markdown by default (reusing the existing `renderMarkdown()` util) with a per-field Edit toggle.

**Tech Stack:** FastAPI + SQLite (backend, pytest), SvelteKit 5 runes + TypeScript (frontend, vitest / svelte-check).

## Global Constraints

- Backend queries are always user-scoped via the `exercise_logs → strength_sessions → daily_entries.user_id` join. Never trust a client-supplied user id.
- Prefer a single fan-out method/endpoint over N per-target calls (repo rule 6).
- LLM/markdown output is untrusted: render only through `renderMarkdown()` (marked + DOMPurify), never raw `{@html}` of model text.
- Svelte 5 runes syntax (`$state`, `$derived`), matching the existing files.
- Run backend tests from `backend/` with `pytest`; frontend checks from `frontend/` with `npm run check` and `npm run test`.

---

### Task 1: Backend `last_logs` endpoint

**Files:**
- Modify: `backend/app/services/sessions.py` (add `last_logs` after `exercise_progression`, ~line 211)
- Modify: `backend/app/routers/exercises.py` (add `GET /exercises/last-logs`)
- Test: `backend/tests/test_last_logs.py` (create)

**Interfaces:**
- Consumes: existing `create_session(db, user_id, entry_id, SessionIn)`, `entries_service.ensure_entry(db, user_id, date)`, `db` and `user_id` pytest fixtures.
- Produces: `sessions.last_logs(db, user_id) -> dict[str, dict]` mapping stringified `exercise_id` → `{sets, reps, hold_seconds, weight_kg, difficulty, nerve_response, modification}` for that exercise's most recent log. Route `GET /exercises/last-logs` returns the same JSON object.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_last_logs.py`:

```python
"""Most-recent-log-per-exercise lookup used to prefill the add-exercise flow."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.sessions import ExerciseLogIn, SessionIn
from app.services import entries as entries_service
from app.services import sessions as service


def _exercise_id(db, user_id, name: str) -> str:
    row = db.query_one(
        "SELECT id FROM exercises WHERE user_id = ? AND name = ?", [user_id, name]
    )
    return str(row["id"])


def _add_session(db, user_id, day: date, logs: list[ExerciseLogIn], performed: datetime):
    entry_id = entries_service.ensure_entry(db, user_id, day)
    service.create_session(
        db, user_id, entry_id, SessionIn(performed_at=performed, intensity=5, logs=logs)
    )


def test_last_logs_returns_most_recent_per_exercise(db, user_id):
    from uuid import UUID

    # Two seeded exercises; log the first on two days, the second once.
    names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 2", [user_id])]
    a = _exercise_id(db, user_id, names[0])
    b = _exercise_id(db, user_id, names[1])

    _add_session(db, user_id, date(2026, 6, 1),
                 [ExerciseLogIn(exercise_id=UUID(a), sets=2, reps=8)],
                 datetime(2026, 6, 1, 9, tzinfo=timezone.utc))
    _add_session(db, user_id, date(2026, 6, 8),
                 [ExerciseLogIn(exercise_id=UUID(a), sets=3, reps=12),
                  ExerciseLogIn(exercise_id=UUID(b), hold_seconds=30)],
                 datetime(2026, 6, 8, 9, tzinfo=timezone.utc))

    result = service.last_logs(db, user_id)

    assert result[a]["sets"] == 3      # most recent, not the 2-set older one
    assert result[a]["reps"] == 12
    assert result[b]["hold_seconds"] == 30


def test_last_logs_omits_never_logged_and_is_user_scoped(db, user_id, make_user):
    names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 1", [user_id])]
    from uuid import UUID
    a = _exercise_id(db, user_id, names[0])

    # A second seeded user logs their own exercise; must not leak into user_id's result.
    other_user_id = make_user()
    other_names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 1", [other_user_id])]
    other_a = _exercise_id(db, other_user_id, other_names[0])
    _add_session(db, other_user_id, date(2026, 6, 1),
                 [ExerciseLogIn(exercise_id=UUID(other_a), sets=9)],
                 datetime(2026, 6, 1, 9, tzinfo=timezone.utc))

    result = service.last_logs(db, user_id)
    assert a not in result          # user_id logged nothing
    assert other_a not in result    # other user's log never leaks
```

The `make_user` factory fixture (in `conftest.py`) creates an additional seeded user; each seeded user gets their own exercise catalogue.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_last_logs.py -v`
Expected: FAIL with `AttributeError: module 'app.services.sessions' has no attribute 'last_logs'`.

- [ ] **Step 3: Implement the service function**

Append to `backend/app/services/sessions.py`:

```python
def last_logs(db: Database, user_id: UUID) -> dict[str, dict]:
    """Most recent log per exercise for the user, to prefill new session rows."""
    rows = db.query(
        """
        SELECT exercise_id, sets, reps, hold_seconds, weight_kg,
               difficulty, nerve_response, modification
        FROM (
            SELECT el.*,
                   ROW_NUMBER() OVER (PARTITION BY el.exercise_id
                                      ORDER BY s.performed_at DESC) AS rn
            FROM exercise_logs el
            JOIN strength_sessions s ON s.id = el.session_id
            JOIN daily_entries d     ON d.id = s.daily_entry_id
            WHERE d.user_id = ?
        ) t
        WHERE rn = 1
        """,
        [user_id],
    )
    out: dict[str, dict] = {}
    for r in rows:
        eid = str(r.pop("exercise_id"))
        out[eid] = r
    return out
```

- [ ] **Step 4: Add the route**

In `backend/app/routers/exercises.py`, add (import `sessions as sessions_service` at top with the other imports; place the route function above `patch_exercise` so the literal `/exercises/last-logs` path is registered clearly):

```python
from app.services import sessions as sessions_service


@router.get("/exercises/last-logs")
def last_logs(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return sessions_service.last_logs(db, user_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_last_logs.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Run the full backend suite (guard against regressions)**

Run: `cd backend && pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/sessions.py backend/app/routers/exercises.py backend/tests/test_last_logs.py
git commit -m "feat(sessions): last-logs endpoint for per-exercise prefill"
```

---

### Task 2: Exercises page — add-as-you-go

**Files:**
- Modify: `frontend/src/lib/api.ts` (add `lastLogs`)
- Modify: `frontend/src/routes/exercises/+page.svelte` (script + "Log session" card markup + styles)

**Interfaces:**
- Consumes: `GET /exercises/last-logs` from Task 1; existing `api.listExercises()`, `api.createSession()`, `ExerciseLog` type (`{ exercise_id, sets, reps, hold_seconds, weight_kg, difficulty, nerve_response, modification }`, all nullable).
- Produces: none (leaf UI).

- [ ] **Step 1: Add the API client method**

In `frontend/src/lib/api.ts`, directly after the `progression:` entry (~line 131), add:

```ts
  lastLogs: () => request<Record<string, Partial<ExerciseLog>>>('/exercises/last-logs'),
```

`ExerciseLog` is already imported in this file (used by `createSession`); if not, add it to the type import.

- [ ] **Step 2: Rework the page script**

In `frontend/src/routes/exercises/+page.svelte`, replace the state + `load()` + `toggleSessionInstance`/`saveSession` region (lines ~9–86) so it uses an ordered `added` list and per-exercise prefill. Replace these specific pieces:

Replace the `included` declaration:

```ts
  let rows = $state<Record<string, ExerciseLog>>({});
  let included = $state<Record<string, boolean>>({});
```

with:

```ts
  let rows = $state<Record<string, ExerciseLog>>({});
  let added = $state<string[]>([]);
  let lastLogs = $state<Record<string, Partial<ExerciseLog>>>({});
  let toAdd = $state('');
```

Replace `load()` (lines ~44–61) with:

```ts
  async function load() {
    exercises = (await api.listExercises()).filter((e) => e.active);
    lastLogs = await api.lastLogs();
    // Fresh slate every time: no prefilled exercises, intensity, notes, or tags.
    rows = {};
    added = [];
    toAdd = '';
    intensity = null;
    sessionNotes = '';
    sessionInstanceIds = [];
  }
```

Add an `addExerciseToSession` helper (near `blankRow`):

```ts
  function addExerciseToSession(id: string) {
    if (!id || added.includes(id)) return;
    rows[id] = { ...blankRow(id), ...(lastLogs[id] ?? {}) };
    added = [...added, id];
    toAdd = '';
  }

  function removeFromSession(id: string) {
    added = added.filter((x) => x !== id);
    delete rows[id];
  }

  function exerciseName(id: string): string {
    return exercises.find((e) => e.id === id)?.name ?? '';
  }

  const availableToAdd = $derived(exercises.filter((e) => !added.includes(e.id)));
```

Replace `saveSession()`'s first line (line ~71):

```ts
    const logs = exercises.filter((e) => included[e.id]).map((e) => rows[e.id]);
```

with:

```ts
    const logs = added.map((id) => rows[id]);
```

- [ ] **Step 3: Rework the "Log session" card markup**

Replace the intro paragraph and the `{#each exercises as e}` block (lines ~138–192) with a picker + an added-list keyed on `added`:

```svelte
  <h3 style="margin-top: 0">Log session</h3>
  <p class="muted small">Add each exercise as you do it — inputs prefill from the last time you logged it.</p>
  {#if availableToAdd.length}
    <div class="row picker">
      <select bind:value={toAdd} style="flex: 1">
        <option value="">Choose an exercise…</option>
        {#each availableToAdd as e}<option value={e.id}>{e.name}</option>{/each}
      </select>
      <button onclick={() => addExerciseToSession(toAdd)} disabled={!toAdd}>+ Add</button>
    </div>
  {:else}
    <p class="muted small">All exercises added.</p>
  {/if}
  <div class="rows">
    {#each added as id (id)}
      {@const name = exerciseName(id)}
      <div class="exrow on">
        <div class="exhead">
          <span class="exname">{name}</span>
          <button class="link" onclick={() => removeFromSession(id)}>✕ remove</button>
        </div>
        <div class="inputs">
          <span><label>Sets</label><input type="number" bind:value={rows[id].sets} /></span>
          {#if isTimeBased(name)}
            <span><label>Hold (s)</label><input type="number" bind:value={rows[id].hold_seconds} /></span>
          {:else}
            <span><label>Reps</label><input type="number" bind:value={rows[id].reps} /></span>
          {/if}
          <span><label>Weight (kg)</label><input type="number" step="0.5" bind:value={rows[id].weight_kg} /></span>
          <span><label>Difficulty</label><input type="number" min="1" max="10" step="0.5" bind:value={rows[id].difficulty} /></span>
          <span class="wide"><label>Nerve response</label><input bind:value={rows[id].nerve_response} placeholder="e.g. slight twinge 2nd set" /></span>
          <span class="wide"><label>Modification</label><input bind:value={rows[id].modification} placeholder="e.g. heel elevation" /></span>
        </div>
      </div>
    {/each}
  </div>
```

Leave the Session notes field, pain-instance chips, Save button, and message unchanged below this block.

- [ ] **Step 4: Add styles for the new header/picker**

In the `<style>` block, add (the existing `.exname` rule sets font-weight/color; keep it, these additions cover the new row header layout):

```css
  .exhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .picker {
    margin-bottom: 0.75rem;
  }
```

`.exname` no longer wraps a checkbox; that's fine — the existing rule still styles the name text.

- [ ] **Step 5: Typecheck and lint**

Run: `cd frontend && npm run check && npm run lint`
Expected: no errors. (If `npm run lint` reports formatting, run `npm run format` and re-run.)

- [ ] **Step 6: Manual verification**

Run: `cd frontend && npm run dev` (backend running separately). In the browser on `/exercises`: page loads with no exercise rows; pick one from the dropdown → Add → row appears prefilled from its last log (blank for a never-logged exercise); ✕ remove works; Save persists only the added rows. Stop the dev server when done.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/routes/exercises/+page.svelte
git commit -m "feat(exercises): add-as-you-go session logging with per-exercise prefill"
```

---

### Task 3: Weekly page — render markdown with per-field edit toggle

**Files:**
- Modify: `frontend/src/routes/weekly/+page.svelte` (script + Key observations / Next steps fields + styles)

**Interfaces:**
- Consumes: existing `renderMarkdown` from `$lib/markdown`; existing `editObs`, `editNext`, `select()`, `draftWithAi()`, `save()`.
- Produces: none (leaf UI).

- [ ] **Step 1: Import the markdown renderer and add edit-state**

At the top of the `<script>` in `frontend/src/routes/weekly/+page.svelte`, add to the imports:

```ts
  import { renderMarkdown } from '$lib/markdown';
```

Add state alongside the other `$state` declarations:

```ts
  let editingObs = $state(false);
  let editingNext = $state(false);
```

- [ ] **Step 2: Reset edit-state on week select and after drafting**

In `select(w)` (after the existing assignments, before `message = ''`), add:

```ts
    editingObs = false;
    editingNext = false;
```

In `draftWithAi()`, in the `try` block after setting `editObs`/`editNext`, add so the formatted draft shows immediately:

```ts
      editingObs = false;
      editingNext = false;
```

- [ ] **Step 3: Replace the Key observations field**

Replace the Key observations `<div class="field">` (lines ~148–151) with a render/edit toggle:

```svelte
    <div class="field">
      <div class="fieldhead">
        <label>Key observations</label>
        {#if editObs && !editingObs}
          <button class="link" onclick={() => (editingObs = true)}>✎ Edit</button>
        {:else if editingObs}
          <button class="link" onclick={() => (editingObs = false)}>Done</button>
        {/if}
      </div>
      {#if editObs && !editingObs}
        <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
        <div class="markdown rendered">{@html renderMarkdown(editObs)}</div>
      {:else}
        <textarea bind:value={editObs} rows="6" placeholder="What stood out this week…"></textarea>
      {/if}
    </div>
```

- [ ] **Step 4: Replace the Next steps field**

Replace the Next steps `<div class="field">` (lines ~152–155) similarly:

```svelte
    <div class="field">
      <div class="fieldhead">
        <label>Next steps</label>
        {#if editNext && !editingNext}
          <button class="link" onclick={() => (editingNext = true)}>✎ Edit</button>
        {:else if editingNext}
          <button class="link" onclick={() => (editingNext = false)}>Done</button>
        {/if}
      </div>
      {#if editNext && !editingNext}
        <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
        <div class="markdown rendered">{@html renderMarkdown(editNext)}</div>
      {:else}
        <textarea bind:value={editNext} rows="4" placeholder="Plan for the upcoming week…"></textarea>
      {/if}
    </div>
```

- [ ] **Step 5: Add scoped markdown + header styles**

Append to the `<style>` block (mirrors the chat page's markdown rules, scoped here):

```css
  .fieldhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
  .rendered {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.5rem 0.75rem;
    background: var(--surface-2);
  }
  .markdown :global(> :first-child) {
    margin-top: 0;
  }
  .markdown :global(> :last-child) {
    margin-bottom: 0;
  }
  .markdown :global(h1),
  .markdown :global(h2),
  .markdown :global(h3) {
    margin: 0.6rem 0 0.3rem;
    line-height: 1.25;
  }
  .markdown :global(p),
  .markdown :global(ul),
  .markdown :global(ol) {
    margin: 0.4rem 0;
  }
  .markdown :global(ul),
  .markdown :global(ol) {
    padding-left: 1.25rem;
  }
  .markdown :global(li) {
    margin: 0.15rem 0;
  }
```

- [ ] **Step 6: Typecheck and lint**

Run: `cd frontend && npm run check && npm run lint`
Expected: no errors. (Run `npm run format` first if lint flags formatting.)

- [ ] **Step 7: Manual verification**

Run: `cd frontend && npm run dev`. On `/weekly`: select a week that already has notes → observations/next-steps show formatted markdown; ✎ Edit → raw textarea; Done → rendered again; ✨ Draft with AI (with a model configured) → both fields show the formatted draft; Save persists and stays rendered; an empty field shows the textarea directly.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/weekly/+page.svelte
git commit -m "feat(weekly): render AI-drafted markdown with per-field edit toggle"
```

---

## Self-Review Notes

- **Spec coverage:** Change 1 add-flow → Task 2; per-exercise prefill + fan-out endpoint → Task 1 + Task 2 Step 1–2; blank slate for intensity/notes/tags → Task 2 Step 2 `load()`. Change 2 render-on-view + per-field toggle + draft-leaves-rendered + empty-shows-textarea + scoped CSS → Task 3. Out-of-scope items untouched.
- **Placeholders:** none — all steps carry concrete code/commands.
- **Type consistency:** `lastLogs` typed `Record<string, Partial<ExerciseLog>>` in both api.ts and the page; service returns `dict[str, dict]` keyed by stringified UUID matching the frontend string keys; `added: string[]` used consistently in state, markup, and `saveSession`.
