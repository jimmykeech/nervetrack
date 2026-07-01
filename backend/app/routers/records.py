"""Records endpoints: patient profile (condition notes + detail added later)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.records import (
    ConditionNote,
    ConditionNoteIn,
    ConditionNoteUpdate,
    PatientProfile,
    PatientProfileIn,
)
from app.services import condition_notes as notes_service
from app.services import profile as profile_service

router = APIRouter(tags=["records"])


@router.get("/profile", response_model=PatientProfile)
def get_profile(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return profile_service.get_profile(db, user_id)


@router.put("/profile", response_model=PatientProfile)
def put_profile(
    data: PatientProfileIn, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    return profile_service.save_profile(db, user_id, data)


@router.post("/pain-instances/{instance_id}/notes", response_model=ConditionNote, status_code=201)
def add_condition_note(
    instance_id: UUID,
    data: ConditionNoteIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    try:
        return notes_service.add_note(db, user_id, instance_id, data.occurred_at, data.body)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/condition-notes/{note_id}", response_model=ConditionNote)
def update_condition_note(
    note_id: UUID,
    data: ConditionNoteUpdate,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    note = notes_service.update_note(db, user_id, note_id, data.body, data.occurred_at)
    if note is None:
        raise HTTPException(404, "No such note")
    return note


@router.delete("/condition-notes/{note_id}", status_code=204)
def delete_condition_note(
    note_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not notes_service.delete_note(db, user_id, note_id):
        raise HTTPException(404, "No such note")
