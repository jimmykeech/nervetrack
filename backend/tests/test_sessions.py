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
