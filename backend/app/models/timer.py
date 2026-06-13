"""Sit/stand timer schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.entries import PostureTotals

POSTURES = ("sitting", "standing", "lying", "walking")


class TimerStart(BaseModel):
    posture: str = Field(pattern="^(sitting|standing|lying|walking)$")
    label: str | None = None


class IntervalPatch(BaseModel):
    posture: str | None = Field(default=None, pattern="^(sitting|standing|lying|walking)$")
    started_at: datetime | None = None
    ended_at: datetime | None = None
    label: str | None = None


class Interval(BaseModel):
    id: UUID
    entry_date: date
    posture: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    label: str | None = None


class DayTimer(BaseModel):
    entry_date: date
    intervals: list[Interval] = Field(default_factory=list)
    totals: PostureTotals = Field(default_factory=PostureTotals)
    running: Interval | None = None
