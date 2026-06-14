"""Daily entry upsert and pain events."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.entries import DailyEntryUpsert
from app.services import entries as service


def test_upsert_creates_then_updates(db, user_id):
    d = date(2026, 6, 13)
    first = service.upsert_entry(db, user_id, d, DailyEntryUpsert(status="G", notes="ok"))
    assert first.status == "G"
    assert first.notes == "ok"

    # A partial update leaves unspecified fields untouched.
    second = service.upsert_entry(db, user_id, d, DailyEntryUpsert(tingling_level=3))
    assert second.status == "G"
    assert second.tingling_level == Decimal("3")
    assert second.notes == "ok"

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
