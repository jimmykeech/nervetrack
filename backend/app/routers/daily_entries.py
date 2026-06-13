"""Daily entry endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import current_user
from app.deps import db_dep
from app.models.entries import (
    DailyEntry,
    DailyEntrySummary,
    DailyEntryUpsert,
    PainEvent,
    PainEventIn,
)
from app.services import entries as service

router = APIRouter(tags=["entries"])


@router.get("/entries", response_model=list[DailyEntrySummary])
def list_entries(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.list_entries(db, user_id, from_, to)


@router.get("/entries/{entry_date}", response_model=DailyEntry)
def get_entry(entry_date: date, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    entry = service.get_entry(db, user_id, entry_date)
    if entry is None:
        raise HTTPException(404, "No entry for that date")
    return entry


@router.put("/entries/{entry_date}", response_model=DailyEntry)
def upsert_entry(
    entry_date: date,
    data: DailyEntryUpsert,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.upsert_entry(db, user_id, entry_date, data)


@router.post("/entries/{entry_date}/pain-events", response_model=PainEvent, status_code=201)
def add_pain_event(
    entry_date: date,
    data: PainEventIn,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.add_pain_event(
        db, user_id, entry_date, data.occurred_at, data.pain_level, data.context
    )


@router.delete("/pain-events/{event_id}", status_code=204)
def delete_pain_event(
    event_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not service.delete_pain_event(db, user_id, event_id):
        raise HTTPException(404, "No such pain event")
