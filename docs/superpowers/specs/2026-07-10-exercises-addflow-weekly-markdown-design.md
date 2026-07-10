# Design: Exercises add-as-you-go & Weekly markdown rendering

**Date:** 2026-07-10
**Status:** Approved (design), pending implementation plan

Two independent, self-contained UI changes to the NerveTrack site. They share
no code and can be built in either order.

---

## Change 1 — Exercises page: add exercises as you go

### Problem

`frontend/src/routes/exercises/+page.svelte` currently lists **every** active
exercise as a checkbox row and, on load, pre-checks and prefills the exercises
from the most recent session ("same as last time"). The user wants to start each
session from an empty slate and add exercises one at a time as they perform them.
When an exercise is added, its inputs should prefill from the **last time that
specific exercise was logged** (across any past session), or be blank if it has
never been logged.

### Chosen approach

"Dropdown + Add" (Approach A from brainstorming). The session starts empty; a
picker adds one exercise at a time into an "Added this session" list.

### Frontend — `frontend/src/routes/exercises/+page.svelte`

**Remove:**
- The prefill block inside `load()` (lines ~49–60) that reads `latestSession()`
  and sets `intensity`, `sessionInstanceIds`, `rows[...]`, and `included[...]`.
- The `included` map and the full-catalogue checkbox list in the "Log session"
  card.

**State changes:**
- Replace `included: Record<string, boolean>` with `added: string[]` — the
  ordered list of exercise ids added to the current session (insertion order).
- Keep `rows: Record<string, ExerciseLog>` keyed by exercise id, but only
  populate an entry when its exercise is added.
- Add `lastLogs: Record<string, Partial<ExerciseLog>>` — the most-recent logged
  values per exercise, fetched once on load (see backend).
- `intensity`, `sessionNotes`, and `sessionInstanceIds` start blank/empty every
  time (no prefill from the last session).

**`load()` becomes:**
1. `exercises = (await api.listExercises()).filter((e) => e.active)`.
2. `lastLogs = await api.lastLogs()`.
3. Do **not** prefill anything else; `added` starts `[]`.

**Picker UI (top of the "Log session" card):**
- A `<select>` whose options are active exercises **not yet in `added`**
  (plus a leading "Choose an exercise…" placeholder), and an **Add** button.
- On Add: append the chosen id to `added`; set
  `rows[id] = { ...blankRow(id), ...(lastLogs[id] ?? {}) }` so it prefills from
  that exercise's last values (or stays blank). Reset the select to placeholder.
- When every active exercise has been added, show a muted "All exercises added"
  note instead of the picker.

**Added list UI:**
- Iterate `added` (in order) rather than `exercises`. Each entry renders the
  existing expanded input row (sets / reps-or-hold / weight / difficulty /
  nerve response / modification), reusing current markup, styles, and the
  `isTimeBased(name)` reps-vs-hold logic.
- Each row gets a small **✕ remove** control that removes the id from `added`
  (and deletes `rows[id]`).
- Update the helper copy ("Prefilled from your last session…") to reflect the
  new flow, e.g. "Add each exercise as you do it — inputs prefill from the last
  time you logged it."

**Save:**
- `saveSession()` maps over `added` (preserving order) into `logs`, instead of
  filtering `exercises` by `included`. Everything else (POST to
  `/entries/{date}/session`, success message) is unchanged.

The Catalogue and Progression cards are untouched.

### Backend — new fan-out endpoint for last-logged values

A single endpoint returns the last log per exercise so the page never issues N
per-exercise calls (repository rule 6: prefer fan-out over loops).

- **Service** — `app/services/sessions.py`, new `last_logs(db, user_id)`:
  returns `dict[str, dict]` mapping `exercise_id` → the columns
  `sets, reps, hold_seconds, weight_kg, difficulty, nerve_response,
  modification` from that exercise's most recent log. Query uses a window
  function to pick the latest row per exercise, scoped to the user via the
  `exercise_logs → strength_sessions → daily_entries.user_id` join:

  ```sql
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
  ```

  Keys are stringified UUIDs so the JSON object round-trips to the frontend map.

- **Router** — `app/routers/exercises.py`, add
  `GET /exercises/last-logs` → `service.last_logs(db, user_id)`. Place this
  route so it is registered before any `/exercises/{id}`-style path that could
  otherwise capture `last-logs` (the current `{exercise_id}/progression` route
  lives in the sessions router, but keep the literal path defined explicitly to
  avoid collisions).

- **API client** — `frontend/src/lib/api.ts`, add
  `lastLogs: () => request<Record<string, Partial<ExerciseLog>>>('/exercises/last-logs')`.

### Tests (Change 1)

- Backend: extend `backend/tests/test_sessions.py` (or a new
  `test_last_logs.py`): with sessions on multiple dates, `last_logs` returns the
  most recent values per exercise; an exercise never logged is absent from the
  map; results are user-scoped (another user's logs never leak).

---

## Change 2 — Weekly page: render AI-drafted markdown

### Problem

`frontend/src/routes/weekly/+page.svelte` shows **Key observations** and
**Next steps** as plain `<textarea>`s. The "✨ Draft with AI" button
(`draftWithAi()`) fills them with markdown from the backend, but the user only
ever sees raw `**stars**` / `- dashes`. The user wants the formatted markdown
visible.

### Chosen approach

"Render when saved / not editing" (Approach C from brainstorming). Each field
shows rendered markdown by default and reveals its `<textarea>` on demand. Reuse
the existing `renderMarkdown()` util from `$lib/markdown` (marked + DOMPurify),
already used by the chat page — no backend change.

### Frontend — `frontend/src/routes/weekly/+page.svelte`

**State:**
- Add `editingObs = $state(false)` and `editingNext = $state(false)` — per-field
  edit toggles (independent, as confirmed).

**Per field (Key observations, Next steps):**
- **Rendered view (default):** a `<div class="markdown">` containing
  `{@html renderMarkdown(editObs)}` (resp. `editNext`), with the same
  eslint-disable comment used in chat noting DOMPurify sanitizes the HTML. A
  small **✎ Edit** button toggles `editingObs = true`.
- **Edit view:** the current `<textarea bind:value={editObs}>`, plus a **Done**
  button that sets `editingObs = false` (returns to rendered view). `Done` is a
  local view toggle only; persistence is still the card's existing **Save**
  button.
- **Empty state:** when the field value is empty, show the textarea directly
  (open for editing) rather than an empty rendered box — nothing to format yet.

**Interaction with existing buttons:**
- `select(w)` resets `editingObs`/`editingNext` to `false` so switching weeks
  lands on the rendered view.
- `draftWithAi()` sets `editObs`/`editNext` from the draft and leaves both fields
  in **rendered** view (`editingObs = editingNext = false`) so the formatting is
  immediately visible. The existing "Draft ready — review and Save." message is
  kept.
- `save()` is unchanged; after saving, fields remain in rendered view.

**Styling:**
- Add scoped markdown CSS mirroring the chat page's `.bubble.markdown :global(…)`
  rules (headings, `p`/`ul`/`ol` spacing, `li`, `code`, first/last-child margin
  reset), scoped here to `.markdown` within the weekly card, so lists and
  headings render tidily. Keep it visually consistent with chat.

### Tests (Change 2)

- No backend change. `frontend/src/lib/markdown.test.ts` already covers
  `renderMarkdown`; the weekly change is view wiring. Optionally add a component
  smoke test if the frontend has a harness for it — otherwise rely on manual
  verification (draft → rendered view shows formatting; Edit → raw textarea;
  Done → rendered again).

---

## Out of scope

- No change to the AI draft endpoint or prompt.
- No markdown editing toolbar / WYSIWYG — plain textarea editing, rendered
  preview only.
- No change to how sessions are stored or to the daily-entry mirroring.
- No change to intensity/notes semantics beyond no longer prefilling them.

## Verification

- Exercises: load page → empty session; Add an exercise → row appears prefilled
  from its last log (or blank if new); remove works; Save persists only added
  rows in order; a brand-new exercise adds blank.
- Weekly: select a week with saved markdown → rendered; Edit → textarea; Draft
  with AI → rendered draft; Save → persists and stays rendered.
