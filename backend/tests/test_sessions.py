"""Strengthening session creation/update, including pain-instance tagging."""

from __future__ import annotations

from datetime import UTC, date, datetime

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
