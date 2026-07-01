"""Records endpoints: patient profile (condition notes + detail added later)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.deps import db_dep
from app.models.records import PatientProfile, PatientProfileIn
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
