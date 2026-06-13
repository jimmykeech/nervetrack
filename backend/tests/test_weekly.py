"""Weekly aggregation maths."""

from __future__ import annotations

from datetime import date

from app.models.entries import DailyEntryUpsert
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
