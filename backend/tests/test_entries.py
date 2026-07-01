"""Daily entry upsert and pain events."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.entries import DailyEntryUpsert
from app.models.pain_instances import PainInstanceCreate
from app.services import entries as service
from app.services import pain_instances as pain_instances_service


def test_upsert_creates_then_updates(db, user_id):
    d = date(2026, 6, 13)
    first = service.upsert_entry(db, user_id, d, DailyEntryUpsert(status="G", iced=True))
    assert first.status == "G"
    assert first.iced is True

    # A partial update leaves unspecified fields untouched.
    second = service.upsert_entry(db, user_id, d, DailyEntryUpsert(tingling_level=3))
    assert second.status == "G"
    assert second.tingling_level == Decimal("3")
    assert second.iced is True

    rows = db.query("SELECT * FROM daily_entries WHERE entry_date = ?", [d])
    assert len(rows) == 1


def test_pain_event_updates_summary(db, user_id):
    d = date(2026, 6, 13)
    service.upsert_entry(db, user_id, d, DailyEntryUpsert(status="A"))
    service.add_pain_event(db, user_id, d, None, 3, "sitting at desk")
    service.add_pain_event(db, user_id, d, None, 5, "during stretch")
    entry = service.get_entry(db, user_id, d)
    assert entry is not None
    assert entry.sharp_pain_episodes == 2
    assert entry.worst_pain == Decimal("5")
    assert len(entry.pain_events) == 2


def test_pain_event_normalizes_aware_timestamp_to_naive_utc(db, user_id):
    d = date(2026, 6, 13)
    # 22:30 at UTC+10 == 12:30 UTC. Stored value must be naive UTC.
    aware = datetime(2026, 6, 13, 22, 30, tzinfo=timezone(timedelta(hours=10)))
    ev = service.add_pain_event(db, user_id, d, aware, 4, None)
    assert ev.occurred_at == datetime(2026, 6, 13, 12, 30)
    assert ev.occurred_at.tzinfo is None


def test_delete_pain_event_recomputes(db, user_id):
    d = date(2026, 6, 13)
    ev = service.add_pain_event(db, user_id, d, None, 7, None)
    service.add_pain_event(db, user_id, d, None, 2, None)
    service.delete_pain_event(db, user_id, ev.id)
    entry = service.get_entry(db, user_id, d)
    assert entry is not None
    assert entry.sharp_pain_episodes == 1
    assert entry.worst_pain == Decimal("2")


def test_api_upsert_and_validation(auth_client):
    r = auth_client.put("/api/v1/entries/2026-06-13", json={"status": "G", "worst_pain": 4.5})
    assert r.status_code == 200
    assert r.json()["status"] == "G"

    bad = auth_client.put("/api/v1/entries/2026-06-13", json={"status": "X"})
    assert bad.status_code == 422

    out_of_range = auth_client.put("/api/v1/entries/2026-06-13", json={"worst_pain": 20})
    assert out_of_range.status_code == 422


def test_api_requires_auth(client):
    assert client.put("/api/v1/entries/2026-06-13", json={"status": "G"}).status_code == 401
    assert client.get("/api/v1/entries").status_code == 401


def test_add_note_and_list_ordering(db, user_id):
    d = date(2026, 6, 13)
    service.add_note(db, user_id, d, datetime(2026, 6, 13, 14, 0), "second")
    service.add_note(db, user_id, d, datetime(2026, 6, 13, 9, 0), "first")
    entry = service.get_entry(db, user_id, d)
    assert [n.body for n in entry.notes] == ["first", "second"]
    assert entry.notes[0].occurred_at == datetime(2026, 6, 13, 9, 0)


def test_add_note_defaults_timestamp_to_now(db, user_id):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, None, "stamp me")
    assert note.occurred_at is not None
    assert note.occurred_at.tzinfo is None


def test_update_note_body_and_time(db, user_id):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, datetime(2026, 6, 13, 9, 0), "old")
    updated = service.update_note(
        db, user_id, note.id, "new body", datetime(2026, 6, 13, 10, 30)
    )
    assert updated.body == "new body"
    assert updated.occurred_at == datetime(2026, 6, 13, 10, 30)


def test_delete_note(db, user_id):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, None, "bye")
    assert service.delete_note(db, user_id, note.id) is True
    entry = service.get_entry(db, user_id, d)
    assert entry.notes == []


def test_note_ownership_isolated(db, user_id, make_user):
    d = date(2026, 6, 13)
    note = service.add_note(db, user_id, d, None, "mine")
    other = make_user()
    assert service.update_note(db, other, note.id, "hijack", None) is None
    assert service.delete_note(db, other, note.id) is False


def test_api_note_crud(auth_client):
    created = auth_client.post(
        "/api/v1/entries/2026-06-13/notes", json={"body": "felt tightness"}
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    entry = auth_client.get("/api/v1/entries/2026-06-13").json()
    assert [n["body"] for n in entry["notes"]] == ["felt tightness"]

    patched = auth_client.patch(f"/api/v1/notes/{note_id}", json={"body": "eased"})
    assert patched.status_code == 200
    assert patched.json()["body"] == "eased"

    assert auth_client.delete(f"/api/v1/notes/{note_id}").status_code == 204

    blank = auth_client.post("/api/v1/entries/2026-06-13/notes", json={"body": ""})
    assert blank.status_code == 422


def test_checkbox_tick_stamps_time(db, user_id):
    d = date(2026, 6, 13)
    entry = service.upsert_entry(db, user_id, d, DailyEntryUpsert(iced=True))
    assert entry.iced_at is not None
    assert entry.iced_at.tzinfo is None


def test_checkbox_untick_clears_time(db, user_id):
    d = date(2026, 6, 13)
    service.upsert_entry(db, user_id, d, DailyEntryUpsert(strengthening_done=True))
    entry = service.upsert_entry(db, user_id, d, DailyEntryUpsert(strengthening_done=False))
    assert entry.strengthening_done_at is None


def test_checkbox_restamp_not_overwritten_when_unchanged(db, user_id):
    d = date(2026, 6, 13)
    first = service.upsert_entry(db, user_id, d, DailyEntryUpsert(iced=True))
    # An unrelated field changes; iced stays true and its stamp is preserved.
    second = service.upsert_entry(db, user_id, d, DailyEntryUpsert(iced=True, status="A"))
    assert second.iced_at == first.iced_at


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
