"""Strengthening session endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.sessions import SessionDetail, SessionIn
from app.services import entries as entries_service
from app.services import sessions as service

router = APIRouter(tags=["sessions"])


@router.post("/entries/{entry_date}/session", response_model=SessionDetail, status_code=201)
def create_session(
    entry_date: date,
    data: SessionIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    entry_id = entries_service.ensure_entry(db, user_id, entry_date)
    try:
        return service.create_session(db, user_id, entry_id, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/sessions/{session_id}", response_model=SessionDetail)
def update_session(
    session_id: UUID,
    data: SessionIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    try:
        updated = service.update_session(db, user_id, session_id, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, "No such session")
    return updated


@router.get("/sessions/{session_id}/previous", response_model=SessionDetail | None)
def previous_session(
    session_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    return service.previous_session(db, user_id, session_id)


@router.get("/sessions/latest", response_model=SessionDetail | None)
def latest_session(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.latest_session(db, user_id)


@router.get("/exercises/{exercise_id}/progression")
def progression(
    exercise_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    return service.exercise_progression(db, user_id, exercise_id)
