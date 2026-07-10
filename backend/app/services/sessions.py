"""Strengthening session logic.

Sessions are owned through their daily entry; queries scope to a user by joining
``daily_entries.user_id``. ``get_session_for_entry`` is called with an entry id
that the caller has already confirmed belongs to the user, so it needs no extra
scoping.
"""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.sessions import ExerciseLog, ExerciseLogIn, SessionDetail, SessionIn
from app.services import pain_instances as pain_instances_service
from app.services.timeutil import now_utc


def _load_logs(db: Database, session_id: UUID) -> list[ExerciseLog]:
    rows = db.query(
        """
        SELECT el.*, e.name AS exercise_name
        FROM exercise_logs el
        JOIN exercises e ON e.id = el.exercise_id
        WHERE el.session_id = ?
        ORDER BY e.sort_order
        """,
        [session_id],
    )
    return [ExerciseLog(**r) for r in rows]


def _tag_session(db: Database, session_id: UUID, instance_ids: list) -> None:
    for iid in dict.fromkeys(instance_ids):
        db.execute(
            "INSERT INTO session_instances (session_id, instance_id) VALUES (?, ?)",
            [session_id, iid],
        )


def _load_instance_ids(db: Database, session_id: UUID) -> list:
    rows = db.query(
        "SELECT instance_id FROM session_instances WHERE session_id = ?", [session_id]
    )
    return [r["instance_id"] for r in rows]


def _hydrate(db: Database, session_row: dict) -> SessionDetail:
    return SessionDetail(
        **session_row,
        logs=_load_logs(db, session_row["id"]),
        instance_ids=_load_instance_ids(db, session_row["id"]),
    )


def _owned_session(db: Database, user_id: UUID, session_id: UUID) -> dict | None:
    return db.query_one(
        """
        SELECT s.*
        FROM strength_sessions s
        JOIN daily_entries d ON d.id = s.daily_entry_id
        WHERE s.id = ? AND d.user_id = ?
        """,
        [session_id, user_id],
    )


def get_session(db: Database, user_id: UUID, session_id: UUID) -> SessionDetail | None:
    row = _owned_session(db, user_id, session_id)
    return _hydrate(db, row) if row else None


def get_session_for_entry(db: Database, daily_entry_id: UUID) -> SessionDetail | None:
    row = db.query_one(
        "SELECT * FROM strength_sessions WHERE daily_entry_id = ? ORDER BY performed_at LIMIT 1",
        [daily_entry_id],
    )
    return _hydrate(db, row) if row else None


def _validate_exercises(db: Database, user_id: UUID, logs: list[ExerciseLogIn]) -> None:
    """Ensure every referenced exercise belongs to the user."""
    ids = {log.exercise_id for log in logs}
    for ex_id in ids:
        owned = db.query_one(
            "SELECT 1 AS ok FROM exercises WHERE id = ? AND user_id = ?", [ex_id, user_id]
        )
        if not owned:
            raise ValueError(f"Exercise {ex_id} does not belong to this account")


def _insert_logs(db: Database, session_id: UUID, logs: list[ExerciseLogIn]) -> None:
    for log in logs:
        db.execute(
            """
            INSERT INTO exercise_logs
                (session_id, exercise_id, sets, reps, hold_seconds, weight_kg,
                 difficulty, nerve_response, modification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session_id,
                log.exercise_id,
                log.sets,
                log.reps,
                log.hold_seconds,
                log.weight_kg,
                log.difficulty,
                log.nerve_response,
                log.modification,
            ],
        )


def create_session(
    db: Database, user_id: UUID, daily_entry_id: UUID, data: SessionIn
) -> SessionDetail:
    with db.cursor():
        _validate_exercises(db, user_id, data.logs)
        pain_instances_service.validate_instances(db, user_id, data.instance_ids)
        row = db.query_one(
            """
            INSERT INTO strength_sessions (daily_entry_id, performed_at, intensity, notes)
            VALUES (?, ?, ?, ?)
            RETURNING *
            """,
            [daily_entry_id, data.performed_at or now_utc(), data.intensity, data.notes],
        )
        assert row is not None
        _insert_logs(db, row["id"], data.logs)
        _tag_session(db, row["id"], data.instance_ids)
        # Mirror onto the daily entry so the Today view reflects the session.
        db.execute(
            "UPDATE daily_entries SET strengthening_done = TRUE, session_intensity = ?, "
            "updated_at = ? WHERE id = ?",
            [data.intensity, now_utc(), daily_entry_id],
        )
    return _hydrate(db, row)


def update_session(
    db: Database, user_id: UUID, session_id: UUID, data: SessionIn
) -> SessionDetail | None:
    existing = _owned_session(db, user_id, session_id)
    if not existing:
        return None
    with db.cursor():
        _validate_exercises(db, user_id, data.logs)
        pain_instances_service.validate_instances(db, user_id, data.instance_ids)
        db.execute(
            "UPDATE strength_sessions SET performed_at = ?, intensity = ?, notes = ? WHERE id = ?",
            [data.performed_at or existing["performed_at"], data.intensity, data.notes, session_id],
        )
        db.execute("DELETE FROM exercise_logs WHERE session_id = ?", [session_id])
        _insert_logs(db, session_id, data.logs)
        db.execute("DELETE FROM session_instances WHERE session_id = ?", [session_id])
        _tag_session(db, session_id, data.instance_ids)
        db.execute(
            "UPDATE daily_entries SET session_intensity = ?, updated_at = ? WHERE id = ?",
            [data.intensity, now_utc(), existing["daily_entry_id"]],
        )
    return get_session(db, user_id, session_id)


def previous_session(
    db: Database, user_id: UUID, before_session_id: UUID
) -> SessionDetail | None:
    """The user's most recent session strictly before the given one (for prefill)."""
    current = _owned_session(db, user_id, before_session_id)
    if not current:
        return None
    row = db.query_one(
        """
        SELECT s.*
        FROM strength_sessions s
        JOIN daily_entries d ON d.id = s.daily_entry_id
        WHERE d.user_id = ? AND s.performed_at < ?
        ORDER BY s.performed_at DESC LIMIT 1
        """,
        [user_id, current["performed_at"]],
    )
    return _hydrate(db, row) if row else None


def latest_session(db: Database, user_id: UUID) -> SessionDetail | None:
    row = db.query_one(
        """
        SELECT s.*
        FROM strength_sessions s
        JOIN daily_entries d ON d.id = s.daily_entry_id
        WHERE d.user_id = ?
        ORDER BY s.performed_at DESC LIMIT 1
        """,
        [user_id],
    )
    return _hydrate(db, row) if row else None


def exercise_progression(db: Database, user_id: UUID, exercise_id: UUID) -> list[dict]:
    """Difficulty and load over time for one of the user's exercises."""
    return db.query(
        """
        SELECT s.performed_at, el.sets, el.reps, el.hold_seconds, el.weight_kg, el.difficulty
        FROM exercise_logs el
        JOIN strength_sessions s ON s.id = el.session_id
        JOIN daily_entries d ON d.id = s.daily_entry_id
        WHERE el.exercise_id = ? AND d.user_id = ?
        ORDER BY s.performed_at
        """,
        [exercise_id, user_id],
    )


def last_logs(db: Database, user_id: UUID) -> dict[str, dict]:
    """Most recent log per exercise for the user, to prefill new session rows."""
    rows = db.query(
        """
        SELECT exercise_id, sets, reps, hold_seconds, weight_kg,
               difficulty, nerve_response, modification
        FROM (
            SELECT el.*,
                   ROW_NUMBER() OVER (PARTITION BY el.exercise_id
                                      ORDER BY s.performed_at DESC, el.rowid DESC) AS rn
            FROM exercise_logs el
            JOIN strength_sessions s ON s.id = el.session_id
            JOIN daily_entries d     ON d.id = s.daily_entry_id
            WHERE d.user_id = ?
        ) t
        WHERE rn = 1
        """,
        [user_id],
    )
    out: dict[str, dict] = {}
    for r in rows:
        eid = str(r.pop("exercise_id"))
        out[eid] = r
    return out
