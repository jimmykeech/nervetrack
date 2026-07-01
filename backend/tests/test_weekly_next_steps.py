from datetime import date

from app.models.weekly import WeeklyUserFields
from app.services import weekly


def test_next_steps_round_trips(db, user_id):
    ws = date(2026, 6, 22)
    db.execute(
        "INSERT INTO daily_entries (user_id, entry_date, status) VALUES (?, ?, 'G')",
        [user_id, ws],
    )
    weekly.save_week(
        db, user_id, ws,
        WeeklyUserFields(key_observations="calm week", next_steps="add one standing block"),
    )
    got = weekly.get_week(db, user_id, ws)
    assert got.key_observations == "calm week"
    assert got.next_steps == "add one standing block"
