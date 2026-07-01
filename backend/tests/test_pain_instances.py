"""Pain instance catalogue: schema, CRUD, and tagging."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest

from app.models.pain_instances import PainInstanceCreate, PainInstancePatch
from app.services import pain_instances as service


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
