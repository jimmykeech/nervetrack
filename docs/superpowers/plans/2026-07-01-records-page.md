# Records Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Records page with an editable patient-background profile, richly editable conditions (details + dated notes log + documents), document attachments stored as SQLite BLOBs, and always-inject the patient/condition context into the Phase 2 LLM chat and weekly drafts.

**Architecture:** New per-user tables (`patient_profile`, `condition_notes`, `documents`) behind focused service modules and two new routers (`records`, `documents`). A DB-free `records_context()` string is built in the AI router and appended to the LLM system prompt; two new read-only tools expose condition notes and document summaries. A new `/records` SvelteKit page hosts the profile form, condition cards, and document lists; condition editing is removed from Settings.

**Tech Stack:** FastAPI (Python 3.12), Pydantic v2, SQLite (WAL, BLOB storage); SvelteKit + Svelte 5 runes, TypeScript, Vitest. Builds on `feat/phase2-ai` (Phase 2 AI, PR #12).

## Global Constraints

- Python `requires-python = ">=3.12"`; ruff line-length 100; type hints throughout; Pydantic model per request/response.
- All new tables scope to `user_id`; all endpoints use the `current_user` + `db_dep` FastAPI dependencies. Data is never reachable across users.
- SQLite conventions: `UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6))))`, `TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))`, `user_id UUID NOT NULL REFERENCES users (id)`. Timestamps are naive UTC ISO-8601 text.
- Documents: file bytes stored in the `documents.content` BLOB column (Litestream-backed). Only the document's `title` + user `notes` ever reach the LLM — the binary is never parsed.
- Upload guards: max 20 MB; allowed mime types `application/pdf`, `image/png`, `image/jpeg`, `image/heic`, `text/plain`, `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
- The next migration number on `feat/phase2-ai` is `0007` (0001–0006 already exist).
- Backend tests use the `db` / `user_id` / `make_user` / `auth_client` fixtures in `backend/tests/conftest.py`. Run backend from `backend/` with `.venv/bin/pytest` and `.venv/bin/ruff`. Run frontend from `frontend/` with `npm run check`, `npm run test`, `npm run lint` (run `npm run format` before lint).
- LiteLLM is always mocked in tests; no live API calls.

---

## Task 1: Migration — records tables

**Files:**
- Create: `backend/app/migrations/0007_records.sql`
- Test: `backend/tests/test_records_migration.py`

**Interfaces:**
- Produces: tables `patient_profile`, `condition_notes`, `documents`.

- [ ] **Step 1: Write the migration**

Create `backend/app/migrations/0007_records.sql`:

```sql
-- Patient background that sits outside any single condition. One row per user.
CREATE TABLE patient_profile (
    user_id UUID PRIMARY KEY REFERENCES users (id),
    dob DATE,
    sex TEXT,
    height_cm DECIMAL(5, 1),
    weight_kg DECIMAL(5, 1),
    lifestyle TEXT,
    medical_history TEXT,
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

-- Dated notes log per condition (mirrors the daily notes table).
CREATE TABLE condition_notes (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    instance_id UUID NOT NULL REFERENCES pain_instances (id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users (id),
    occurred_at TIMESTAMP NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE INDEX idx_condition_notes_instance ON condition_notes (instance_id, occurred_at);

-- Supporting documents (medical reports/imaging). Bytes live in content;
-- owner_type is 'profile' (general) or 'condition' (instance_id set).
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    owner_type TEXT NOT NULL,
    instance_id UUID REFERENCES pain_instances (id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    notes TEXT,
    filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    content BLOB,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE INDEX idx_documents_user ON documents (user_id, owner_type);
CREATE INDEX idx_documents_instance ON documents (instance_id);
```

- [ ] **Step 2: Write the test**

Create `backend/tests/test_records_migration.py`:

```python
def test_records_tables_exist(db, user_id):
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"patient_profile", "condition_notes", "documents"} <= tables


def test_blob_round_trips(db, user_id):
    db.execute(
        "INSERT INTO documents (user_id, owner_type, title, content) VALUES (?, 'profile', 't', ?)",
        [user_id, b"\x89PNG\x00bytes"],
    )
    row = db.query_one("SELECT content FROM documents WHERE user_id = ?", [user_id])
    assert row["content"] == b"\x89PNG\x00bytes"
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_records_migration.py -v`
Expected: PASS (the `db` fixture runs `migrate()`).

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/0007_records.sql backend/tests/test_records_migration.py
git commit -m "feat(records): add patient_profile, condition_notes, documents tables"
```

---

## Task 2: Records Pydantic models

**Files:**
- Create: `backend/app/models/records.py`
- Test: `backend/tests/test_records_models.py`

**Interfaces:**
- Produces: `PatientProfile`, `PatientProfileIn`, `ConditionNoteIn`, `ConditionNoteUpdate`, `ConditionNote`, `DocumentMeta`, `DocumentPatch`, `ConditionDetail`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_records_models.py`:

```python
from decimal import Decimal

from app.models.records import DocumentMeta, PatientProfile


def test_profile_all_optional():
    p = PatientProfile()
    assert p.dob is None and p.height_cm is None


def test_profile_accepts_decimal():
    p = PatientProfile(height_cm=Decimal("178.0"), weight_kg=Decimal("74.5"))
    assert p.height_cm == Decimal("178.0")


def test_document_meta_has_no_content_field():
    fields = set(DocumentMeta.model_fields)
    assert "content" not in fields
    assert {"id", "owner_type", "title", "filename", "mime_type", "size_bytes"} <= fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_records_models.py -v`
Expected: FAIL (`ModuleNotFoundError: app.models.records`).

- [ ] **Step 3: Implement the models**

Create `backend/app/models/records.py`:

```python
"""Schemas for the Records feature: patient profile, condition notes, documents."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.pain_instances import PainInstance


class PatientProfile(BaseModel):
    dob: date | None = None
    sex: str | None = None
    height_cm: Decimal | None = None
    weight_kg: Decimal | None = None
    lifestyle: str | None = None
    medical_history: str | None = None


class PatientProfileIn(PatientProfile):
    """Same optional fields; used as the PUT body."""


class ConditionNoteIn(BaseModel):
    body: str = Field(min_length=1)
    occurred_at: datetime | None = None


class ConditionNoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1)
    occurred_at: datetime | None = None


class ConditionNote(BaseModel):
    id: UUID
    instance_id: UUID
    occurred_at: datetime
    body: str
    created_at: datetime | None = None


class DocumentMeta(BaseModel):
    id: UUID
    owner_type: str
    instance_id: UUID | None = None
    title: str
    notes: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    notes: str | None = None


class ConditionDetail(BaseModel):
    instance: PainInstance
    notes: list[ConditionNote] = []
    documents: list[DocumentMeta] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_records_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/records.py backend/tests/test_records_models.py
git commit -m "feat(records): add records Pydantic models"
```

---

## Task 3: Patient-profile service + endpoints

**Files:**
- Create: `backend/app/services/profile.py`
- Create: `backend/app/routers/records.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_profile.py`

**Interfaces:**
- Consumes: models from Task 2.
- Produces:
  - `profile.get_profile(db, user_id) -> PatientProfile`
  - `profile.save_profile(db, user_id, data: PatientProfileIn) -> PatientProfile`
  - Router endpoints `GET /profile`, `PUT /profile`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_profile.py`:

```python
def test_profile_empty_default(auth_client):
    r = auth_client.get("/api/v1/profile")
    assert r.status_code == 200
    assert r.json()["dob"] is None


def test_profile_upsert_round_trip(auth_client):
    r = auth_client.put("/api/v1/profile", json={
        "dob": "1991-04-01", "sex": "male", "height_cm": "178.0",
        "weight_kg": "74.5", "lifestyle": "desk job, runs 3x/wk",
        "medical_history": "appendectomy 2010",
    })
    assert r.status_code == 200
    got = auth_client.get("/api/v1/profile").json()
    assert got["sex"] == "male"
    assert got["lifestyle"].startswith("desk job")
    assert got["medical_history"] == "appendectomy 2010"


def test_profile_second_put_overwrites(auth_client):
    auth_client.put("/api/v1/profile", json={"sex": "male"})
    auth_client.put("/api/v1/profile", json={"sex": "female", "weight_kg": "70.0"})
    got = auth_client.get("/api/v1/profile").json()
    assert got["sex"] == "female"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_profile.py -v`
Expected: FAIL (404 — routes not registered).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/profile.py`:

```python
"""Patient background profile: one row per user."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.records import PatientProfile, PatientProfileIn

_FIELDS = ("dob", "sex", "height_cm", "weight_kg", "lifestyle", "medical_history")


def get_profile(db: Database, user_id: UUID) -> PatientProfile:
    row = db.query_one("SELECT * FROM patient_profile WHERE user_id = ?", [user_id])
    if row is None:
        return PatientProfile()
    return PatientProfile(**{k: row[k] for k in _FIELDS})


def save_profile(db: Database, user_id: UUID, data: PatientProfileIn) -> PatientProfile:
    with db.cursor():
        db.execute(
            """
            INSERT INTO patient_profile
                (user_id, dob, sex, height_cm, weight_kg, lifestyle, medical_history, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f','now'))
            ON CONFLICT (user_id) DO UPDATE SET
                dob = excluded.dob,
                sex = excluded.sex,
                height_cm = excluded.height_cm,
                weight_kg = excluded.weight_kg,
                lifestyle = excluded.lifestyle,
                medical_history = excluded.medical_history,
                updated_at = excluded.updated_at
            """,
            [user_id, data.dob, data.sex, data.height_cm, data.weight_kg,
             data.lifestyle, data.medical_history],
        )
    return get_profile(db, user_id)
```

- [ ] **Step 4: Implement the router**

Create `backend/app/routers/records.py`:

```python
"""Records endpoints: patient profile (condition notes + detail added later)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.deps import db_dep
from app.models.records import PatientProfile, PatientProfileIn
from app.services import profile as profile_service

router = APIRouter(tags=["records"])


@router.get("/profile", response_model=PatientProfile)
def get_profile(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return profile_service.get_profile(db, user_id)


@router.put("/profile", response_model=PatientProfile)
def put_profile(
    data: PatientProfileIn, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    return profile_service.save_profile(db, user_id, data)
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add `records` to the `from app.routers import (...)` block (alphabetically, after `pain_instances`) and to the `for module in (...)` registration tuple (add `records,` after `pain_instances,`).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_profile.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/profile.py backend/app/routers/records.py backend/app/main.py backend/tests/test_profile.py
git commit -m "feat(records): patient-profile service + GET/PUT /profile"
```

---

## Task 4: Condition-notes service + endpoints

**Files:**
- Create: `backend/app/services/condition_notes.py`
- Modify: `backend/app/routers/records.py`
- Test: `backend/tests/test_condition_notes.py`

**Interfaces:**
- Consumes: `pain_instances` service (for a seeded instance in tests).
- Produces:
  - `condition_notes.add_note(db, user_id, instance_id: UUID, occurred_at, body: str) -> ConditionNote` (raises `ValueError` if the instance is not the user's)
  - `condition_notes.list_notes(db, user_id, instance_id: UUID) -> list[ConditionNote]`
  - `condition_notes.update_note(db, user_id, note_id: UUID, body, occurred_at) -> ConditionNote | None`
  - `condition_notes.delete_note(db, user_id, note_id: UUID) -> bool`
  - Endpoints `POST /pain-instances/{instance_id}/notes`, `PATCH /condition-notes/{note_id}`, `DELETE /condition-notes/{note_id}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_condition_notes.py`:

```python
from app.models.pain_instances import PainInstanceCreate
from app.services import pain_instances as pi


def _instance(db, user_id, name="Left sciatic"):
    return pi.create_instance(db, user_id, PainInstanceCreate(name=name)).id


def test_add_list_update_delete(auth_client, db, user_id):
    iid = _instance(db, user_id)
    created = auth_client.post(f"/api/v1/pain-instances/{iid}/notes",
                               json={"body": "started physio"})
    assert created.status_code == 201
    note_id = created.json()["id"]

    listed = auth_client.get(f"/api/v1/pain-instances/{iid}").json()["notes"]
    assert [n["body"] for n in listed] == ["started physio"]

    upd = auth_client.patch(f"/api/v1/condition-notes/{note_id}", json={"body": "started PT"})
    assert upd.status_code == 200 and upd.json()["body"] == "started PT"

    assert auth_client.delete(f"/api/v1/condition-notes/{note_id}").status_code == 204


def test_note_on_foreign_instance_rejected(auth_client, db, user_id, make_user):
    other = make_user()
    foreign = _instance(db, other, name="theirs")
    r = auth_client.post(f"/api/v1/pain-instances/{foreign}/notes", json={"body": "x"})
    assert r.status_code == 404


def test_notes_cascade_on_instance_delete(db, user_id):
    iid = _instance(db, user_id)
    from app.services import condition_notes as cn
    cn.add_note(db, user_id, iid, None, "n1")
    with db.cursor():
        db.execute("DELETE FROM pain_instances WHERE id = ?", [iid])
    assert db.query("SELECT id FROM condition_notes WHERE instance_id = ?", [iid]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_condition_notes.py -v`
Expected: FAIL (`ModuleNotFoundError` / 404).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/condition_notes.py`:

```python
"""Dated notes log per condition (pain instance)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db import Database
from app.models.records import ConditionNote
from app.services.timeutil import now_utc, to_utc_naive


def _owns_instance(db: Database, user_id: UUID, instance_id: UUID) -> bool:
    return db.query_one(
        "SELECT 1 FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
    ) is not None


def _owns_note(db: Database, user_id: UUID, note_id: UUID) -> bool:
    return db.query_one(
        "SELECT 1 FROM condition_notes WHERE id = ? AND user_id = ?", [note_id, user_id]
    ) is not None


def add_note(
    db: Database, user_id: UUID, instance_id: UUID, occurred_at, body: str
) -> ConditionNote:
    if not _owns_instance(db, user_id, instance_id):
        raise ValueError("No such pain instance")
    occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
    with db.cursor():
        created = db.query_one(
            "INSERT INTO condition_notes (instance_id, user_id, occurred_at, body) "
            "VALUES (?, ?, ?, ?) RETURNING id, instance_id, occurred_at, body, created_at",
            [instance_id, user_id, occurred, body],
        )
    assert created is not None
    return ConditionNote(**created)


def list_notes(db: Database, user_id: UUID, instance_id: UUID) -> list[ConditionNote]:
    rows = db.query(
        "SELECT id, instance_id, occurred_at, body, created_at FROM condition_notes "
        "WHERE instance_id = ? AND user_id = ? ORDER BY occurred_at DESC",
        [instance_id, user_id],
    )
    return [ConditionNote(**r) for r in rows]


def update_note(
    db: Database, user_id: UUID, note_id: UUID, body, occurred_at
) -> ConditionNote | None:
    if not _owns_note(db, user_id, note_id):
        return None
    sets: list[str] = []
    params: list[Any] = []
    if body is not None:
        sets.append("body = ?")
        params.append(body)
    if occurred_at is not None:
        sets.append("occurred_at = ?")
        params.append(to_utc_naive(occurred_at))
    if sets:
        params.extend([note_id, user_id])
        with db.cursor():
            db.execute(
                f"UPDATE condition_notes SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                params,
            )
    row = db.query_one(
        "SELECT id, instance_id, occurred_at, body, created_at FROM condition_notes WHERE id = ?",
        [note_id],
    )
    return ConditionNote(**row) if row else None


def delete_note(db: Database, user_id: UUID, note_id: UUID) -> bool:
    if not _owns_note(db, user_id, note_id):
        return False
    with db.cursor():
        db.execute("DELETE FROM condition_notes WHERE id = ? AND user_id = ?", [note_id, user_id])
    return True
```

- [ ] **Step 4: Add the endpoints**

In `backend/app/routers/records.py`, extend the imports and add the note routes:

Update the imports block:

```python
from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.records import (
    ConditionNote,
    ConditionNoteIn,
    ConditionNoteUpdate,
    PatientProfile,
    PatientProfileIn,
)
from app.services import condition_notes as notes_service
from app.services import profile as profile_service
```

Append the routes:

```python
@router.post("/pain-instances/{instance_id}/notes", response_model=ConditionNote, status_code=201)
def add_condition_note(
    instance_id: UUID,
    data: ConditionNoteIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    try:
        return notes_service.add_note(db, user_id, instance_id, data.occurred_at, data.body)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/condition-notes/{note_id}", response_model=ConditionNote)
def update_condition_note(
    note_id: UUID,
    data: ConditionNoteUpdate,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    note = notes_service.update_note(db, user_id, note_id, data.body, data.occurred_at)
    if note is None:
        raise HTTPException(404, "No such note")
    return note


@router.delete("/condition-notes/{note_id}", status_code=204)
def delete_condition_note(
    note_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not notes_service.delete_note(db, user_id, note_id):
        raise HTTPException(404, "No such note")
```

> Note: `test_add_list_update_delete` also exercises `GET /pain-instances/{id}` (the aggregate), which is added in Task 6. Until then, run just the isolation + cascade tests: `pytest tests/test_condition_notes.py::test_note_on_foreign_instance_rejected tests/test_condition_notes.py::test_notes_cascade_on_instance_delete -v`. Task 6 makes the full file green.

- [ ] **Step 5: Run the runnable tests**

Run: `cd backend && .venv/bin/pytest tests/test_condition_notes.py::test_note_on_foreign_instance_rejected tests/test_condition_notes.py::test_notes_cascade_on_instance_delete -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/condition_notes.py backend/app/routers/records.py backend/tests/test_condition_notes.py
git commit -m "feat(records): condition-notes service + endpoints"
```

---

## Task 5: Documents service

**Files:**
- Create: `backend/app/services/documents.py`
- Test: `backend/tests/test_documents_service.py`

**Interfaces:**
- Produces:
  - `documents.MAX_BYTES: int`, `documents.ALLOWED_MIME: set[str]`
  - `documents.create_document(db, user_id, *, owner_type, instance_id, title, notes, filename, mime_type, content: bytes) -> DocumentMeta` (raises `ValueError` on bad size/mime/foreign instance)
  - `documents.list_documents(db, user_id, owner_type=None, instance_id=None) -> list[DocumentMeta]`
  - `documents.get_document_blob(db, user_id, doc_id) -> tuple[bytes, str | None, str | None] | None` (bytes, mime_type, filename)
  - `documents.update_document(db, user_id, doc_id, patch: DocumentPatch) -> DocumentMeta | None`
  - `documents.delete_document(db, user_id, doc_id) -> bool`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_documents_service.py`:

```python
import pytest

from app.models.pain_instances import PainInstanceCreate
from app.models.records import DocumentPatch
from app.services import documents as docs
from app.services import pain_instances as pi


def _mk(db, user_id, **kw):
    defaults = dict(owner_type="profile", instance_id=None, title="Bloods",
                    notes="normal", filename="b.pdf", mime_type="application/pdf",
                    content=b"%PDF-1.4 data")
    defaults.update(kw)
    return docs.create_document(db, user_id, **defaults)


def test_create_list_download(db, user_id):
    meta = _mk(db, user_id)
    assert meta.size_bytes == len(b"%PDF-1.4 data")

    listed = docs.list_documents(db, user_id)
    assert [m.title for m in listed] == ["Bloods"]
    assert not hasattr(listed[0], "content")

    blob, mime, fname = docs.get_document_blob(db, user_id, meta.id)
    assert blob == b"%PDF-1.4 data" and mime == "application/pdf" and fname == "b.pdf"


def test_reject_oversize_and_bad_mime(db, user_id):
    with pytest.raises(ValueError, match="too large"):
        _mk(db, user_id, content=b"x" * (docs.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="type"):
        _mk(db, user_id, mime_type="application/x-msdownload")


def test_condition_owner_validates_instance(db, user_id, make_user):
    other = make_user()
    foreign = pi.create_instance(db, other, PainInstanceCreate(name="theirs")).id
    with pytest.raises(ValueError, match="pain instance"):
        _mk(db, user_id, owner_type="condition", instance_id=foreign)


def test_filter_and_isolation(db, user_id, make_user):
    iid = pi.create_instance(db, user_id, PainInstanceCreate(name="mine")).id
    _mk(db, user_id, owner_type="condition", instance_id=iid, title="MRI")
    _mk(db, user_id, title="General")
    assert {m.title for m in docs.list_documents(db, user_id, instance_id=iid)} == {"MRI"}
    assert {m.title for m in docs.list_documents(db, user_id, owner_type="profile")} == {"General"}

    other = make_user()
    assert docs.list_documents(db, other) == []


def test_update_and_delete(db, user_id):
    meta = _mk(db, user_id)
    upd = docs.update_document(db, user_id, meta.id, DocumentPatch(title="Blood panel"))
    assert upd.title == "Blood panel"
    assert docs.delete_document(db, user_id, meta.id) is True
    assert docs.get_document_blob(db, user_id, meta.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_documents_service.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/documents.py`:

```python
"""Supporting documents stored as SQLite BLOBs, scoped per user."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.records import DocumentMeta, DocumentPatch

MAX_BYTES = 20 * 1024 * 1024
ALLOWED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/heic",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_META_COLS = (
    "id, owner_type, instance_id, title, notes, filename, mime_type, size_bytes, created_at"
)


def create_document(
    db: Database,
    user_id: UUID,
    *,
    owner_type: str,
    instance_id: UUID | None,
    title: str,
    notes: str | None,
    filename: str | None,
    mime_type: str | None,
    content: bytes,
) -> DocumentMeta:
    if len(content) > MAX_BYTES:
        raise ValueError("file too large")
    if mime_type not in ALLOWED_MIME:
        raise ValueError(f"unsupported file type: {mime_type}")
    if owner_type == "condition":
        owned = db.query_one(
            "SELECT 1 FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
        )
        if not owned:
            raise ValueError("pain instance does not belong to this account")
    else:
        owner_type = "profile"
        instance_id = None

    with db.cursor():
        created = db.query_one(
            f"""
            INSERT INTO documents
                (user_id, owner_type, instance_id, title, notes, filename, mime_type,
                 size_bytes, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING {_META_COLS}
            """,
            [user_id, owner_type, instance_id, title, notes, filename, mime_type,
             len(content), content],
        )
    assert created is not None
    return DocumentMeta(**created)


def list_documents(
    db: Database, user_id: UUID, owner_type: str | None = None, instance_id: UUID | None = None
) -> list[DocumentMeta]:
    where = ["user_id = ?"]
    params: list = [user_id]
    if owner_type is not None:
        where.append("owner_type = ?")
        params.append(owner_type)
    if instance_id is not None:
        where.append("instance_id = ?")
        params.append(instance_id)
    rows = db.query(
        f"SELECT {_META_COLS} FROM documents WHERE {' AND '.join(where)} ORDER BY created_at DESC",
        params,
    )
    return [DocumentMeta(**r) for r in rows]


def get_document_blob(
    db: Database, user_id: UUID, doc_id: UUID
) -> tuple[bytes, str | None, str | None] | None:
    row = db.query_one(
        "SELECT content, mime_type, filename FROM documents WHERE id = ? AND user_id = ?",
        [doc_id, user_id],
    )
    if row is None:
        return None
    return row["content"], row["mime_type"], row["filename"]


def update_document(
    db: Database, user_id: UUID, doc_id: UUID, patch: DocumentPatch
) -> DocumentMeta | None:
    fields = patch.model_dump(exclude_unset=True)
    if fields:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        params = [*fields.values(), doc_id, user_id]
        with db.cursor():
            db.execute(
                f"UPDATE documents SET {assignments} WHERE id = ? AND user_id = ?", params
            )
    row = db.query_one(
        f"SELECT {_META_COLS} FROM documents WHERE id = ? AND user_id = ?", [doc_id, user_id]
    )
    return DocumentMeta(**row) if row else None


def delete_document(db: Database, user_id: UUID, doc_id: UUID) -> bool:
    with db.cursor() as conn:
        cur = conn.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?", [doc_id, user_id]
        )
        return cur.rowcount > 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_documents_service.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/documents.py backend/tests/test_documents_service.py
git commit -m "feat(records): documents service (BLOB storage, scoped, validated)"
```

---

## Task 6: Documents router + condition-detail aggregate

**Files:**
- Create: `backend/app/routers/documents.py`
- Modify: `backend/app/routers/records.py` (add `GET /pain-instances/{id}` aggregate)
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_documents_router.py`

**Interfaces:**
- Consumes: `documents`, `condition_notes`, `pain_instances` services; models from Task 2.
- Produces:
  - `POST /documents` (multipart), `GET /documents`, `GET /documents/{id}/download`, `PATCH /documents/{id}`, `DELETE /documents/{id}`.
  - `GET /pain-instances/{instance_id}` → `ConditionDetail`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_documents_router.py`:

```python
from app.models.pain_instances import PainInstanceCreate
from app.services import pain_instances as pi


def _upload(auth_client, **form):
    data = {"title": "Bloods", "owner_type": "profile"}
    data.update({k: v for k, v in form.items() if k != "file"})
    files = {"file": form.get("file", ("b.pdf", b"%PDF-1.4 x", "application/pdf"))}
    return auth_client.post("/api/v1/documents", data=data, files=files)


def test_upload_list_download_delete(auth_client):
    r = _upload(auth_client, notes="normal")
    assert r.status_code == 201
    doc_id = r.json()["id"]
    assert "content" not in r.json()

    listed = auth_client.get("/api/v1/documents?owner_type=profile").json()
    assert any(d["id"] == doc_id for d in listed)

    dl = auth_client.get(f"/api/v1/documents/{doc_id}/download")
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 x"
    assert dl.headers["content-type"].startswith("application/pdf")

    assert auth_client.delete(f"/api/v1/documents/{doc_id}").status_code == 204


def test_upload_bad_mime_rejected(auth_client):
    r = _upload(auth_client, file=("m.exe", b"MZ", "application/x-msdownload"))
    assert r.status_code == 400


def test_condition_detail_aggregate(auth_client, db, user_id):
    iid = pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic")).id
    auth_client.post(f"/api/v1/pain-instances/{iid}/notes", json={"body": "started PT"})
    _upload(auth_client, owner_type="condition", instance_id=str(iid), title="MRI")

    detail = auth_client.get(f"/api/v1/pain-instances/{iid}").json()
    assert detail["instance"]["name"] == "Left sciatic"
    assert [n["body"] for n in detail["notes"]] == ["started PT"]
    assert [d["title"] for d in detail["documents"]] == ["MRI"]


def test_download_isolation(auth_client, db, make_user):
    other = make_user()
    from app.services import documents as docs
    meta = docs.create_document(
        db, other, owner_type="profile", instance_id=None, title="theirs",
        notes=None, filename="x.pdf", mime_type="application/pdf", content=b"secret",
    )
    assert auth_client.get(f"/api/v1/documents/{meta.id}/download").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_documents_router.py -v`
Expected: FAIL (404 — routes not registered).

- [ ] **Step 3: Implement the documents router**

Create `backend/app/routers/documents.py`:

```python
"""Document upload/list/download/edit/delete (files stored as SQLite BLOBs)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.auth import current_user
from app.deps import db_dep
from app.models.records import DocumentMeta, DocumentPatch
from app.services import documents as service

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentMeta, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    owner_type: str = Form("profile"),
    notes: str | None = Form(None),
    instance_id: UUID | None = Form(None),
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    content = await file.read()
    try:
        return service.create_document(
            db, user_id,
            owner_type=owner_type,
            instance_id=instance_id,
            title=title,
            notes=notes,
            filename=file.filename,
            mime_type=file.content_type,
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/documents", response_model=list[DocumentMeta])
def list_documents(
    owner_type: str | None = None,
    instance_id: UUID | None = None,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.list_documents(db, user_id, owner_type, instance_id)


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    blob = service.get_document_blob(db, user_id, doc_id)
    if blob is None:
        raise HTTPException(404, "No such document")
    content, mime, filename = blob
    headers = {"Content-Disposition": f'inline; filename="{filename or "document"}"'}
    return Response(content=content, media_type=mime or "application/octet-stream", headers=headers)


@router.patch("/documents/{doc_id}", response_model=DocumentMeta)
def patch_document(
    doc_id: UUID,
    data: DocumentPatch,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    updated = service.update_document(db, user_id, doc_id, data)
    if updated is None:
        raise HTTPException(404, "No such document")
    return updated


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    if not service.delete_document(db, user_id, doc_id):
        raise HTTPException(404, "No such document")
```

- [ ] **Step 4: Add the condition-detail aggregate to the records router**

In `backend/app/routers/records.py`, add imports and the aggregate endpoint:

Add to imports:

```python
from app.models.pain_instances import PainInstance
from app.models.records import ConditionDetail
from app.services import documents as documents_service
```

Append the route:

```python
@router.get("/pain-instances/{instance_id}", response_model=ConditionDetail)
def condition_detail(
    instance_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    row = db.query_one(
        "SELECT * FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
    )
    if row is None:
        raise HTTPException(404, "No such pain instance")
    return ConditionDetail(
        instance=PainInstance(**row),
        notes=notes_service.list_notes(db, user_id, instance_id),
        documents=documents_service.list_documents(db, user_id, instance_id=instance_id),
    )
```

> The owned-row read is inline (one `SELECT ... WHERE id = ? AND user_id = ?`), so no extra service import is needed.

- [ ] **Step 5: Register the documents router**

In `backend/app/main.py`, add `documents` to the `from app.routers import (...)` block (after `daily_entries`) and to the `for module in (...)` tuple.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_documents_router.py tests/test_condition_notes.py -v`
Expected: PASS (the full condition-notes file is now green too, since the aggregate exists).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/documents.py backend/app/routers/records.py backend/app/main.py backend/tests/test_documents_router.py
git commit -m "feat(records): documents router + condition-detail aggregate"
```

---

## Task 7: Records context builder

**Files:**
- Create: `backend/app/services/records_context.py`
- Test: `backend/tests/test_records_context.py`

**Interfaces:**
- Consumes: `profile`, `pain_instances` services.
- Produces: `records_context.build(db, user_id) -> str` (empty string when nothing is set).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_records_context.py`:

```python
from app.models.pain_instances import PainInstanceCreate, PainInstancePatch
from app.models.records import PatientProfileIn
from app.services import pain_instances as pi
from app.services import profile as profile_service
from app.services import records_context


def test_empty_when_nothing_set(db, user_id):
    assert records_context.build(db, user_id) == ""


def test_includes_profile_and_conditions(db, user_id):
    profile_service.save_profile(
        db, user_id, PatientProfileIn(sex="male", lifestyle="desk job"),
    )
    inst = pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))
    pi.patch_instance(db, user_id, inst.id, PainInstancePatch(background="L5-S1 disc bulge"))

    ctx = records_context.build(db, user_id)
    assert "PATIENT BACKGROUND" in ctx
    assert "desk job" in ctx
    assert "Left sciatic" in ctx
    assert "L5-S1 disc bulge" in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_records_context.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the builder**

Create `backend/app/services/records_context.py`:

```python
"""Compact patient/condition context injected into every LLM request."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.services import pain_instances as pain_instances_service
from app.services import profile as profile_service


def build(db: Database, user_id: UUID) -> str:
    p = profile_service.get_profile(db, user_id)
    lines: list[str] = []

    bg: list[str] = []
    if p.dob:
        bg.append(f"DOB: {p.dob.isoformat()}")
    if p.sex:
        bg.append(f"Sex: {p.sex}")
    if p.height_cm is not None:
        bg.append(f"Height: {p.height_cm} cm")
    if p.weight_kg is not None:
        bg.append(f"Weight: {p.weight_kg} kg")
    if bg or p.lifestyle or p.medical_history:
        lines.append("PATIENT BACKGROUND:")
        if bg:
            lines.append("- " + "; ".join(bg))
        if p.lifestyle:
            lines.append(f"- Lifestyle: {p.lifestyle}")
        if p.medical_history:
            lines.append(f"- Medical history: {p.medical_history}")

    conditions = [c for c in pain_instances_service.list_instances(db, user_id) if c.active]
    if conditions:
        lines.append("CONDITIONS:")
        for c in conditions:
            region = f" ({c.body_region})" if c.body_region else ""
            details = f": {c.background}" if c.background else ""
            lines.append(f"- {c.name}{region}{details}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_records_context.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/records_context.py backend/tests/test_records_context.py
git commit -m "feat(records): patient/condition LLM context builder"
```

---

## Task 8: LLM `extra_context` parameter

**Files:**
- Modify: `backend/app/services/llm.py`
- Test: `backend/tests/test_llm.py` (add one test)

**Interfaces:**
- Produces: `llm.stream_chat(config, history, run_tool, max_iters=8, extra_context="")` and `llm.draft_weekly(config, bundle, extra_context="")` — when `extra_context` is non-empty it is appended to the system prompt. Default `""` preserves existing behaviour.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_llm.py`:

```python
async def test_extra_context_reaches_system_prompt(monkeypatch, cfg):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _aiter([_chunk(content="ok")])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    async for _ in llm.stream_chat(
        cfg, [{"role": "user", "content": "hi"}], lambda n, a: None,
        extra_context="PATIENT BACKGROUND:\n- Sex: male",
    ):
        pass
    system = captured["messages"][0]
    assert system["role"] == "system"
    assert "PATIENT BACKGROUND" in system["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_llm.py::test_extra_context_reaches_system_prompt -v`
Expected: FAIL (`stream_chat() got an unexpected keyword argument 'extra_context'`).

- [ ] **Step 3: Add the parameter**

In `backend/app/services/llm.py`, add a helper and thread `extra_context` through both functions.

Add after `_completion_kwargs`:

```python
def _system(extra_context: str) -> str:
    return f"{SYSTEM_PROMPT}\n\n{extra_context}" if extra_context else SYSTEM_PROMPT
```

Change `stream_chat`'s signature and its first system message:

```python
async def stream_chat(
    config: ResolvedLlmConfig,
    history: list[dict],
    run_tool: Callable[[str, dict], Any],
    max_iters: int = 8,
    extra_context: str = "",
) -> AsyncIterator[dict]:
    """Run the tool loop, streaming assistant tokens. Yields token/tool/final events."""
    messages: list[dict] = [{"role": "system", "content": _system(extra_context)}, *history]
```

Change `draft_weekly`'s signature and its system message:

```python
async def draft_weekly(
    config: ResolvedLlmConfig, bundle: dict, extra_context: str = ""
) -> WeeklyDraftResponse:
```

and in its `messages` list replace `{"role": "system", "content": SYSTEM_PROMPT}` with `{"role": "system", "content": _system(extra_context)}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_llm.py -v`
Expected: PASS (all prior tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm.py backend/tests/test_llm.py
git commit -m "feat(ai): thread extra_context into system prompt"
```

---

## Task 9: New AI tools — condition notes + documents

**Files:**
- Modify: `backend/app/services/ai_tools.py`
- Test: `backend/tests/test_ai_tools.py` (add tests)

**Interfaces:**
- Consumes: `condition_notes`, `documents` services.
- Produces: `TOOL_SCHEMAS` gains `get_condition_notes` and `list_documents`; `dispatch` handles both. `list_documents` returns metadata only (title, notes, owner_type, instance_id, filename) — never bytes.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ai_tools.py`:

```python
def test_new_tools_registered():
    names = {t["function"]["name"] for t in ai_tools.TOOL_SCHEMAS}
    assert {"get_condition_notes", "list_documents"} <= names


def test_get_condition_notes_and_list_documents(db, user_id):
    from app.models.pain_instances import PainInstanceCreate
    from app.services import condition_notes as cn
    from app.services import documents as docs
    from app.services import pain_instances as pi

    iid = pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic")).id
    cn.add_note(db, user_id, iid, None, "started PT")
    docs.create_document(
        db, user_id, owner_type="condition", instance_id=iid, title="MRI",
        notes="disc bulge", filename="m.pdf", mime_type="application/pdf", content=b"%PDF x",
    )

    notes = ai_tools.dispatch(db, user_id, "get_condition_notes", {"instance_id": str(iid)})
    assert notes[0]["body"] == "started PT"

    listed = ai_tools.dispatch(db, user_id, "list_documents", {})
    assert listed[0]["title"] == "MRI" and listed[0]["notes"] == "disc bulge"
    assert "content" not in listed[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_ai_tools.py::test_new_tools_registered -v`
Expected: FAIL (tool not registered).

- [ ] **Step 3: Add the tools**

In `backend/app/services/ai_tools.py`, add service imports near the others:

```python
from app.services import condition_notes as condition_notes_service
from app.services import documents as documents_service
```

Add two schema entries to `TOOL_SCHEMAS` (before the closing `]`):

```python
    {"type": "function", "function": {
        "name": "get_condition_notes",
        "description": "The dated notes log for one condition (pain instance), newest first.",
        "parameters": {"type": "object", "properties": {"instance_id": {
            "type": "string", "description": "pain instance UUID"}},
            "required": ["instance_id"]},
    }},
    {"type": "function", "function": {
        "name": "list_documents",
        "description": "The user's supporting documents (medical reports/imaging) as metadata: "
                       "title, the user's notes/summary, which condition (if any), and filename. "
                       "The file contents are NOT available.",
        "parameters": {"type": "object", "properties": {}},
    }},
```

Add two branches to `dispatch` (before the final `raise ValueError`):

```python
    if name == "get_condition_notes":
        notes = condition_notes_service.list_notes(db, user_id, UUID(a["instance_id"]))
        return [n.model_dump(mode="json") for n in notes]
    if name == "list_documents":
        return [d.model_dump(mode="json") for d in documents_service.list_documents(db, user_id)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_ai_tools.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_tools.py backend/tests/test_ai_tools.py
git commit -m "feat(ai): add get_condition_notes + list_documents tools"
```

---

## Task 10: Wire records context into the AI router

**Files:**
- Modify: `backend/app/routers/ai.py`
- Modify: `backend/tests/test_ai_router.py` (update fakes + add assertion)

**Interfaces:**
- Consumes: `records_context.build`, updated `llm.stream_chat` / `llm.draft_weekly`.
- Produces: chat + weekly-draft requests carry the patient/condition context.

- [ ] **Step 1: Update the existing fakes and add a test**

In `backend/tests/test_ai_router.py`:

Update `test_chat_streams_and_persists`'s fake to accept + capture `extra_context`:

```python
def test_chat_streams_and_persists(auth_client, monkeypatch, db, user_id):
    auth_client.put("/api/v1/ai/settings", json={
        "provider": "anthropic", "model": "anthropic/claude-sonnet-5", "api_key": "k",
    })
    from app.models.pain_instances import PainInstanceCreate
    from app.services import pain_instances as pi
    pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))

    captured = {}

    async def fake_stream(config, history, run_tool, max_iters=8, extra_context=""):
        captured["extra_context"] = extra_context
        yield {"type": "token", "text": "Hi "}
        yield {"type": "token", "text": "there"}
        yield {"type": "final", "content": "Hi there"}

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    conv = auth_client.post("/api/v1/ai/conversations").json()
    with auth_client.stream("POST", f"/api/v1/ai/conversations/{conv['id']}/messages",
                            json={"content": "hello"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert "Hi there" in text
    assert "Left sciatic" in captured["extra_context"]

    detail = auth_client.get(f"/api/v1/ai/conversations/{conv['id']}").json()
    roles = [(m["role"], m["content"]) for m in detail["messages"]]
    assert ("user", "hello") in roles
    assert ("assistant", "Hi there") in roles
```

Update `test_weekly_draft`'s fake signature to accept `extra_context`:

```python
    async def fake_draft(config, bundle, extra_context=""):
        from app.models.ai import WeeklyDraftResponse
        return WeeklyDraftResponse(key_observations="obs", next_steps="plan")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_ai_router.py::test_chat_streams_and_persists -v`
Expected: FAIL (`extra_context` is empty — router doesn't pass it yet).

- [ ] **Step 3: Wire the context in**

In `backend/app/routers/ai.py`:

Add the import:

```python
from app.services import ai_tools, conversations, llm, llm_settings
from app.services import records_context
from app.services import weekly as weekly_service
```

In `send_message`, after `history = conversations.history_for_llm(db, conv_id)` and the `run_tool` definition, build the context and pass it into the stream call. Change:

```python
        async for event in llm.stream_chat(config, history, run_tool):
```

to:

```python
        async for event in llm.stream_chat(
            config, history, run_tool, extra_context=records_context.build(db, user_id)
        ):
```

In `weekly_draft`, change:

```python
    return await llm.draft_weekly(config, bundle)
```

to:

```python
    return await llm.draft_weekly(config, bundle, extra_context=records_context.build(db, user_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_ai_router.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Full backend suite + ruff**

Run: `cd backend && .venv/bin/pytest -q && .venv/bin/ruff check app tests`
Expected: all pass, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/ai.py backend/tests/test_ai_router.py
git commit -m "feat(ai): inject patient/condition context into chat + weekly draft"
```

---

## Task 11: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces TS types `PatientProfile`, `ConditionNote`, `DocumentMeta`, `ConditionDetail`; `api` methods for profile, condition notes, documents. `documentDownloadUrl(id)` returns the download path.

- [ ] **Step 1: Add types**

In `frontend/src/lib/types.ts`, append:

```typescript
export interface PatientProfile {
  dob: string | null;
  sex: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  lifestyle: string | null;
  medical_history: string | null;
}

export interface ConditionNote {
  id: string;
  instance_id: string;
  occurred_at: string;
  body: string;
  created_at: string | null;
}

export interface DocumentMeta {
  id: string;
  owner_type: string;
  instance_id: string | null;
  title: string;
  notes: string | null;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  created_at: string | null;
}

export interface ConditionDetail {
  instance: PainInstance;
  notes: ConditionNote[];
  documents: DocumentMeta[];
}
```

- [ ] **Step 2: Add API methods**

In `frontend/src/lib/api.ts`, add the new types to the `./types` import (`ConditionDetail`, `ConditionNote`, `DocumentMeta`, `PatientProfile`). Then add to the `api` object before `importXlsx`:

```typescript
  // Records
  getProfile: () => request<PatientProfile>('/profile'),
  saveProfile: (data: Partial<PatientProfile>) =>
    request<PatientProfile>('/profile', { method: 'PUT', body: JSON.stringify(data) }),
  getCondition: (id: string) => request<ConditionDetail>(`/pain-instances/${id}`),
  addConditionNote: (id: string, data: { body: string; occurred_at?: string }) =>
    request<ConditionNote>(`/pain-instances/${id}/notes`, {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  updateConditionNote: (noteId: string, data: { body?: string; occurred_at?: string }) =>
    request<ConditionNote>(`/condition-notes/${noteId}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    }),
  deleteConditionNote: (noteId: string) =>
    request(`/condition-notes/${noteId}`, { method: 'DELETE' }),
  listDocuments: (params?: { owner_type?: string; instance_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.owner_type) q.set('owner_type', params.owner_type);
    if (params?.instance_id) q.set('instance_id', params.instance_id);
    return request<DocumentMeta[]>(`/documents?${q}`);
  },
  uploadDocument: async (form: FormData) => {
    const res = await fetch('/api/v1/documents', {
      method: 'POST',
      credentials: 'include',
      body: form
    });
    if (!res.ok) throw new Error(`${res.status}: ${(await res.json()).detail}`);
    return (await res.json()) as DocumentMeta;
  },
  updateDocument: (id: string, data: { title?: string; notes?: string }) =>
    request<DocumentMeta>(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteDocument: (id: string) => request(`/documents/${id}`, { method: 'DELETE' }),
  documentDownloadUrl: (id: string) => `/api/v1/documents/${id}/download`,
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npm run check`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(records): frontend types + API client"
```

---

## Task 12: Records store

**Files:**
- Create: `frontend/src/lib/stores/records.svelte.ts`
- Test: `frontend/src/lib/stores/records.test.ts`

**Interfaces:**
- Consumes: `api`, `loadPainInstances`.
- Produces: `class RecordsStore` with `$state` fields `profile`, `conditions` (PainInstance[]), `details` (Record<string, ConditionDetail>), `generalDocs` (DocumentMeta[]); methods `load()`, `saveProfile(patch)`, `openCondition(id)`, `addNote(id, body)`, `deleteNote(id, noteId)`, `uploadDoc(form, ownerType, instanceId?)`, `deleteDoc(docId, instanceId?)`. A pure helper `removeDoc(list, id)` is exported for unit testing.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/stores/records.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { removeDoc } from './records.svelte';
import type { DocumentMeta } from '$lib/types';

const doc = (id: string): DocumentMeta => ({
  id, owner_type: 'profile', instance_id: null, title: id, notes: null,
  filename: null, mime_type: null, size_bytes: null, created_at: null
});

describe('removeDoc', () => {
  it('removes the matching document by id', () => {
    const list = [doc('a'), doc('b'), doc('c')];
    expect(removeDoc(list, 'b').map((d) => d.id)).toEqual(['a', 'c']);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/stores/records.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the store**

Create `frontend/src/lib/stores/records.svelte.ts`:

```typescript
// Records store: patient profile, conditions with lazily-loaded detail
// (notes + documents), and general (profile-level) documents.

import { api } from '$lib/api';
import { loadPainInstances } from '$lib/stores/painInstances.svelte';
import type { ConditionDetail, DocumentMeta, PainInstance, PatientProfile } from '$lib/types';

export function removeDoc(list: DocumentMeta[], id: string): DocumentMeta[] {
  return list.filter((d) => d.id !== id);
}

export class RecordsStore {
  profile = $state<PatientProfile | null>(null);
  conditions = $state<PainInstance[]>([]);
  details = $state<Record<string, ConditionDetail>>({});
  generalDocs = $state<DocumentMeta[]>([]);

  async load() {
    this.profile = await api.getProfile();
    this.conditions = await loadPainInstances();
    this.generalDocs = await api.listDocuments({ owner_type: 'profile' });
  }

  async saveProfile(patch: Partial<PatientProfile>) {
    this.profile = await api.saveProfile(patch);
  }

  async openCondition(id: string) {
    this.details = { ...this.details, [id]: await api.getCondition(id) };
  }

  async addNote(id: string, body: string) {
    await api.addConditionNote(id, { body });
    await this.openCondition(id);
  }

  async deleteNote(id: string, noteId: string) {
    await api.deleteConditionNote(noteId);
    await this.openCondition(id);
  }

  async uploadDoc(form: FormData, ownerType: string, instanceId?: string) {
    await api.uploadDocument(form);
    if (ownerType === 'condition' && instanceId) {
      await this.openCondition(instanceId);
    } else {
      this.generalDocs = await api.listDocuments({ owner_type: 'profile' });
    }
  }

  async deleteDoc(docId: string, instanceId?: string) {
    await api.deleteDocument(docId);
    if (instanceId) {
      await this.openCondition(instanceId);
    } else {
      this.generalDocs = removeDoc(this.generalDocs, docId);
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/stores/records.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/stores/records.svelte.ts frontend/src/lib/stores/records.test.ts
git commit -m "feat(records): records store"
```

---

## Task 13: Records page + nav item

**Files:**
- Create: `frontend/src/routes/records/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte`

**Interfaces:**
- Consumes: `RecordsStore`.

- [ ] **Step 1: Add the nav item**

In `frontend/src/routes/+layout.svelte`, add to the `nav` array after the Exercises entry:

```javascript
    { href: '/records', label: 'Records' },
```

- [ ] **Step 2: Build the page**

Create `frontend/src/routes/records/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { RecordsStore } from '$lib/stores/records.svelte';

  const records = new RecordsStore();
  let expanded = $state<string | null>(null);
  let noteDraft = $state<Record<string, string>>({});
  let profileMsg = $state('');

  onMount(() => records.load());

  async function saveProfile(e: Event) {
    e.preventDefault();
    if (!records.profile) return;
    await records.saveProfile(records.profile);
    profileMsg = 'Saved ✓';
  }

  async function toggle(id: string) {
    if (expanded === id) {
      expanded = null;
      return;
    }
    expanded = id;
    if (!records.details[id]) await records.openCondition(id);
  }

  async function saveDetails(id: string) {
    const d = records.details[id];
    if (!d) return;
    await api.patchPainInstance(id, {
      body_region: d.instance.body_region,
      background: d.instance.background
    });
  }

  async function addNote(id: string) {
    const body = (noteDraft[id] ?? '').trim();
    if (!body) return;
    await records.addNote(id, body);
    noteDraft = { ...noteDraft, [id]: '' };
  }

  async function upload(e: Event, ownerType: string, instanceId?: string) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const title = prompt('Document title', file.name) ?? file.name;
    const summary = prompt('Notes/summary for the AI (optional)') ?? '';
    const form = new FormData();
    form.append('file', file);
    form.append('title', title);
    form.append('owner_type', ownerType);
    if (summary) form.append('notes', summary);
    if (instanceId) form.append('instance_id', instanceId);
    await records.uploadDoc(form, ownerType, instanceId);
    input.value = '';
  }
</script>

<div class="card">
  <h2 style="margin-top: 0">Patient background</h2>
  {#if records.profile}
    <form class="grid" onsubmit={saveProfile}>
      <label>Date of birth <input type="date" bind:value={records.profile.dob} /></label>
      <label>Sex <input bind:value={records.profile.sex} placeholder="e.g. male" /></label>
      <label>Height (cm) <input type="number" step="0.1" bind:value={records.profile.height_cm} /></label>
      <label>Weight (kg) <input type="number" step="0.1" bind:value={records.profile.weight_kg} /></label>
      <label class="wide">Lifestyle
        <textarea bind:value={records.profile.lifestyle} rows="3"
          placeholder="Activity, work setup, sleep, habits…"></textarea>
      </label>
      <label class="wide">Medical history
        <textarea bind:value={records.profile.medical_history} rows="4"
          placeholder="Previous events/conditions, surgeries, medications…"></textarea>
      </label>
      <div class="wide">
        <button type="submit">Save background</button>
        {#if profileMsg}<span class="small muted" style="margin-left: 0.6rem">{profileMsg}</span>{/if}
      </div>
    </form>
  {/if}
</div>

<div class="card">
  <h2 style="margin-top: 0">Conditions</h2>
  {#each records.conditions as c (c.id)}
    <div class="condition">
      <button class="crow" onclick={() => toggle(c.id)}>
        <strong>{c.name}</strong>
        {#if c.body_region}<span class="muted small">{c.body_region}</span>{/if}
        <span class="chev">{expanded === c.id ? '▾' : '▸'}</span>
      </button>
      {#if expanded === c.id && records.details[c.id]}
        {@const d = records.details[c.id]}
        <div class="cbody">
          <label>Body region
            <input bind:value={d.instance.body_region} /></label>
          <label>Details
            <textarea bind:value={d.instance.background} rows="4"
              placeholder="Nature of the condition, diagnosis, current status…"></textarea>
          </label>
          <button onclick={() => saveDetails(c.id)}>Save details</button>

          <h4>Notes</h4>
          <div class="row">
            <input placeholder="Add a dated note…" bind:value={noteDraft[c.id]} />
            <button onclick={() => addNote(c.id)}>Add</button>
          </div>
          <ul class="log">
            {#each d.notes as n (n.id)}
              <li>
                <span class="muted small">{n.occurred_at.slice(0, 10)}</span>
                {n.body}
                <button class="link" onclick={() => records.deleteNote(c.id, n.id)}>delete</button>
              </li>
            {/each}
          </ul>

          <h4>Documents</h4>
          <ul class="log">
            {#each d.documents as doc (doc.id)}
              <li>
                <a href={api.documentDownloadUrl(doc.id)} target="_blank" rel="noreferrer"
                  >{doc.title}</a
                >
                {#if doc.notes}<span class="muted small">— {doc.notes}</span>{/if}
                <button class="link" onclick={() => records.deleteDoc(doc.id, c.id)}>delete</button>
              </li>
            {/each}
          </ul>
          <input type="file" onchange={(e) => upload(e, 'condition', c.id)} />
        </div>
      {/if}
    </div>
  {/each}
  {#if records.conditions.length === 0}
    <p class="muted small">No conditions yet — add one from the onboarding prompt.</p>
  {/if}
</div>

<div class="card">
  <h2 style="margin-top: 0">General documents</h2>
  <p class="muted small">Reports/imaging not tied to a single condition.</p>
  <ul class="log">
    {#each records.generalDocs as doc (doc.id)}
      <li>
        <a href={api.documentDownloadUrl(doc.id)} target="_blank" rel="noreferrer">{doc.title}</a>
        {#if doc.notes}<span class="muted small">— {doc.notes}</span>{/if}
        <button class="link" onclick={() => records.deleteDoc(doc.id)}>delete</button>
      </li>
    {/each}
  </ul>
  <input type="file" onchange={(e) => upload(e, 'profile')} />
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }
  .grid label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .grid .wide {
    grid-column: 1 / -1;
  }
  .condition {
    border-bottom: 1px solid var(--border);
    padding: 0.4rem 0;
  }
  .crow {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    color: inherit;
    padding: 0.35rem 0;
  }
  .chev {
    margin-left: auto;
  }
  .cbody {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.5rem 0 0.75rem;
  }
  .cbody label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .log {
    list-style: none;
    padding: 0;
    margin: 0.25rem 0;
  }
  .log li {
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--border);
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0 0 0 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
  }
  @media (max-width: 640px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
```

> The `prompt()` calls for title/summary keep this task small and dependency-free; if the design system has a modal component, a follow-up can replace them. Confirm `var(--text-muted)` / `var(--border)` exist in `frontend/src/app.css` (used elsewhere in Settings) and adjust if the token names differ.

- [ ] **Step 3: Type-check + lint**

Run: `cd frontend && npm run check && npm run format && npm run lint`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/records/+page.svelte frontend/src/routes/+layout.svelte
git commit -m "feat(records): Records page + nav item"
```

---

## Task 14: Remove condition editing from Settings

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`

**Interfaces:** none (moves the pain-instances editor to Records).

- [ ] **Step 1: Remove the Pain instances card and its script**

In `frontend/src/routes/settings/+page.svelte`:

Delete the entire `<div class="card">…Pain instances…</div>` block (the section with the instance list, `addInstance`, and `toggleActive`).

Remove the now-unused script pieces: the `painInstances` / `loadPainInstances` import, the `newName` / `newRegion` / `newBackground` state, the `addInstance` and `toggleActive` functions, and the `painInstances.loaded` check inside `onMount` (keep the rest of `onMount` — the `getLlmSettings` load). Remove the `.cat` / `.link` CSS rules only if they are no longer referenced elsewhere in the file.

Add a one-line pointer where the card was:

```svelte
<div class="card">
  <h2 style="margin-top: 0">Conditions & records</h2>
  <p class="muted small">
    Manage your conditions, patient background, and documents on the
    <a href="/records">Records</a> page.
  </p>
</div>
```

- [ ] **Step 2: Type-check + lint**

Run: `cd frontend && npm run check && npm run format && npm run lint`
Expected: 0 errors, no unused-import/variable warnings.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/settings/+page.svelte
git commit -m "feat(records): move condition editing from Settings to Records"
```

---

## Task 15: Full regression + finalize

- [ ] **Step 1: Backend suite + ruff**

Run: `cd backend && .venv/bin/pytest -q && .venv/bin/ruff check app tests`
Expected: all pass, no lint errors.

- [ ] **Step 2: Frontend tests + check + lint**

Run: `cd frontend && npm run test && npm run check && npm run lint`
Expected: all pass.

- [ ] **Step 3: End-to-end smoke (manual, needs a model configured)**

Run `docker compose up --build` with `NERVETRACK_SECRET_KEY` set, then:
1. Records → fill in patient background → Save; add a condition detail + note; upload a document to the condition and a general document; download one back.
2. Settings → confirm the pain-instances editor is gone and the pointer links to Records.
3. Chat → configure a model (or local Ollama) → ask "what do you know about my background and conditions?" → confirm the answer reflects the profile + condition details (proves the always-injected context) and that it can call `get_condition_notes` / `list_documents`.
4. Weekly → Draft with AI → confirm the draft reflects the patient context.

- [ ] **Step 4: Final commit (if any polish needed)**

```bash
git add -A && git commit -m "chore(records): regression pass"
```

---

## Notes for the implementer

- **Branch:** this plan runs on `feat/records-page` (already branched off `feat/phase2-ai`). It therefore contains the unmerged Phase 2 commits; sort out history at merge time (rebase onto updated `main` once PR #12 lands).
- **BLOB handling:** `sqlite3` stores/returns `bytes` for a `BLOB` column natively (no adapter needed). Pass `bytes` as a query param; reads come back as `bytes`.
- **`db.cursor()` yields the connection** (`with db.cursor() as conn:`), used in `delete_document` for `rowcount`.
- **DECIMAL fields:** `height_cm`/`weight_kg` are `Decimal | None`; the frontend sends them as JSON numbers/strings and Pydantic coerces. The DB stores them via the existing Decimal adapter.
- **Do not** re-add condition editing to Settings; Records is the single home.
