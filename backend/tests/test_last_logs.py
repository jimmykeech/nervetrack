"""Most-recent-log-per-exercise lookup used to prefill the add-exercise flow."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.models.sessions import ExerciseLogIn, SessionIn
from app.services import entries as entries_service
from app.services import sessions as service


def _exercise_id(db, user_id, name: str) -> str:
    row = db.query_one(
        "SELECT id FROM exercises WHERE user_id = ? AND name = ?", [user_id, name]
    )
    return str(row["id"])


def _add_session(db, user_id, day: date, logs: list[ExerciseLogIn], performed: datetime):
    entry_id = entries_service.ensure_entry(db, user_id, day)
    service.create_session(
        db, user_id, entry_id, SessionIn(performed_at=performed, intensity=5, logs=logs)
    )


def test_last_logs_returns_most_recent_per_exercise(db, user_id):
    from uuid import UUID

    # Two seeded exercises; log the first on two days, the second once.
    names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 2", [user_id])]
    a = _exercise_id(db, user_id, names[0])
    b = _exercise_id(db, user_id, names[1])

    _add_session(db, user_id, date(2026, 6, 1),
                 [ExerciseLogIn(exercise_id=UUID(a), sets=2, reps=8)],
                 datetime(2026, 6, 1, 9, tzinfo=UTC))
    _add_session(db, user_id, date(2026, 6, 8),
                 [ExerciseLogIn(exercise_id=UUID(a), sets=3, reps=12),
                  ExerciseLogIn(exercise_id=UUID(b), hold_seconds=30)],
                 datetime(2026, 6, 8, 9, tzinfo=UTC))

    result = service.last_logs(db, user_id)

    assert result[a]["sets"] == 3      # most recent, not the 2-set older one
    assert result[a]["reps"] == 12
    assert result[b]["hold_seconds"] == 30


def test_last_logs_omits_never_logged_and_is_user_scoped(db, user_id, make_user):
    names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 1", [user_id])]
    from uuid import UUID
    a = _exercise_id(db, user_id, names[0])

    # A second seeded user logs their own exercise; must not leak into user_id's result.
    other_user_id = make_user()
    other_names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 1", [other_user_id])]
    other_a = _exercise_id(db, other_user_id, other_names[0])
    _add_session(db, other_user_id, date(2026, 6, 1),
                 [ExerciseLogIn(exercise_id=UUID(other_a), sets=9)],
                 datetime(2026, 6, 1, 9, tzinfo=UTC))

    result = service.last_logs(db, user_id)
    assert a not in result          # user_id logged nothing
    assert other_a not in result    # other user's log never leaks


def test_last_logs_deterministic_tiebreaker_on_equal_performed_at(db, user_id):
    """When two sessions have same exercise and same performed_at,
    the newer-inserted row (larger el.id) wins."""
    from uuid import UUID

    names = [r["name"] for r in db.query("SELECT name FROM exercises WHERE user_id = ? ORDER BY sort_order LIMIT 1", [user_id])]
    a = _exercise_id(db, user_id, names[0])

    # Create two sessions on the same day with the same performed_at,
    # but different sets to distinguish them.
    same_time = datetime(2026, 6, 1, 9, tzinfo=UTC)

    _add_session(db, user_id, date(2026, 6, 1),
                 [ExerciseLogIn(exercise_id=UUID(a), sets=1, reps=8)],
                 same_time)
    _add_session(db, user_id, date(2026, 6, 1),
                 [ExerciseLogIn(exercise_id=UUID(a), sets=2, reps=8)],
                 same_time)

    result = service.last_logs(db, user_id)

    # The second-created log (sets=2, larger id) should win on the tiebreaker.
    assert result[a]["sets"] == 2
