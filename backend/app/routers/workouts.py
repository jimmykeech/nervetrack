"""Reusable workout endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.workouts import Workout, WorkoutIn
from app.services import workouts as service

router = APIRouter(tags=["workouts"])


@router.get("/workouts", response_model=list[Workout])
def list_workouts(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.list_workouts(db, user_id)


@router.post("/workouts", response_model=Workout, status_code=201)
def create_workout(
    data: WorkoutIn, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    try:
        return service.create_workout(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/workouts/{workout_id}", response_model=Workout)
def update_workout(
    workout_id: UUID,
    data: WorkoutIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    try:
        updated = service.update_workout(db, user_id, workout_id, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, "No such workout")
    return updated


@router.delete("/workouts/{workout_id}", status_code=204)
def delete_workout(
    workout_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not service.delete_workout(db, user_id, workout_id):
        raise HTTPException(404, "No such workout")
