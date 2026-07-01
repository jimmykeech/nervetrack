"""Dated notes log per condition (pain instance)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db import Database
from app.models.records import ConditionNote
from app.services.timeutil import now_utc, to_utc_naive


def _owns_instance(db: Database, user_id: UUID, instance_id: UUID) -> bool:
    return db.query_one(
        "SELECT 1 FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
    ) is not None


def _owns_note(db: Database, user_id: UUID, note_id: UUID) -> bool:
    return db.query_one(
        "SELECT 1 FROM condition_notes WHERE id = ? AND user_id = ?", [note_id, user_id]
    ) is not None


def add_note(
    db: Database, user_id: UUID, instance_id: UUID, occurred_at, body: str
) -> ConditionNote:
    if not _owns_instance(db, user_id, instance_id):
        raise ValueError("No such pain instance")
    occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
    with db.cursor():
        created = db.query_one(
            "INSERT INTO condition_notes (instance_id, user_id, occurred_at, body) "
            "VALUES (?, ?, ?, ?) RETURNING id, instance_id, occurred_at, body, created_at",
            [instance_id, user_id, occurred, body],
        )
    assert created is not None
    return ConditionNote(**created)


def list_notes(db: Database, user_id: UUID, instance_id: UUID) -> list[ConditionNote]:
    rows = db.query(
        "SELECT id, instance_id, occurred_at, body, created_at FROM condition_notes "
        "WHERE instance_id = ? AND user_id = ? ORDER BY occurred_at DESC",
        [instance_id, user_id],
    )
    return [ConditionNote(**r) for r in rows]


def update_note(
    db: Database, user_id: UUID, note_id: UUID, body, occurred_at
) -> ConditionNote | None:
    if not _owns_note(db, user_id, note_id):
        return None
    sets: list[str] = []
    params: list[Any] = []
    if body is not None:
        sets.append("body = ?")
        params.append(body)
    if occurred_at is not None:
        sets.append("occurred_at = ?")
        params.append(to_utc_naive(occurred_at))
    if sets:
        params.extend([note_id, user_id])
        with db.cursor():
            db.execute(
                f"UPDATE condition_notes SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                params,
            )
    row = db.query_one(
        "SELECT id, instance_id, occurred_at, body, created_at FROM condition_notes WHERE id = ?",
        [note_id],
    )
    return ConditionNote(**row) if row else None


def delete_note(db: Database, user_id: UUID, note_id: UUID) -> bool:
    if not _owns_note(db, user_id, note_id):
        return False
    with db.cursor():
        db.execute("DELETE FROM condition_notes WHERE id = ? AND user_id = ?", [note_id, user_id])
    return True
