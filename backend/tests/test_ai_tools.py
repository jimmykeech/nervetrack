from datetime import date

import pytest

from app.services import ai_tools


def _seed(db, user_id):
    db.execute(
        "INSERT INTO daily_entries (user_id, entry_date, status, sharp_pain_episodes) "
        "VALUES (?, ?, 'A', 3)",
        [user_id, date(2026, 6, 23)],
    )


def test_schemas_are_wellformed():
    names = {t["function"]["name"] for t in ai_tools.TOOL_SCHEMAS}
    assert {
        "list_weeks", "get_week_summary", "get_daily_entry", "get_daily_entries",
        "get_pain_events", "get_timer_day", "get_posture_totals",
        "get_strengthening_sessions", "get_stats", "list_pain_instances",
    } == names
    for t in ai_tools.TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


def test_pain_instances_catalogue_and_tags(db, user_id):
    from app.models.pain_instances import PainInstanceCreate
    from app.services import entries as entries_service
    from app.services import pain_instances as pi

    inst = pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))

    listed = ai_tools.dispatch(db, user_id, "list_pain_instances", {})
    assert any(i["name"] == "Left sciatic" for i in listed)

    # A tagged pain jab must expose its instance_ids through the range tool.
    entries_service.add_pain_event(
        db, user_id, date(2026, 6, 23), None, 5, "sitting", instance_ids=[inst.id]
    )
    events = ai_tools.dispatch(
        db, user_id, "get_pain_events", {"from": "2026-06-22", "to": "2026-06-28"}
    )
    assert str(inst.id) in [str(x) for x in events[0]["instance_ids"]]


def test_dispatch_scopes_to_session_user(db, user_id, make_user):
    _seed(db, user_id)
    other = make_user()
    # Model tries to smuggle another user's id; dispatcher must ignore it.
    result = ai_tools.dispatch(
        db, user_id, "get_daily_entries",
        {"from": "2026-06-22", "to": "2026-06-28", "user_id": str(other)},
    )
    assert len(result) == 1
    assert result[0]["sharp_pain_episodes"] == 3

    # The other user genuinely has no data.
    empty = ai_tools.dispatch(
        db, other, "get_daily_entries", {"from": "2026-06-22", "to": "2026-06-28"}
    )
    assert empty == []


def test_dispatch_unknown_tool_raises(db, user_id):
    with pytest.raises(ValueError, match="unknown tool"):
        ai_tools.dispatch(db, user_id, "drop_tables", {})


def test_get_daily_entry_returns_json(db, user_id):
    _seed(db, user_id)
    out = ai_tools.dispatch(db, user_id, "get_daily_entry", {"date": "2026-06-23"})
    assert out["status"] == "A"
