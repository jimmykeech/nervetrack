"""Weekly summary endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.deps import db_dep
from app.models.weekly import WeeklySummary, WeeklyUserFields
from app.services import weekly as service

router = APIRouter(tags=["weekly"])


@router.get("/weeks", response_model=list[WeeklySummary])
def list_weeks(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.list_weeks(db, user_id)


@router.get("/weeks/{week_start}", response_model=WeeklySummary)
def get_week(week_start: date, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.get_week(db, user_id, week_start)


@router.put("/weeks/{week_start}", response_model=WeeklySummary)
def save_week(
    week_start: date,
    fields: WeeklyUserFields,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.save_week(db, user_id, week_start, fields)
