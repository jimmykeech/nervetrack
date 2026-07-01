# Records page — patient profile, conditions, documents, LLM context

**Status:** Design approved, pending implementation plan
**Date:** 2026-07-01
**Builds on:** PR #11 (pain instances) and PR #12 / `feat/phase2-ai` (Phase 2 AI).
This feature branches from `feat/phase2-ai` because it extends the LLM context
plumbing added there.

## 1. Goal

A new **Records** page that consolidates the user's medical context in one place:

1. **Patient background** — a profile that sits outside any single condition
   (date of birth, sex, height, weight, lifestyle, medical history).
2. **Conditions** — the PR #11 pain instances, now richly editable here: a
   details narrative plus a dated notes log, and attachable documents. Records
   becomes the home for condition editing (moved out of Settings).
3. **Documents** — supporting files (medical reports / imaging) attachable at the
   profile level or to a specific condition, stored for download.

All of this feeds the Phase 2 LLM so chats and weekly drafts are grounded in the
patient's full context. Documents contribute their **title + the user's own
notes/summary** to the model — the binary is never parsed (no OCR/PDF/vision).

## 2. Page structure

`/records` route, new nav item, three stacked sections:

- **Patient background** — an editable form: structured basics (DOB, sex,
  height, weight) + free-text `lifestyle` and `medical_history`.
- **Conditions** — each pain instance as an expandable card: edit name / body
  region / details inline, append dated notes, attach / download / delete
  documents. This is the home for condition editing.
- **General documents** — profile-level attachments not tied to one condition.

The pain-instances editor is **removed from the Settings page** (moved, not
duplicated). The PR #11 mandatory first-login onboarding modal is unaffected.

## 3. Data model (new migrations, per-user)

All new tables scope to `user_id` and follow existing conventions (UUID PK
default, `TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))`, naive UTC).

**`patient_profile`** — one row per user:

```
patient_profile(
  user_id         PK / FK -> users,
  dob             DATE,
  sex             TEXT,
  height_cm       DECIMAL(5,1),
  weight_kg       DECIMAL(5,1),
  lifestyle       TEXT,
  medical_history TEXT,
  updated_at      TIMESTAMP
)
```

**`pain_instances`** — no schema change. The existing `background` column is
reused as the condition **Details** narrative and surfaced/edited on Records.

**`condition_notes`** — the dated notes log per condition (mirrors the daily
`notes` table):

```
condition_notes(
  id          PK,
  instance_id FK -> pain_instances (ON DELETE CASCADE),
  user_id     FK -> users,
  occurred_at TIMESTAMP,
  body        TEXT NOT NULL,
  created_at  TIMESTAMP
)
```

**`documents`**:

```
documents(
  id          PK,
  user_id     FK -> users,
  owner_type  TEXT,        -- 'profile' | 'condition'
  instance_id FK -> pain_instances (nullable; set when owner_type='condition',
                                     ON DELETE CASCADE),
  title       TEXT NOT NULL,
  notes       TEXT,        -- the user's summary; this is what the LLM sees
  filename    TEXT,
  mime_type   TEXT,
  size_bytes  INTEGER,
  content     BLOB,        -- file bytes; on the /data volume, Litestream-backed
  created_at  TIMESTAMP
)
```

Storing bytes in SQLite keeps the single-volume + Litestream backup story intact
and works fully offline.

## 4. Backend API

New routers `records` (profile + condition notes) and `documents`; condition
name/region/details editing reuses the PR #11 `PATCH /pain-instances/{id}`.

**Profile**
- `GET /profile` → profile (returns an empty/default shape if unset).
- `PUT /profile` → upsert.

**Condition details + notes**
- `GET /pain-instances/{id}` → the condition plus its notes and its documents
  (metadata only).
- `POST /pain-instances/{id}/notes` → add a dated note.
- `PATCH /condition-notes/{note_id}` → edit a note (own resource path, distinct
  from the daily-`notes` routes).
- `DELETE /condition-notes/{note_id}` → delete a note.

**Documents**
- `POST /documents` — multipart: `file` + `title` + optional `notes` +
  `owner_type` + optional `instance_id`. Guards: allowed mime types
  (pdf / png / jpeg / heic / plain text / common office docs) and a size cap
  (20 MB). `instance_id` is validated to belong to the user when
  `owner_type='condition'`.
- `GET /documents` — metadata list (no bytes); optional `instance_id` filter.
- `GET /documents/{id}/download` — streams the bytes with the stored
  `mime_type` / `filename`.
- `PATCH /documents/{id}` — edit `title` / `notes`.
- `DELETE /documents/{id}`.

All endpoints are `user_id`-scoped via the existing `current_user` dependency.

## 5. LLM context integration

Chosen approach: **always-inject the core, tools for the rest.**

- `llm.py` stays DB-free. A new context builder — `records_context(db, user_id)`
  in a small service — returns a compact text block: the patient background plus
  each active condition's name + details. The **AI router** computes this string
  and passes it (as `extra_context`) to `llm.stream_chat` and `llm.draft_weekly`,
  which append it to the system prompt. Every chat and every weekly draft
  therefore always carries the patient's background and condition summaries.
- Two new on-demand, `user_id`-scoped tools in `ai_tools.py`:
  - `get_condition_notes(instance_id)` → the dated notes log for a condition.
  - `list_documents()` → each document's `title`, `notes` (user summary),
    `owner_type`, condition name (if any), and `filename` — never the bytes.

`stream_chat` / `draft_weekly` signatures gain an optional
`extra_context: str = ""` parameter; when present it is concatenated after
`SYSTEM_PROMPT`. This preserves the existing Phase 2 tests (default empty).

## 6. Frontend

- New `/records` route + nav item, three sections per §2.
  - **Background**: a form bound to the profile; Save via `PUT /profile`.
  - **Conditions**: expandable cards; inline edit of name/region/details
    (`PATCH /pain-instances/{id}`), a notes log with add/edit/delete, and a
    documents sub-list with upload (`FormData`, like the xlsx import),
    download, and delete.
  - **General documents**: the `owner_type='profile'` list with the same
    upload/download/delete controls.
- `api.ts` gains profile, condition-notes, and document methods. Document upload
  posts `FormData`; download opens `/api/v1/documents/{id}/download`.
- A small `records` store (Svelte 5 runes) holds the profile, conditions with
  their notes/documents, and general documents.
- The pain-instances card is removed from `settings/+page.svelte`.

## 7. Testing

**Backend (pytest):**
- Profile upsert round-trip + empty default.
- Condition-notes add/edit/delete + per-user isolation + cascade on condition
  delete.
- Document upload → list (no bytes) → download (bytes + mime) → delete; size and
  mime-type rejection; cross-user isolation; `owner_type='condition'` validates
  instance ownership.
- `records_context` builder output includes profile + condition details.
- `get_condition_notes` / `list_documents` tools are `user_id`-scoped and never
  return bytes.
- Existing Phase 2 tests still pass with the new optional `extra_context` param.

**Frontend (vitest):**
- Profile form save path; a documents-list store test.

## 8. Out of scope (YAGNI)

- Parsing/OCR/vision over document contents (only the user's title + notes reach
  the LLM).
- Document versioning, folders, or sharing.
- Many-to-many document↔condition tagging (each document has one owner).
- Structured medication/allergy lists (captured as free text under
  `medical_history` for now).
