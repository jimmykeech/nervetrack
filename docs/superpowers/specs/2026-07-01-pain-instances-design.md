# Pain Instances — Design Spec

## Problem

NerveTrack currently hardcodes a single condition into the schema and UI: one
`worst_pain`, one `tingling_level`, one sharp-pain-episode counter per day.
Users recovering from more than one nerve issue at once (or wanting to
document background/context for their condition) have nowhere to record
that, and no way to say which issue a given pain jab or strengthening session
relates to.

This adds a **pain instance** concept: a per-user catalogue of "things I'm
tracking" (e.g. "Left sciatic / piriformis", "Right shoulder impingement"),
each with optional background notes, introduced via a mandatory first-login
setup popup and tied into the existing pain-jab and strengthening-session
logging on the Today page.

## Scope

**In scope:**
- `pain_instances` catalogue table + CRUD API (mirrors the existing
  `exercises` catalogue pattern).
- Many-to-many tagging of pain jabs and strengthening sessions with one or
  more instances.
- Mandatory first-login popup to create at least one instance.
- Settings page section to manage instances after first login (add, edit,
  retire).
- Tagging UI on the Today page for pain jabs and the session form.

**Out of scope (deferred to a later pass):**
- Per-instance breakdowns/filtering in History, Weekly, or Stats — those
  pages keep their current day-level aggregate views unchanged.
- Any change to day-level fields on `daily_entries` (`worst_pain`,
  `tingling_level`, `status`, etc.) — these remain untagged, whole-day
  aggregates across all instances.
- Tingling as a discrete taggable log (it stays a single day-level value).

## Data model

New migration `0004_pain_instances.sql`:

```sql
CREATE TABLE pain_instances (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    body_region TEXT,
    background TEXT,
    active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE TABLE pain_event_instances (
    pain_event_id UUID NOT NULL REFERENCES pain_events (id),
    instance_id UUID NOT NULL REFERENCES pain_instances (id),
    PRIMARY KEY (pain_event_id, instance_id)
);

CREATE TABLE session_instances (
    session_id UUID NOT NULL REFERENCES strength_sessions (id),
    instance_id UUID NOT NULL REFERENCES pain_instances (id),
    PRIMARY KEY (session_id, instance_id)
);
```

No changes to existing tables/columns. Purely additive.

## Backend API

New router `pain_instances.py`, modeled on `routers/exercises.py`:

- `GET /pain-instances` — list all (active + inactive), ordered by
  `sort_order, name`.
- `POST /pain-instances` — create `{name, body_region?, background?}`.
- `PATCH /pain-instances/{id}` — partial update: rename, edit background,
  toggle `active`, reorder.

Existing schemas gain an `instance_ids` field:

- `PainEventIn` / `PainEvent`: `instance_ids: list[UUID] = []`. Write path
  (`add_pain_event`) inserts the join rows in the same call; read path joins
  and returns tagged IDs (+ denormalized names, matching how `ExerciseLog`
  already denormalizes `exercise_name`).
- `SessionIn` / `SessionDetail`: same `instance_ids: list[UUID] = []`,
  handled by session create/update.

No changes to `DailyEntryUpsert` / `DailyEntry`.

Popup gating requires no new flag: the frontend treats an empty
`GET /pain-instances` result as "needs setup." Instance count is the single
source of truth, so there's nothing to get out of sync.

## First-login popup

- Rendered from `+layout.svelte`, after `auth.ready` and `auth.user` are set.
  Fetches `GET /pain-instances`; if the result is empty, renders a modal
  overlay on top of whatever route the user landed on (no redirect).
- Form: repeatable blocks of Name (required) / Body region (optional) /
  Background (optional textarea). "+ Add another pain issue" appends a
  blank block. "Done" is disabled until at least one block has a non-empty
  name.
- Submitting posts each filled block via `POST /pain-instances`, then closes
  the modal and refetches so the guard clears.
- No skip/dismiss affordance while the list is empty — this is mandatory,
  per product decision.
- One-time gate only: once ≥1 instance exists it never reappears. Managing
  instances afterward (add more, edit, retire) happens in a new "Pain
  Instances" section on the Settings page, reusing the same form component
  used by the popup.

## Today-page tagging UX

- **Pain jab mini-form** (`routes/+page.svelte`): a row of multi-select
  toggle chips, one per active pain instance, below Level/Context. Selecting
  none is allowed (untagged jab). Logged jab list items show tagged instance
  name(s) as small badges.
- **Strengthening session form** (`routes/exercises/+page.svelte`): the same
  chip row added once at the session level (not per-exercise-log), since
  intensity/notes/logs are already session-level.
- Active instances are fetched once (e.g. alongside the existing exercise
  catalogue fetch) and shared rather than re-fetched per component.

## Testing

- Backend: pytest coverage for `pain_instances` CRUD (create, patch,
  deactivate, uniqueness/ordering), and for tagging on
  `add_pain_event`/session create+update (join rows written and returned
  correctly, including the empty-tags case).
- Frontend: a component/store test for the first-login gating logic (popup
  shows iff instance list is empty; clears after creation) and for the
  "Done" button's enable condition (at least one non-empty name).
