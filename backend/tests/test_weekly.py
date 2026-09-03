"""Weekly aggregation maths."""

from __future__ import annotations

from datetime import date

from app.config import get_settings
from app.models.entries import DailyEntryUpsert
from app.models.weekly import WeeklyUserFields
from app.services import entries as entries_service
from app.services import weekly as service
from app.services.timeutil import week_start_for


def _seed_week(db, user_id):
    # Friday 2026-06-12 .. Thursday 2026-06-18
    data = [
        ("2026-06-12", "G", 2, 3, False, 2),
        ("2026-06-13", "A", 4, 5, True, 5),
        ("2026-06-14", "A", 0, 1, False, 1),
        ("2026-06-15", "A", 1, 2, True, 3),
        ("2026-06-16", "G", 3, 4, False, 4),
    ]
    for d, status, episodes, tingling, strengthening, worst in data:
        entries_service.upsert_entry(
            db,
            user_id,
            date.fromisoformat(d),
            DailyEntryUpsert(
                status=status,
                sharp_pain_episodes=episodes,
                tingling_level=tingling,
                strengthening_done=strengthening,
                worst_pain=worst,
            ),
        )


def test_week_start_for_friday():
    # 2026-06-13 is a Saturday; Friday week start day = 4.
    assert week_start_for(date(2026, 6, 13), 4) == date(2026, 6, 12)
    assert week_start_for(date(2026, 6, 12), 4) == date(2026, 6, 12)
    assert week_start_for(date(2026, 6, 11), 4) == date(2026, 6, 5)


def test_weekly_aggregation_honours_configured_week_start_day(db, make_user, monkeypatch):
    monkeypatch.setenv("NERVETRACK_WEEK_START_DAY", "6")
    get_settings.cache_clear()
    configured_user = make_user("sunday@example.com", "sub-sunday", "Sunday")
    _seed_day(db, configured_user, "2026-06-14")

    weeks = service.list_weeks(db, configured_user)

    assert [week.week_start for week in weeks] == [date(2026, 6, 14)]


def test_compute_week_metrics(db, user_id):
    _seed_week(db, user_id)
    computed = service.compute_week(db, user_id, date(2026, 6, 12))
    assert computed.days_logged == 5
    assert computed.strengthening_sessions == 2
    assert computed.amber_days == 3
    assert computed.green_days == 2
    # avg episodes (2+4+0+1+3)/5 = 2.0
    assert float(computed.avg_pain_episodes_per_day) == 2.0
    assert float(computed.worst_pain) == 5.0
    # >=3 amber days, no red -> suggested A
    assert computed.suggested_status == "A"


def test_suggested_status_red_wins(db, user_id):
    entries_service.upsert_entry(db, user_id, date(2026, 6, 12), DailyEntryUpsert(status="R"))
    computed = service.compute_week(db, user_id, date(2026, 6, 12))
    assert computed.suggested_status == "R"


def test_save_and_get_week_roundtrip(auth_client):
    auth_client.put("/api/v1/entries/2026-06-13", json={"status": "A"})
    r = auth_client.put(
        "/api/v1/weeks/2026-06-12",
        json={"overall_status": "A", "key_observations": "Steady", "trend_vs_last_week": "Better"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key_observations"] == "Steady"
    assert body["computed"]["days_logged"] == 1


def _seed_day(db, user_id, iso, status="G", worst=2):
    entries_service.upsert_entry(
        db,
        user_id,
        date.fromisoformat(iso),
        DailyEntryUpsert(
            status=status,
            sharp_pain_episodes=1,
            tingling_level=2,
            strengthening_done=False,
            worst_pain=worst,
        ),
    )


# The seeded default week start day is 0 (Monday, see app/services/seed.py);
# 2026-06-08 is a Monday, so each date below opens a new tracking week.
WEEK_STARTS = ["2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06"]


def test_bundle_history_covers_prior_weeks_only(db, user_id):
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, user_id, iso)

    bundle = service.get_draft_bundle(db, user_id, date(2026, 6, 22))

    assert bundle["program_week"] == 3
    assert [h["program_week"] for h in bundle["history"]] == [1, 2]
    assert [h["week_start"] for h in bundle["history"]] == ["2026-06-08", "2026-06-15"]
    # Metrics only — never day-level data.
    assert "days" not in bundle["history"][0]
    assert bundle["history"][0]["avg_tingling_level"] is not None


def test_bundle_history_empty_for_first_week(db, user_id):
    _seed_day(db, user_id, "2026-06-08")

    bundle = service.get_draft_bundle(db, user_id, date(2026, 6, 8))

    assert bundle["program_week"] == 1
    assert bundle["history"] == []
    assert bundle["recent_reviews"] == []


def test_bundle_recent_reviews_caps_at_three_most_recent(db, user_id):
    for iso in WEEK_STARTS:
        _seed_day(db, user_id, iso)
    for iso in WEEK_STARTS[:4]:
        service.save_week(
            db,
            user_id,
            date.fromisoformat(iso),
            WeeklyUserFields(key_observations=f"obs {iso}"),
        )

    bundle = service.get_draft_bundle(db, user_id, date(2026, 7, 6))

    assert [r["program_week"] for r in bundle["recent_reviews"]] == [4, 3, 2]
    assert bundle["recent_reviews"][0]["key_observations"] == "obs 2026-06-29"


def test_bundle_recent_reviews_skips_weeks_without_observations(db, user_id):
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, user_id, iso)
    service.save_week(
        db,
        user_id,
        date.fromisoformat(WEEK_STARTS[0]),
        WeeklyUserFields(key_observations="only this one"),
    )

    bundle = service.get_draft_bundle(db, user_id, date(2026, 6, 22))

    assert [r["program_week"] for r in bundle["recent_reviews"]] == [1]


def test_bundle_history_is_user_scoped(db, user_id, make_user):
    other = make_user("other@example.com", "sub-other", "Other")
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, other, iso)
    _seed_day(db, user_id, WEEK_STARTS[2])

    bundle = service.get_draft_bundle(db, user_id, date(2026, 6, 22))

    # This user has logged only one week, so it is their week 1 with no history.
    assert bundle["program_week"] == 1
    assert bundle["history"] == []


def test_get_week_bundle_stays_lean_for_the_chat_tool(db, user_id):
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, user_id, iso)

    bundle = service.get_week_bundle(db, user_id, date.fromisoformat(WEEK_STARTS[2]))

    # get_week_summary (ai_tools) shares this function; history there would be
    # uncapped duplicate context its tool description does not advertise.
    assert set(bundle) == {"week_start", "week_end", "summary", "days"}


def test_draft_bundle_numbers_a_week_before_the_program_as_one(db, user_id):
    _seed_day(db, user_id, WEEK_STARTS[2])

    bundle = service.get_draft_bundle(db, user_id, date(2020, 1, 6))

    assert bundle["program_week"] == 1
    assert bundle["history"] == []
