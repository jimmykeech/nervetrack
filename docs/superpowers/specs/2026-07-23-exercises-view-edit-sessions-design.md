# View & edit logged sessions on the exercise page

**Date:** 2026-07-23
**Status:** Approved

## Goal

On the exercise page, let the user see the strengthening session(s) already
logged for the selected day, edit any of them, and delete any of them. Today the
page only supports logging a **new** session — changing the date fetches nothing
and the page always starts from a fresh slate.

## Scope

- A **"Logged sessions"** section at the top of the exercise page listing the
  sessions logged on the selected day. It renders only when at least one session
  exists for that day.
- **Edit** loads the chosen session back into the existing "Log session" box,
  which switches from create-mode to edit-mode; saving **updates** that session.
- **Delete** removes a session (with a confirm prompt).
- Days can have **multiple** sessions; each is listed and edited/deleted
  independently.

Out of scope: moving a session to a different day, and any bulk operations.

## Backend

The update path already exists (`PUT /sessions/{id}` →
`service.update_session`). Two endpoints are new.

### 1. `GET /entries/{date}/sessions` → `list[SessionDetail]`

- Returns every session on that day's daily entry, ordered by `performed_at`.
- Returns `[]` when the day has no entry or no sessions — **no 404**.
- New service function `list_sessions_for_entry(db, daily_entry_id)` (parallel to
  the existing single-session `get_session_for_entry`), each row hydrated via the
  existing `_hydrate`. The router resolves the date → entry without creating one
  (do not call `ensure_entry`; a missing entry yields `[]`).

### 2. `DELETE /sessions/{session_id}` → 204

- Owner check via the existing `_owned_session`; 404 if not found/owned.
- Delete the session and cascade its `exercise_logs` and `session_instances`.
- **Re-sync the daily-entry mirror** after deletion:
  - If sessions remain on the entry: set `session_intensity` to the latest
    remaining session's intensity (leave `strengthening_done = TRUE`).
  - If none remain: set `strengthening_done = FALSE, session_intensity = NULL`.
  - Always bump `updated_at`.

### 3. `PUT /sessions/{id}` (existing, unchanged)

Used as-is for edits. It preserves the session's `performed_at` when none is
supplied and does not reassign the daily entry, so an edited session stays on its
original day.

## Frontend

All changes are in `frontend/src/routes/exercises/+page.svelte` plus two client
methods in `frontend/src/lib/api.ts`.

### API client (`api.ts`)

- `sessionsForDate(date)` → `GET /entries/${date}/sessions`, returns
  `SessionDetail[]`.
- `deleteSession(id)` → `DELETE /sessions/${id}`.
- `updateSession(id, data)` already exists and is reused.

### "Logged sessions" card (new, top of page)

Renders only when `loggedSessions.length > 0`. One row per session showing:

- time of day (from `performed_at`) and `intensity`;
- the exercise names (from each `log.exercise_name`);
- notes, if present;
- an **Edit** and a **Delete** button.

### Reactive fetch

- New state `loggedSessions: SessionDetail[]`.
- A `$effect` on `date` calls `sessionsForDate(date)` and populates
  `loggedSessions`; this also covers initial mount. Switching the date picker
  refreshes the list.

### Edit mode

- New state `editingId: string | null`.
- **Edit** populates the existing Log session box from the session — `rows`,
  `added`, `intensity`, `sessionNotes`, `sessionInstanceIds` — and sets
  `editingId`.
- Edit-mode affordances on the Log session box (chosen option):
  - heading "Log session" → **"Edit session"**;
  - save button "Save session" → **"Update session"**;
  - an **accent border** on the box;
  - a **"Cancel edit"** link that resets to a fresh create slate.
- `saveSession()` branches:
  `editingId ? updateSession(editingId, …) : createSession(date, …)`.
- After any save or delete: refresh `loggedSessions` and reset to a fresh create
  slate. Deleting the session currently being edited also exits edit mode.

### Delete

- `deleteSession(id)` behind a `confirm()`, then refresh `loggedSessions`.

## Testing

- **Backend (pytest):**
  - `GET /entries/{date}/sessions`: empty day → `[]`; a day with multiple
    sessions returns them ordered by `performed_at`; scoping keeps another user's
    sessions out.
  - `DELETE /sessions/{id}`: owner scoping (404 for someone else's session);
    mirror re-sync when a session remains vs. when the last one is removed;
    cascade removes the session's logs and instance tags.
- **Frontend:** manual verification in the running app, matching the page's
  existing pattern (no component test harness on this page).
