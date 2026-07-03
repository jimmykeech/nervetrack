"""Sit/stand timer endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import current_user
from app.deps import db_dep
from app.models.timer import DayTimer, Interval, IntervalPatch, TimerStart
from app.services import timer as service

router = APIRouter(tags=["timer"])


@router.post("/timer/start", response_model=Interval)
def start_timer(data: TimerStart, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.start(db, user_id, data.posture, data.label)


@router.post("/timer/stop", response_model=Interval | None)
def stop_timer(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.stop_running(db, user_id)


@router.get("/timer/current", response_model=Interval | None)
def current_timer(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.current_interval(db, user_id)


@router.get("/timer/day/{entry_date}", response_model=DayTimer)
def day_timer(entry_date: date, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return service.day(db, user_id, entry_date)


@router.patch("/timer/intervals/{interval_id}", response_model=Interval)
def patch_interval(
    interval_id: UUID,
    data: IntervalPatch,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    fields = data.model_dump(exclude_unset=True)
    try:
        updated = service.patch_interval(
            db,
            user_id,
            interval_id,
            posture=data.posture,
            started_at=data.started_at,
            ended_at=data.ended_at,
            label=data.label,
            label_set="label" in fields,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, "No such interval")
    return updated


@router.delete("/timer/intervals/{interval_id}", status_code=204)
def delete_interval(
    interval_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    if not service.delete_interval(db, user_id, interval_id):
        raise HTTPException(404, "No such interval")
    return Response(status_code=204)
