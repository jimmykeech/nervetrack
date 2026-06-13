"""Exercise catalogue endpoints (per-user)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.exercises import Exercise, ExerciseCreate, ExercisePatch

router = APIRouter(tags=["exercises"])


@router.get("/exercises", response_model=list[Exercise])
def list_exercises(
    include_inactive: bool = True,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    where = "user_id = ?" if include_inactive else "user_id = ? AND active"
    return [
        Exercise(**r)
        for r in db.query(
            f"SELECT * FROM exercises WHERE {where} ORDER BY sort_order, name", [user_id]
        )
    ]


@router.post("/exercises", response_model=Exercise, status_code=201)
def create_exercise(
    data: ExerciseCreate, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    existing = db.query_one(
        "SELECT id FROM exercises WHERE user_id = ? AND lower(name) = lower(?)",
        [user_id, data.name],
    )
    if existing:
        raise HTTPException(409, "Exercise already exists")
    order = data.sort_order
    if order is None:
        row = db.query_one(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM exercises WHERE user_id = ?",
            [user_id],
        )
        order = row["n"]
    created = db.query_one(
        "INSERT INTO exercises (user_id, name, active, sort_order) "
        "VALUES (?, ?, TRUE, ?) RETURNING *",
        [user_id, data.name, order],
    )
    return Exercise(**created)


@router.patch("/exercises/{exercise_id}", response_model=Exercise)
def patch_exercise(
    exercise_id: UUID,
    data: ExercisePatch,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        existing = db.query_one(
            "SELECT * FROM exercises WHERE id = ? AND user_id = ?", [exercise_id, user_id]
        )
        if not existing:
            raise HTTPException(404, "No such exercise")
        return Exercise(**existing)
    assignments = ", ".join(f"{k} = ?" for k in fields)
    params = [*fields.values(), exercise_id, user_id]
    updated = db.query_one(
        f"UPDATE exercises SET {assignments} WHERE id = ? AND user_id = ? RETURNING *", params
    )
    if not updated:
        raise HTTPException(404, "No such exercise")
    return Exercise(**updated)
