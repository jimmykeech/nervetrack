"""Pain instance catalogue endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.deps import db_dep
from app.models.pain_instances import PainInstance, PainInstanceCreate, PainInstancePatch
from app.services import pain_instances as service

router = APIRouter(tags=["pain-instances"])


@router.get("/pain-instances", response_model=list[PainInstance])
def list_pain_instances(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.list_instances(db, user_id)


@router.post("/pain-instances", response_model=PainInstance, status_code=201)
def create_pain_instance(
    data: PainInstanceCreate, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    try:
        return service.create_instance(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.patch("/pain-instances/{instance_id}", response_model=PainInstance)
def patch_pain_instance(
    instance_id: UUID,
    data: PainInstancePatch,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    updated = service.patch_instance(db, user_id, instance_id, data)
    if updated is None:
        raise HTTPException(404, "No such pain instance")
    return updated
