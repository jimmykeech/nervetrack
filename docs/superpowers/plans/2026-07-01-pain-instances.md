# Pain Instances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user catalogue one or more nerve-pain "instances" they're tracking (name, body region, background), require setting up at least one via a mandatory first-login popup, and let pain jabs and strengthening sessions each be tagged with multiple instances.

**Architecture:** A new per-user `pain_instances` catalogue table (modeled on the existing `exercises` catalogue) plus two many-to-many join tables (`pain_event_instances`, `session_instances`). Backend gains a CRUD router/service for the catalogue and `instance_ids` fields on the existing pain-event and session read/write paths. Frontend gains a shared Svelte store for the catalogue, a mandatory onboarding modal wired into the root layout, a Settings management section, and tagging chips on the Today and Exercises pages.

**Tech Stack:** FastAPI + Pydantic v2 + raw SQLite (via the existing `Database` wrapper) on the backend; SvelteKit + TypeScript + vitest on the frontend.

## Global Constraints

- SQLite dialect only; copy the existing UUID-default and `TIMESTAMP DEFAULT` idioms verbatim from `backend/app/migrations/0001_initial.sql` — do not invent new ones.
- Migrations are additive-only for this feature: new tables, no `ALTER TABLE` on existing ones, no backfill.
- `PRAGMA foreign_keys=ON` is active (`backend/app/db.py:65`) — deleting a row that a join table still references raises `sqlite3.IntegrityError`. Any delete path touching `pain_events` or `strength_sessions` must delete their join rows first.
- All new tables/endpoints are scoped per-user (`user_id`), following the `exercises` catalogue pattern: `id`, `name`, `active`, `sort_order`, `PATCH` for partial updates, ownership verified via `WHERE ... AND user_id = ?`.
- Do not touch `daily_entries` columns (`worst_pain`, `tingling_level`, `status`, etc.) or the History/Weekly/Stats routers/pages — explicitly out of scope for this pass (see `docs/superpowers/specs/2026-07-01-pain-instances-design.md`).
- The frontend's vitest config runs in a plain `node` environment (`frontend/vite.config.ts:20`) — there is no component-testing setup. Any logic that needs a unit test must live in a plain `.ts` module (not inside a `.svelte` file) so it can be tested directly.
- The first-login popup is mandatory: no skip/dismiss control while the user has zero pain instances.

---

### Task 1: Migration — pain_instances schema

**Files:**
- Create: `backend/app/migrations/0004_pain_instances.sql`
- Test: `backend/tests/test_pain_instances.py`

**Interfaces:**
- Produces: tables `pain_instances(id, user_id, name, body_region, background, active, sort_order, created_at)`, `pain_event_instances(pain_event_id, instance_id)`, `session_instances(session_id, instance_id)`.

- [ ] **Step 1: Write the failing test**

```python
"""Pain instance catalogue: schema, CRUD, and tagging."""

from __future__ import annotations

import sqlite3

import pytest


def test_schema_creates_tables_with_fk_enforcement(db, user_id):
    created = db.query_one(
        """
        INSERT INTO pain_instances (user_id, name, body_region, background)
        VALUES (?, ?, ?, ?)
        RETURNING *
        """,
        [user_id, "Left sciatic / piriformis", "Left glute/hip", "Started March 2026"],
    )
    assert created["active"] is True
    assert created["sort_order"] == 0

    ev = db.query_one(
        "INSERT INTO daily_entries (user_id, entry_date) VALUES (?, ?) RETURNING id",
        [user_id, "2026-07-01"],
    )
    event = db.query_one(
        "INSERT INTO pain_events (daily_entry_id, occurred_at, pain_level) "
        "VALUES (?, ?, ?) RETURNING id",
        [ev["id"], "2026-07-01T10:00:00", 4],
    )
    db.execute(
        "INSERT INTO pain_event_instances (pain_event_id, instance_id) VALUES (?, ?)",
        [event["id"], created["id"]],
    )

    # Deleting the pain_event while a join row still references it must fail
    # under PRAGMA foreign_keys=ON — this is the exact hazard callers must avoid.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM pain_events WHERE id = ?", [event["id"]])


def test_name_unique_per_user(db, user_id):
    db.execute(
        "INSERT INTO pain_instances (user_id, name) VALUES (?, ?)", [user_id, "Left sciatic"]
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO pain_instances (user_id, name) VALUES (?, ?)", [user_id, "Left sciatic"]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_pain_instances.py -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: pain_instances`

- [ ] **Step 3: Write the migration**

```sql
-- Pain instances: per-user catalogue of tracked nerve-pain issues, with
-- many-to-many tagging onto pain jabs and strengthening sessions.

CREATE TABLE pain_instances (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    body_region TEXT,
    background TEXT,
    active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    UNIQUE (user_id, name)
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_pain_instances.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/migrations/0004_pain_instances.sql backend/tests/test_pain_instances.py
git commit -m "feat(db): add pain_instances schema + tagging join tables"
```

---

### Task 2: Pain instance CRUD (models, service, router)

**Files:**
- Create: `backend/app/models/pain_instances.py`
- Create: `backend/app/services/pain_instances.py`
- Create: `backend/app/routers/pain_instances.py`
- Modify: `backend/app/main.py:12-22,50` (register router)
- Modify: `backend/tests/test_isolation.py` (add one isolation test)
- Test: `backend/tests/test_pain_instances.py` (extend from Task 1)

**Interfaces:**
- Consumes: `app.db.Database` (`.query`, `.query_one`, `.execute`, `.cursor()` — see `backend/app/db.py:94-107`).
- Produces (used by later tasks):
  - `PainInstance(id, name, body_region, background, active, sort_order)` — pydantic model.
  - `PainInstanceCreate(name, body_region=None, background=None, sort_order=None)`.
  - `PainInstancePatch(name=None, body_region=None, background=None, active=None, sort_order=None)`.
  - `service.list_instances(db, user_id) -> list[PainInstance]`
  - `service.create_instance(db, user_id, data: PainInstanceCreate) -> PainInstance` (raises `ValueError` on duplicate name)
  - `service.patch_instance(db, user_id, instance_id, data: PainInstancePatch) -> PainInstance | None`
  - `service.validate_instances(db, user_id, instance_ids: list[UUID]) -> None` (raises `ValueError` if any id isn't owned by the user) — **used by Task 3 and Task 4**.
  - Routes: `GET /api/v1/pain-instances`, `POST /api/v1/pain-instances`, `PATCH /api/v1/pain-instances/{id}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_pain_instances.py`:

```python
from uuid import uuid4

from app.models.pain_instances import PainInstanceCreate, PainInstancePatch
from app.services import pain_instances as service


def test_create_and_list_instances(db, user_id):
    created = service.create_instance(
        db, user_id, PainInstanceCreate(name="Left sciatic", body_region="Left hip")
    )
    assert created.active is True
    assert created.sort_order == 0

    second = service.create_instance(db, user_id, PainInstanceCreate(name="Right shoulder"))
    assert second.sort_order == 1

    listed = service.list_instances(db, user_id)
    assert [i.name for i in listed] == ["Left sciatic", "Right shoulder"]


def test_create_duplicate_name_rejected(db, user_id):
    service.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))
    with pytest.raises(ValueError):
        service.create_instance(db, user_id, PainInstanceCreate(name="left sciatic"))


def test_patch_instance_retires_it(db, user_id):
    created = service.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))
    updated = service.patch_instance(db, user_id, created.id, PainInstancePatch(active=False))
    assert updated is not None
    assert updated.active is False


def test_patch_instance_not_owned_returns_none(db, user_id, make_user):
    other = make_user()
    created = service.create_instance(db, other, PainInstanceCreate(name="Other's issue"))
    assert service.patch_instance(db, user_id, created.id, PainInstancePatch(active=False)) is None


def test_validate_instances_rejects_unowned_id(db, user_id):
    with pytest.raises(ValueError):
        service.validate_instances(db, user_id, [uuid4()])


def test_validate_instances_accepts_owned_ids(db, user_id):
    created = service.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))
    service.validate_instances(db, user_id, [created.id])  # must not raise


def test_api_pain_instance_crud(auth_client):
    created = auth_client.post("/api/v1/pain-instances", json={"name": "Left sciatic"})
    assert created.status_code == 201
    iid = created.json()["id"]

    listed = auth_client.get("/api/v1/pain-instances")
    assert [i["name"] for i in listed.json()] == ["Left sciatic"]

    patched = auth_client.patch(f"/api/v1/pain-instances/{iid}", json={"active": False})
    assert patched.status_code == 200
    assert patched.json()["active"] is False

    dup = auth_client.post("/api/v1/pain-instances", json={"name": "Left sciatic"})
    assert dup.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_pain_instances.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.pain_instances'`

- [ ] **Step 3: Write the models**

`backend/app/models/pain_instances.py`:

```python
"""Pain instance catalogue schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PainInstance(BaseModel):
    id: UUID
    name: str
    body_region: str | None = None
    background: str | None = None
    active: bool = True
    sort_order: int = 0


class PainInstanceCreate(BaseModel):
    name: str = Field(min_length=1)
    body_region: str | None = None
    background: str | None = None
    sort_order: int | None = None


class PainInstancePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    body_region: str | None = None
    background: str | None = None
    active: bool | None = None
    sort_order: int | None = None
```

- [ ] **Step 4: Write the service**

`backend/app/services/pain_instances.py`:

```python
"""Pain instance catalogue logic (mirrors the exercises catalogue pattern)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db import Database
from app.models.pain_instances import PainInstance, PainInstanceCreate, PainInstancePatch


def list_instances(db: Database, user_id: UUID) -> list[PainInstance]:
    rows = db.query(
        "SELECT * FROM pain_instances WHERE user_id = ? ORDER BY sort_order, name", [user_id]
    )
    return [PainInstance(**r) for r in rows]


def create_instance(db: Database, user_id: UUID, data: PainInstanceCreate) -> PainInstance:
    existing = db.query_one(
        "SELECT id FROM pain_instances WHERE user_id = ? AND lower(name) = lower(?)",
        [user_id, data.name],
    )
    if existing:
        raise ValueError("Pain instance already exists")
    order = data.sort_order
    if order is None:
        row = db.query_one(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM pain_instances WHERE user_id = ?",
            [user_id],
        )
        order = row["n"]
    created = db.query_one(
        """
        INSERT INTO pain_instances (user_id, name, body_region, background, active, sort_order)
        VALUES (?, ?, ?, ?, TRUE, ?)
        RETURNING *
        """,
        [user_id, data.name, data.body_region, data.background, order],
    )
    assert created is not None
    return PainInstance(**created)


def patch_instance(
    db: Database, user_id: UUID, instance_id: UUID, data: PainInstancePatch
) -> PainInstance | None:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        existing = db.query_one(
            "SELECT * FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
        )
        return PainInstance(**existing) if existing else None
    assignments = ", ".join(f"{k} = ?" for k in fields)
    params: list[Any] = [*fields.values(), instance_id, user_id]
    updated = db.query_one(
        f"UPDATE pain_instances SET {assignments} WHERE id = ? AND user_id = ? RETURNING *",
        params,
    )
    return PainInstance(**updated) if updated else None


def validate_instances(db: Database, user_id: UUID, instance_ids: list[UUID]) -> None:
    """Ensure every referenced instance belongs to the user."""
    for iid in set(instance_ids):
        owned = db.query_one(
            "SELECT 1 AS ok FROM pain_instances WHERE id = ? AND user_id = ?", [iid, user_id]
        )
        if not owned:
            raise ValueError(f"Pain instance {iid} does not belong to this account")
```

- [ ] **Step 5: Write the router**

`backend/app/routers/pain_instances.py`:

```python
"""Pain instance catalogue endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.pain_instances import PainInstance, PainInstanceCreate, PainInstancePatch
from app.services import pain_instances as service

router = APIRouter(tags=["pain-instances"])


@router.get("/pain-instances", response_model=list[PainInstance])
def list_pain_instances(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.list_instances(db, user_id)


@router.post("/pain-instances", response_model=PainInstance, status_code=201)
def create_pain_instance(
    data: PainInstanceCreate, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    try:
        return service.create_instance(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.patch("/pain-instances/{instance_id}", response_model=PainInstance)
def patch_pain_instance(
    instance_id: UUID,
    data: PainInstancePatch,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    updated = service.patch_instance(db, user_id, instance_id, data)
    if updated is None:
        raise HTTPException(404, "No such pain instance")
    return updated
```

- [ ] **Step 6: Register the router**

In `backend/app/main.py`, change the import block (currently lines 12-22):

```python
from app.routers import (
    ai,
    auth,
    daily_entries,
    exercises,
    imports,
    pain_instances,
    sessions,
    stats,
    timer,
    weekly,
)
```

And change the router-mounting loop (currently line 50):

```python
    for module in (
        auth,
        daily_entries,
        exercises,
        pain_instances,
        sessions,
        timer,
        weekly,
        stats,
        imports,
        ai,
    ):
```

- [ ] **Step 7: Add the isolation test**

Append to `backend/tests/test_isolation.py`:

```python
def test_pain_instances_are_per_user(db, user_id, make_user):
    from app.models.pain_instances import PainInstanceCreate
    from app.services import pain_instances as pain_instances_service

    other = make_user()
    pain_instances_service.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))
    assert len(pain_instances_service.list_instances(db, user_id)) == 1
    assert len(pain_instances_service.list_instances(db, other)) == 0
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_pain_instances.py tests/test_isolation.py -v`
Expected: PASS (all tests, including the 2 from Task 1)

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/pain_instances.py backend/app/services/pain_instances.py \
  backend/app/routers/pain_instances.py backend/app/main.py \
  backend/tests/test_pain_instances.py backend/tests/test_isolation.py
git commit -m "feat(api): add pain instance catalogue CRUD"
```

---

### Task 3: Tag pain jabs with instances

**Files:**
- Modify: `backend/app/models/entries.py:14-26` (`PainEventIn`, `PainEvent`)
- Modify: `backend/app/services/entries.py:1-21,163-199` (`add_pain_event`, `delete_pain_event`, `get_entry`)
- Modify: `backend/app/routers/daily_entries.py:53-62` (`add_pain_event` route)
- Test: `backend/tests/test_entries.py`

**Interfaces:**
- Consumes: `pain_instances_service.validate_instances(db, user_id, instance_ids)` from Task 2.
- Produces: `PainEvent.instance_ids: list[UUID]`, `PainEventIn.instance_ids: list[UUID]`, `service.add_pain_event(db, user_id, entry_date, occurred_at, pain_level, context, instance_ids=None) -> PainEvent`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_entries.py`, add to the existing top-of-file import block (currently lines 1-9) so it reads:

```python
"""Daily entry upsert and pain events."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.entries import DailyEntryUpsert
from app.models.pain_instances import PainInstanceCreate
from app.services import entries as service
from app.services import pain_instances as pain_instances_service
```

Then append these test functions at the end of the file:

```python
def test_pain_event_tagged_with_instances(db, user_id):
    d = date(2026, 6, 13)
    instance = pain_instances_service.create_instance(
        db, user_id, PainInstanceCreate(name="Left sciatic")
    )
    ev = service.add_pain_event(db, user_id, d, None, 4, "sitting", [instance.id])
    assert ev.instance_ids == [instance.id]

    entry = service.get_entry(db, user_id, d)
    assert entry.pain_events[0].instance_ids == [instance.id]


def test_pain_event_rejects_unowned_instance(db, user_id):
    from uuid import uuid4

    d = date(2026, 6, 13)
    with pytest.raises(ValueError):
        service.add_pain_event(db, user_id, d, None, 4, None, [uuid4()])


def test_delete_tagged_pain_event_does_not_violate_fk(db, user_id):
    d = date(2026, 6, 13)
    instance = pain_instances_service.create_instance(
        db, user_id, PainInstanceCreate(name="Left sciatic")
    )
    ev = service.add_pain_event(db, user_id, d, None, 4, None, [instance.id])
    assert service.delete_pain_event(db, user_id, ev.id) is True


def test_api_pain_event_tagging(auth_client):
    created = auth_client.post("/api/v1/pain-instances", json={"name": "Left sciatic"})
    iid = created.json()["id"]

    ev = auth_client.post(
        "/api/v1/entries/2026-06-13/pain-events",
        json={"pain_level": 4, "instance_ids": [iid]},
    )
    assert ev.status_code == 201
    assert ev.json()["instance_ids"] == [iid]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -v -k tagged`
Expected: FAIL — `TypeError: add_pain_event() takes ... positional arguments`

- [ ] **Step 3: Update the models**

In `backend/app/models/entries.py`, change `PainEventIn` and `PainEvent`:

```python
class PainEventIn(BaseModel):
    occurred_at: datetime | None = None
    pain_level: Decimal | None = Field(default=None, ge=0, le=10)
    context: str | None = None
    instance_ids: list[UUID] = Field(default_factory=list)


class PainEvent(BaseModel):
    id: UUID
    daily_entry_id: UUID
    occurred_at: datetime
    pain_level: Decimal | None = None
    context: str | None = None
    instance_ids: list[UUID] = Field(default_factory=list)
```

- [ ] **Step 4: Update the service**

In `backend/app/services/entries.py`, add the import and two helpers, and update `add_pain_event`, `delete_pain_event`, `get_entry`:

```python
from app.services import pain_instances as pain_instances_service
```

```python
def _tag_pain_event(db: Database, event_id: UUID, instance_ids: list) -> None:
    for iid in dict.fromkeys(instance_ids):
        db.execute(
            "INSERT INTO pain_event_instances (pain_event_id, instance_id) VALUES (?, ?)",
            [event_id, iid],
        )


def _pain_event_instance_ids(db: Database, event_id: UUID) -> list:
    rows = db.query(
        "SELECT instance_id FROM pain_event_instances WHERE pain_event_id = ?", [event_id]
    )
    return [r["instance_id"] for r in rows]
```

Replace `add_pain_event`:

```python
def add_pain_event(
    db: Database,
    user_id: UUID,
    entry_date: date,
    occurred_at,
    pain_level,
    context,
    instance_ids: list | None = None,
) -> PainEvent:
    instance_ids = instance_ids or []
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        pain_instances_service.validate_instances(db, user_id, instance_ids)
        occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
        created = db.query_one(
            """
            INSERT INTO pain_events (daily_entry_id, occurred_at, pain_level, context)
            VALUES (?, ?, ?, ?)
            RETURNING *
            """,
            [entry_id, occurred, pain_level, context],
        )
        assert created is not None
        _tag_pain_event(db, created["id"], instance_ids)
        _recompute_pain_summary(db, entry_id)
    return PainEvent(**created, instance_ids=_pain_event_instance_ids(db, created["id"]))
```

Replace `delete_pain_event` (must delete join rows before the parent row, per the FK constraint):

```python
def delete_pain_event(db: Database, user_id: UUID, event_id: UUID) -> bool:
    row = db.query_one(
        """
        SELECT pe.daily_entry_id
        FROM pain_events pe
        JOIN daily_entries d ON d.id = pe.daily_entry_id
        WHERE pe.id = ? AND d.user_id = ?
        """,
        [event_id, user_id],
    )
    if not row:
        return False
    with db.cursor():
        db.execute("DELETE FROM pain_event_instances WHERE pain_event_id = ?", [event_id])
        db.execute("DELETE FROM pain_events WHERE id = ?", [event_id])
        _recompute_pain_summary(db, row["daily_entry_id"])
    return True
```

In `get_entry`, replace the `events = [...]` block:

```python
    events = [
        PainEvent(**e, instance_ids=_pain_event_instance_ids(db, e["id"]))
        for e in db.query(
            "SELECT * FROM pain_events WHERE daily_entry_id = ? ORDER BY occurred_at",
            [row["id"]],
        )
    ]
```

- [ ] **Step 5: Update the router**

In `backend/app/routers/daily_entries.py`, replace `add_pain_event`:

```python
@router.post("/entries/{entry_date}/pain-events", response_model=PainEvent, status_code=201)
def add_pain_event(
    entry_date: date,
    data: PainEventIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    try:
        return service.add_pain_event(
            db,
            user_id,
            entry_date,
            data.occurred_at,
            data.pain_level,
            data.context,
            data.instance_ids,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -v`
Expected: PASS (all tests, existing + new)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/entries.py backend/app/services/entries.py \
  backend/app/routers/daily_entries.py backend/tests/test_entries.py
git commit -m "feat(api): tag pain jabs with one or more pain instances"
```

---

### Task 4: Tag strengthening sessions with instances

**Files:**
- Modify: `backend/app/models/sessions.py:29-42` (`SessionIn`, `SessionDetail`)
- Modify: `backend/app/services/sessions.py` (`_hydrate`, `create_session`, `update_session`)
- Create: `backend/tests/test_sessions.py`

**Interfaces:**
- Consumes: `pain_instances_service.validate_instances` from Task 2.
- Produces: `SessionIn.instance_ids: list[UUID]`, `SessionDetail.instance_ids: list[UUID]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_sessions.py`:

```python
"""Strengthening session creation/update, including pain-instance tagging."""

from __future__ import annotations

from datetime import date

import pytest

from app.models.pain_instances import PainInstanceCreate
from app.models.sessions import SessionIn
from app.services import entries as entries_service
from app.services import pain_instances as pain_instances_service
from app.services import sessions as service


def test_create_session_without_tags(db, user_id):
    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    created = service.create_session(db, user_id, entry_id, SessionIn(intensity=5))
    assert created.instance_ids == []


def test_create_session_tagged_with_instances(db, user_id):
    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    instance = pain_instances_service.create_instance(
        db, user_id, PainInstanceCreate(name="Left sciatic")
    )
    created = service.create_session(
        db, user_id, entry_id, SessionIn(intensity=5, instance_ids=[instance.id])
    )
    assert created.instance_ids == [instance.id]

    fetched = service.get_session(db, user_id, created.id)
    assert fetched.instance_ids == [instance.id]


def test_create_session_rejects_unowned_instance(db, user_id):
    from uuid import uuid4

    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    with pytest.raises(ValueError):
        service.create_session(
            db, user_id, entry_id, SessionIn(intensity=5, instance_ids=[uuid4()])
        )


def test_update_session_replaces_tags(db, user_id):
    entry_id = entries_service.ensure_entry(db, user_id, date(2026, 6, 13))
    a = pain_instances_service.create_instance(db, user_id, PainInstanceCreate(name="A"))
    b = pain_instances_service.create_instance(db, user_id, PainInstanceCreate(name="B"))
    created = service.create_session(
        db, user_id, entry_id, SessionIn(intensity=5, instance_ids=[a.id])
    )
    updated = service.update_session(
        db, user_id, created.id, SessionIn(intensity=6, instance_ids=[b.id])
    )
    assert updated.instance_ids == [b.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_sessions.py -v`
Expected: FAIL — `pydantic.ValidationError` (unexpected keyword `instance_ids`) or `AttributeError`

- [ ] **Step 3: Update the models**

In `backend/app/models/sessions.py`, change `SessionIn` and `SessionDetail`:

```python
class SessionIn(BaseModel):
    performed_at: datetime | None = None
    intensity: Decimal | None = Field(default=None, ge=1, le=10)
    notes: str | None = None
    logs: list[ExerciseLogIn] = Field(default_factory=list)
    instance_ids: list[UUID] = Field(default_factory=list)


class SessionDetail(BaseModel):
    id: UUID
    daily_entry_id: UUID
    performed_at: datetime
    intensity: Decimal | None = None
    notes: str | None = None
    logs: list[ExerciseLog] = Field(default_factory=list)
    instance_ids: list[UUID] = Field(default_factory=list)
```

- [ ] **Step 4: Update the service**

In `backend/app/services/sessions.py`, add the import:

```python
from app.services import pain_instances as pain_instances_service
```

Add two helpers near `_load_logs`:

```python
def _tag_session(db: Database, session_id: UUID, instance_ids: list) -> None:
    for iid in dict.fromkeys(instance_ids):
        db.execute(
            "INSERT INTO session_instances (session_id, instance_id) VALUES (?, ?)",
            [session_id, iid],
        )


def _load_instance_ids(db: Database, session_id: UUID) -> list:
    rows = db.query(
        "SELECT instance_id FROM session_instances WHERE session_id = ?", [session_id]
    )
    return [r["instance_id"] for r in rows]
```

Replace `_hydrate`:

```python
def _hydrate(db: Database, session_row: dict) -> SessionDetail:
    return SessionDetail(
        **session_row,
        logs=_load_logs(db, session_row["id"]),
        instance_ids=_load_instance_ids(db, session_row["id"]),
    )
```

Replace `create_session` (adds a `validate_instances` call and tags the row after logs):

```python
def create_session(
    db: Database, user_id: UUID, daily_entry_id: UUID, data: SessionIn
) -> SessionDetail:
    with db.cursor():
        _validate_exercises(db, user_id, data.logs)
        pain_instances_service.validate_instances(db, user_id, data.instance_ids)
        row = db.query_one(
            """
            INSERT INTO strength_sessions (daily_entry_id, performed_at, intensity, notes)
            VALUES (?, ?, ?, ?)
            RETURNING *
            """,
            [daily_entry_id, data.performed_at or now_utc(), data.intensity, data.notes],
        )
        assert row is not None
        _insert_logs(db, row["id"], data.logs)
        _tag_session(db, row["id"], data.instance_ids)
        # Mirror onto the daily entry so the Today view reflects the session.
        db.execute(
            "UPDATE daily_entries SET strengthening_done = TRUE, session_intensity = ?, "
            "updated_at = ? WHERE id = ?",
            [data.intensity, now_utc(), daily_entry_id],
        )
    return _hydrate(db, row)
```

Replace `update_session` (deletes old tags before inserting the new set, same pattern as `exercise_logs`):

```python
def update_session(
    db: Database, user_id: UUID, session_id: UUID, data: SessionIn
) -> SessionDetail | None:
    existing = _owned_session(db, user_id, session_id)
    if not existing:
        return None
    with db.cursor():
        _validate_exercises(db, user_id, data.logs)
        pain_instances_service.validate_instances(db, user_id, data.instance_ids)
        db.execute(
            "UPDATE strength_sessions SET performed_at = ?, intensity = ?, notes = ? WHERE id = ?",
            [data.performed_at or existing["performed_at"], data.intensity, data.notes, session_id],
        )
        db.execute("DELETE FROM exercise_logs WHERE session_id = ?", [session_id])
        _insert_logs(db, session_id, data.logs)
        db.execute("DELETE FROM session_instances WHERE session_id = ?", [session_id])
        _tag_session(db, session_id, data.instance_ids)
        db.execute(
            "UPDATE daily_entries SET session_intensity = ?, updated_at = ? WHERE id = ?",
            [data.intensity, now_utc(), existing["daily_entry_id"]],
        )
    return get_session(db, user_id, session_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_sessions.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `cd backend && .venv/bin/pytest -v`
Expected: PASS (all tests across all files)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/sessions.py backend/app/services/sessions.py backend/tests/test_sessions.py
git commit -m "feat(api): tag strengthening sessions with one or more pain instances"
```

---

### Task 5: Frontend types, API client, shared store, and form helper

**Files:**
- Modify: `frontend/src/lib/types.ts` (add `PainInstance`, add `instance_ids` to `PainEvent` and `SessionDetail`)
- Modify: `frontend/src/lib/api.ts` (add pain-instance endpoints, extend `addPainEvent`)
- Create: `frontend/src/lib/stores/painInstances.svelte.ts`
- Create: `frontend/src/lib/painInstanceForm.ts`
- Test: `frontend/src/lib/painInstanceForm.test.ts`

**Interfaces:**
- Produces (used by later tasks):
  - `PainInstance { id, name, body_region: string | null, background: string | null, active, sort_order }`
  - `api.listPainInstances(): Promise<PainInstance[]>`
  - `api.createPainInstance(data: { name: string; body_region?: string; background?: string }): Promise<PainInstance>`
  - `api.patchPainInstance(id: string, data: Partial<PainInstance>): Promise<PainInstance>`
  - `api.addPainEvent(date, data)` — `data` now accepts `instance_ids?: string[]`
  - `painInstances: { list: PainInstance[]; loaded: boolean }` (shared `$state`), `loadPainInstances(): Promise<PainInstance[]>`
  - `blankPainInstanceDraft(): PainInstanceDraft`, `hasValidDraft(drafts): boolean`, `filledDrafts(drafts): PainInstanceDraft[]`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/painInstanceForm.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { blankPainInstanceDraft, filledDrafts, hasValidDraft } from './painInstanceForm';

describe('painInstanceForm', () => {
  it('blank draft has empty fields', () => {
    expect(blankPainInstanceDraft()).toEqual({ name: '', body_region: '', background: '' });
  });

  it('hasValidDraft is false when every name is blank or whitespace', () => {
    expect(hasValidDraft([{ name: '', body_region: '', background: '' }])).toBe(false);
    expect(hasValidDraft([{ name: '   ', body_region: '', background: '' }])).toBe(false);
  });

  it('hasValidDraft is true when at least one name is non-empty', () => {
    expect(
      hasValidDraft([
        { name: '', body_region: '', background: '' },
        { name: 'Left sciatic', body_region: '', background: '' }
      ])
    ).toBe(true);
  });

  it('filledDrafts keeps only drafts with a non-empty trimmed name', () => {
    const drafts = [
      { name: 'Left sciatic', body_region: 'Hip', background: '' },
      { name: '  ', body_region: '', background: '' }
    ];
    expect(filledDrafts(drafts)).toEqual([drafts[0]]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- painInstanceForm`
Expected: FAIL — cannot resolve `./painInstanceForm`

- [ ] **Step 3: Write the form helper**

`frontend/src/lib/painInstanceForm.ts`:

```ts
// Pure helpers for the pain-instance draft form, shared by the mandatory
// first-login onboarding modal and the Settings management section.

export interface PainInstanceDraft {
  name: string;
  body_region: string;
  background: string;
}

export function blankPainInstanceDraft(): PainInstanceDraft {
  return { name: '', body_region: '', background: '' };
}

export function hasValidDraft(drafts: PainInstanceDraft[]): boolean {
  return drafts.some((d) => d.name.trim().length > 0);
}

export function filledDrafts(drafts: PainInstanceDraft[]): PainInstanceDraft[] {
  return drafts.filter((d) => d.name.trim().length > 0);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- painInstanceForm`
Expected: PASS (4 tests)

- [ ] **Step 5: Add the type and API client changes**

In `frontend/src/lib/types.ts`, add after the `Interval` interface (or anywhere top-level):

```ts
export interface PainInstance {
  id: string;
  name: string;
  body_region: string | null;
  background: string | null;
  active: boolean;
  sort_order: number;
}
```

Add `instance_ids: string[];` as a field on `PainEvent` (after `context`) and on `SessionDetail` (after `logs`).

In `frontend/src/lib/api.ts`, add `PainInstance` to the type import list, change `addPainEvent`'s signature, and add three new entries to the `api` object:

```ts
// import list — add PainInstance
import type {
  DailyEntry,
  DailyEntrySummary,
  DailyStatPoint,
  DayTimer,
  Exercise,
  Interval,
  Note,
  PainInstance,
  Posture,
  SessionDetail,
  WeeklySummary
} from './types';
```

```ts
  addPainEvent: (
    date: string,
    data: {
      pain_level?: number;
      context?: string;
      occurred_at?: string;
      instance_ids?: string[];
    }
  ) => request(`/entries/${date}/pain-events`, { method: 'POST', body: JSON.stringify(data) }),
```

```ts
  // Pain instances
  listPainInstances: () => request<PainInstance[]>('/pain-instances'),
  createPainInstance: (data: { name: string; body_region?: string; background?: string }) =>
    request<PainInstance>('/pain-instances', { method: 'POST', body: JSON.stringify(data) }),
  patchPainInstance: (id: string, data: Partial<PainInstance>) =>
    request<PainInstance>(`/pain-instances/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    }),
```

(Place the new `Pain instances` block after `Exercises & sessions` and before `Timer`.)

- [ ] **Step 6: Add the shared store**

`frontend/src/lib/stores/painInstances.svelte.ts`:

```ts
// Shared pain-instance catalogue, loaded once from the root layout and read
// by the Today/Exercises tagging UI, the Settings management section, and
// the first-login onboarding gate.

import { api } from '$lib/api';
import type { PainInstance } from '$lib/types';

export const painInstances = $state<{ list: PainInstance[]; loaded: boolean }>({
  list: [],
  loaded: false
});

export async function loadPainInstances(): Promise<PainInstance[]> {
  painInstances.list = await api.listPainInstances();
  painInstances.loaded = true;
  return painInstances.list;
}

export function activePainInstances(): PainInstance[] {
  return painInstances.list.filter((i) => i.active);
}
```

- [ ] **Step 7: Run the full frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run check`
Expected: PASS, no type errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts \
  frontend/src/lib/painInstanceForm.ts frontend/src/lib/painInstanceForm.test.ts \
  frontend/src/lib/stores/painInstances.svelte.ts
git commit -m "feat(frontend): add pain instance types, API client, and shared store"
```

---

### Task 6: Mandatory first-login onboarding popup

**Files:**
- Create: `frontend/src/lib/components/PainInstanceOnboarding.svelte`
- Modify: `frontend/src/routes/+layout.svelte:1-43,68-77`

**Interfaces:**
- Consumes: `painInstances`, `loadPainInstances` (Task 5), `blankPainInstanceDraft`, `hasValidDraft`, `filledDrafts`, `PainInstanceDraft` (Task 5), `api.createPainInstance` (Task 5).

- [ ] **Step 1: Write the onboarding component**

`frontend/src/lib/components/PainInstanceOnboarding.svelte`:

```svelte
<script lang="ts">
  import { api } from '$lib/api';
  import {
    blankPainInstanceDraft,
    filledDrafts,
    hasValidDraft,
    type PainInstanceDraft
  } from '$lib/painInstanceForm';
  import { loadPainInstances } from '$lib/stores/painInstances.svelte';

  let drafts = $state<PainInstanceDraft[]>([blankPainInstanceDraft()]);
  let saving = $state(false);
  let error = $state('');

  function addRow() {
    drafts = [...drafts, blankPainInstanceDraft()];
  }

  const canFinish = $derived(hasValidDraft(drafts) && !saving);

  async function done() {
    if (!hasValidDraft(drafts)) return;
    saving = true;
    error = '';
    try {
      for (const d of filledDrafts(drafts)) {
        await api.createPainInstance({
          name: d.name.trim(),
          body_region: d.body_region.trim() || undefined,
          background: d.background.trim() || undefined
        });
      }
      await loadPainInstances();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      saving = false;
    }
  }
</script>

<div class="overlay">
  <div class="modal card">
    <h2 style="margin-top: 0">Tell us about your nerve pain</h2>
    <p class="muted small">
      Add at least one pain issue you're tracking — what it is, roughly where, and any background
      that will help you look back on your recovery. You can add more, or edit these, later from
      Settings.
    </p>
    {#each drafts as draft, i (i)}
      <div class="draft">
        <label
          >Name
          <input bind:value={draft.name} placeholder="e.g. Left sciatic / piriformis" /></label
        >
        <label
          >Body region (optional)
          <input bind:value={draft.body_region} placeholder="e.g. Left glute/hip" /></label
        >
        <label
          >Background (optional)
          <textarea
            bind:value={draft.background}
            placeholder="Onset, cause, anything useful for tracking recovery"
          ></textarea></label
        >
      </div>
    {/each}
    <button type="button" class="link" onclick={addRow}>+ Add another pain issue</button>
    {#if error}<p style="color: var(--bad)">{error}</p>{/if}
    <button class="status-G" style="margin-top: 0.75rem" onclick={done} disabled={!canFinish}>
      {saving ? 'Saving…' : 'Done'}
    </button>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    padding: 1rem;
  }
  .modal {
    max-width: 28rem;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
  }
  .draft {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--border);
  }
  .draft label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.85rem;
    color: var(--text-muted);
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
    margin-top: 0.25rem;
  }
</style>
```

- [ ] **Step 2: Wire it into the root layout**

In `frontend/src/routes/+layout.svelte`, add the import (near the other component imports):

```ts
  import PainInstanceOnboarding from '$lib/components/PainInstanceOnboarding.svelte';
  import { loadPainInstances, painInstances } from '$lib/stores/painInstances.svelte';
```

Update `onMount` so the catalogue loads right after the user resolves:

```ts
  onMount(async () => {
    initTheme();
    const user = await loadUser();
    // Only bounce to /login for a genuine "not signed in". On a backend error
    // stay put and surface it (see the error block in <main>) rather than
    // looping to a login page whose Google button hits the same failure.
    if (!user && !auth.error && !isLogin) goto('/login');
    if (user) await loadPainInstances();
  });
```

Replace the `<main>` block (currently lines 68-77):

```svelte
    <main>
      {#if auth.ready && auth.user}
        {#if !painInstances.loaded}
          <!-- brief gap while the pain-instance catalogue loads -->
        {:else if painInstances.list.length === 0}
          <PainInstanceOnboarding />
        {:else}
          {@render children()}
        {/if}
      {:else if auth.ready && auth.error}
        <div class="card loaderr">
          <p>Couldn't reach the server.</p>
          <button onclick={() => location.reload()}>Retry</button>
        </div>
      {/if}
    </main>
```

- [ ] **Step 3: Verify manually with the dev stack**

Run: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` (or `npm run dev` in `frontend/` against a running backend)

Sign in as a brand-new user and confirm: the modal appears and cannot be dismissed without a name; "+ Add another pain issue" appends a blank block; "Done" is disabled until at least one name is filled; after clicking "Done" the modal closes and the Today page renders; reloading the page does not show the modal again.

- [ ] **Step 4: Run the frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run check`
Expected: PASS, no type errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/PainInstanceOnboarding.svelte frontend/src/routes/+layout.svelte
git commit -m "feat(frontend): mandatory first-login pain-instance onboarding popup"
```

---

### Task 7: Settings page — manage pain instances

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`

**Interfaces:**
- Consumes: `painInstances`, `loadPainInstances` (Task 5), `api.createPainInstance`, `api.patchPainInstance` (Task 5).

- [ ] **Step 1: Add the management section**

In `frontend/src/routes/settings/+page.svelte`, add to the `<script>` block:

```ts
  import { painInstances, loadPainInstances } from '$lib/stores/painInstances.svelte';
  import { onMount } from 'svelte';

  let newName = $state('');
  let newRegion = $state('');
  let newBackground = $state('');

  onMount(() => {
    if (!painInstances.loaded) loadPainInstances();
  });

  async function addInstance() {
    if (!newName.trim()) return;
    await api.createPainInstance({
      name: newName.trim(),
      body_region: newRegion.trim() || undefined,
      background: newBackground.trim() || undefined
    });
    newName = '';
    newRegion = '';
    newBackground = '';
    await loadPainInstances();
  }

  async function toggleActive(id: string, active: boolean) {
    await api.patchPainInstance(id, { active: !active });
    await loadPainInstances();
  }
```

Add this card to the template, before the "Import spreadsheet" card:

```svelte
<div class="card">
  <h2 style="margin-top: 0">Pain instances</h2>
  <p class="muted small">
    The nerve pain issues you're tracking. Tag pain jabs and strengthening sessions with these on
    the Today and Exercises pages.
  </p>
  <ul class="cat">
    {#each painInstances.list as pi (pi.id)}
      <li>
        <span
          >{pi.name}{pi.body_region ? ` · ${pi.body_region}` : ''}{!pi.active
            ? ' (inactive)'
            : ''}</span
        >
        <button class="link" onclick={() => toggleActive(pi.id, pi.active)}
          >{pi.active ? 'retire' : 'reactivate'}</button
        >
      </li>
    {/each}
  </ul>
  <div class="row" style="margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem">
    <input bind:value={newName} placeholder="Name, e.g. Left sciatic" style="flex: 1 1 10rem" />
    <input
      bind:value={newRegion}
      placeholder="Body region (optional)"
      style="flex: 1 1 8rem"
    />
    <button onclick={addInstance}>Add</button>
  </div>
  <textarea
    bind:value={newBackground}
    placeholder="Background (optional)"
    style="margin-top: 0.5rem; width: 100%"
  ></textarea>
</div>
```

Add to the `<style>` block (the `.cat` and `.link` rules match the Exercises catalogue list in `frontend/src/routes/exercises/+page.svelte:248-265` — copy them verbatim if `settings/+page.svelte` doesn't already have them):

```css
  .cat {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .cat li {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--border);
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
```

- [ ] **Step 2: Verify manually**

Run the dev stack, navigate to `/settings`, add a second pain instance, confirm it appears in the list and in the Today page's jab-tagging chips (built in Task 8), retire it, confirm it disappears from the active chip list but still shows "(inactive)" in Settings.

- [ ] **Step 3: Run the frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run check`
Expected: PASS, no type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/settings/+page.svelte
git commit -m "feat(frontend): manage pain instances from Settings"
```

---

### Task 8: Today page — tag pain jabs with instances

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `activePainInstances`, `painInstances` (Task 5), `api.addPainEvent` with `instance_ids` (Task 5).

- [ ] **Step 1: Add tagging state and helpers**

In `frontend/src/routes/+page.svelte`, add the import:

```ts
  import { activePainInstances, painInstances } from '$lib/stores/painInstances.svelte';
```

Add state near the other jab mini-form state (after `jabTime`):

```ts
  let jabInstanceIds = $state<string[]>([]);

  function toggleJabInstance(id: string) {
    jabInstanceIds = jabInstanceIds.includes(id)
      ? jabInstanceIds.filter((x) => x !== id)
      : [...jabInstanceIds, id];
  }

  function instanceNames(ids: string[]): string {
    return ids
      .map((id) => painInstances.list.find((p) => p.id === id)?.name)
      .filter((n): n is string => Boolean(n))
      .join(', ');
  }
```

- [ ] **Step 2: Include tags when logging a jab and reset after**

Update `logJab()`:

```ts
  async function logJab() {
    // Today + untouched picker → let the server stamp now() (full precision).
    // Past day, or an edited time → send the chosen wall-clock time.
    const sendTime = jabTimeOpen || date !== todayISO();
    const hhmm = jabTime || jabDefaultTime;
    await api.addPainEvent(date, {
      pain_level: jabLevel ?? undefined,
      context: jabContext || undefined,
      occurred_at: sendTime ? combineDateTimeToISO(date, hhmm) : undefined,
      instance_ids: jabInstanceIds
    });
    jabContext = '';
    jabTimeOpen = false;
    jabTime = '';
    jabInstanceIds = [];
    showJab = false;
    await load(date);
  }
```

- [ ] **Step 3: Add the chip row to the jab mini-form**

In the template, inside the `{#if showJab}` block, after the `.jab-form` div and before the `.jab-time` div, add:

```svelte
    {#if activePainInstances().length}
      <div class="chips">
        {#each activePainInstances() as pi (pi.id)}
          <button
            type="button"
            class="chip"
            class:on={jabInstanceIds.includes(pi.id)}
            onclick={() => toggleJabInstance(pi.id)}
          >
            {pi.name}
          </button>
        {/each}
      </div>
    {/if}
```

- [ ] **Step 4: Show tag badges on logged events**

Update the events list item to include tag names:

```svelte
      {#each entry.pain_events as ev}
        <li>
          <span
            >{fmtTime(ev.occurred_at)} · level {ev.pain_level ?? '—'}{ev.context
              ? ` · ${ev.context}`
              : ''}{ev.instance_ids.length ? ` · ${instanceNames(ev.instance_ids)}` : ''}</span
          >
          <button class="link" onclick={() => removeJab(ev.id)}>remove</button>
        </li>
      {/each}
```

- [ ] **Step 5: Add chip styles**

Add to the `<style>` block:

```css
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.6rem;
  }
  .chip {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-muted);
    border-radius: 999px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }
  .chip.on {
    border-color: var(--accent);
    color: var(--text);
  }
```

- [ ] **Step 6: Verify manually**

Run the dev stack. On the Today page, open "Log a pain jab", confirm the active pain-instance chips render, toggle one, log the jab, confirm the logged entry shows the tagged instance name, and confirm logging with zero chips selected still works (untagged jab).

- [ ] **Step 7: Run the frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run check`
Expected: PASS, no type errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(frontend): tag pain jabs with pain instances on the Today page"
```

---

### Task 9: Exercises page — tag strengthening sessions with instances

**Files:**
- Modify: `frontend/src/routes/exercises/+page.svelte`

**Interfaces:**
- Consumes: `activePainInstances`, `painInstances` (Task 5), `api.createSession`/`api.latestSession` now carrying `instance_ids` via `SessionDetail` (Task 5).

- [ ] **Step 1: Add tagging state and helper**

In `frontend/src/routes/exercises/+page.svelte`, add the import:

```ts
  import { activePainInstances } from '$lib/stores/painInstances.svelte';
```

Add state near the other session-level state (after `sessionNotes`):

```ts
  let sessionInstanceIds = $state<string[]>([]);

  function toggleSessionInstance(id: string) {
    sessionInstanceIds = sessionInstanceIds.includes(id)
      ? sessionInstanceIds.filter((x) => x !== id)
      : [...sessionInstanceIds, id];
  }
```

- [ ] **Step 2: Prefill from the previous session and include tags on save**

In `load()`, inside the `if (last)` block (after `intensity = last.intensity;`), add:

```ts
      sessionInstanceIds = last.instance_ids;
```

Update `saveSession()`:

```ts
  async function saveSession() {
    const logs = exercises.filter((e) => included[e.id]).map((e) => rows[e.id]);
    saved = await api.createSession(date, {
      intensity,
      notes: sessionNotes || null,
      logs,
      instance_ids: sessionInstanceIds
    });
    message = `Saved session with ${saved.logs.length} exercises.`;
  }
```

- [ ] **Step 3: Add the chip row to the session form**

In the template, inside the "Log session" card, after the `.field` div containing "Session notes" and before the "Save session" button, add:

```svelte
  {#if activePainInstances().length}
    <div class="field" style="margin-top: 0.75rem">
      <label>Tag pain instance(s) (optional)</label>
      <div class="chips">
        {#each activePainInstances() as pi (pi.id)}
          <button
            type="button"
            class="chip"
            class:on={sessionInstanceIds.includes(pi.id)}
            onclick={() => toggleSessionInstance(pi.id)}
          >
            {pi.name}
          </button>
        {/each}
      </div>
    </div>
  {/if}
```

- [ ] **Step 4: Add chip styles**

Add to the `<style>` block (same tokens as Task 8, so the two pages render identically):

```css
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.4rem;
  }
  .chip {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-muted);
    border-radius: 999px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }
  .chip.on {
    border-color: var(--accent);
    color: var(--text);
  }
```

- [ ] **Step 5: Verify manually**

Run the dev stack. On the Exercises page, confirm the chip row appears under "Log session", toggle a tag, save, reload the page, and confirm the prefill-from-last-session logic carries the tag forward.

- [ ] **Step 6: Run the frontend test suite and typecheck**

Run: `cd frontend && npm test && npm run check`
Expected: PASS, no type errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/exercises/+page.svelte
git commit -m "feat(frontend): tag strengthening sessions with pain instances"
```

---

### Task 10: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -v`
Expected: PASS, all tests across all files (existing + new from Tasks 1-4)

- [ ] **Step 2: Run backend lint**

Run: `cd backend && .venv/bin/ruff check .`
Expected: no errors

- [ ] **Step 3: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS, all tests across all files (existing + new from Task 5)

- [ ] **Step 4: Run frontend typecheck and lint**

Run: `cd frontend && npm run check && npm run lint`
Expected: no errors

- [ ] **Step 5: End-to-end manual smoke test**

Run the dev stack (`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` or equivalent local dev servers) and walk through: register a brand-new account → onboarding popup appears and is mandatory → create two pain instances → popup closes → Today page loads → log a pain jab tagged with one instance → Exercises page → save a strengthening session tagged with the other instance → Settings page → retire one instance → confirm it drops out of the Today/Exercises chip lists but still lists as inactive in Settings.

- [ ] **Step 6: Commit (only if verification uncovered fixes)**

```bash
git add -A
git commit -m "fix: address issues found in pain-instances verification pass"
```
