"""Data isolation between accounts."""

from __future__ import annotations

from datetime import date

from app.models.entries import DailyEntryUpsert
from app.services import entries as entries_service
from app.services import timer as timer_service
from app.services import weekly as weekly_service


def test_entries_are_per_user(db, user_id, make_user):
    other = make_user()
    d = date(2026, 6, 13)
    entries_service.upsert_entry(db, user_id, d, DailyEntryUpsert(status="R"))

    # Owner sees it; the other user does not.
    assert entries_service.get_entry(db, user_id, d).status == "R"
    assert entries_service.get_entry(db, other, d) is None
    assert len(entries_service.list_entries(db, user_id, None, None)) == 1
    assert len(entries_service.list_entries(db, other, None, None)) == 0


def test_same_date_allowed_for_two_users(db, user_id, make_user):
    other = make_user()
    d = date(2026, 6, 13)
    entries_service.upsert_entry(db, user_id, d, DailyEntryUpsert(status="G"))
    # The composite unique (user_id, entry_date) lets a second user log the same day.
    entries_service.upsert_entry(db, other, d, DailyEntryUpsert(status="A"))
    assert entries_service.get_entry(db, user_id, d).status == "G"
    assert entries_service.get_entry(db, other, d).status == "A"


def test_running_timer_is_per_user(db, user_id, make_user):
    other = make_user()
    timer_service.start(db, user_id, "sitting", None)
    # The other user has no running interval and an independent timeline.
    assert timer_service.current_interval(db, other) is None
    assert timer_service.current_interval(db, user_id) is not None


def test_exercise_catalogue_seeded_per_user(db, user_id, make_user):
    other = make_user()
    a = db.query("SELECT name FROM exercises WHERE user_id = ?", [user_id])
    b = db.query("SELECT name FROM exercises WHERE user_id = ?", [other])
    assert len(a) == 14 and len(b) == 14  # each account gets its own catalogue


def test_weeks_are_per_user(db, user_id, make_user):
    other = make_user()
    entries_service.upsert_entry(db, user_id, date(2026, 6, 13), DailyEntryUpsert(status="A"))
    assert len(weekly_service.list_weeks(db, user_id)) == 1
    assert len(weekly_service.list_weeks(db, other)) == 0
