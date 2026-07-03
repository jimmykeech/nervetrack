"""Tingling timer endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import current_user
from app.deps import db_dep
from app.models.tingling import DayTingling, TinglingInterval, TinglingStart
from app.services import tingling as service

router = APIRouter(tags=["tingling"])


@router.post("/tingling/start", response_model=TinglingInterval)
def start_tingling(data: TinglingStart, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.start(db, user_id, data.level)


@router.post("/tingling/stop", response_model=TinglingInterval | None)
def stop_tingling(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.stop(db, user_id)


@router.get("/tingling/current", response_model=TinglingInterval | None)
def current_tingling(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.current_interval(db, user_id)


@router.get("/tingling/day/{entry_date}", response_model=DayTingling)
def tingling_day(entry_date: date, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.day(db, user_id, entry_date)


@router.delete("/tingling/intervals/{interval_id}", status_code=204)
def delete_tingling_interval(
    interval_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not service.delete_interval(db, user_id, interval_id):
        raise HTTPException(404, "No such interval")
    return Response(status_code=204)
