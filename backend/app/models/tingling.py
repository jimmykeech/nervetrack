"""Tingling timer schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TinglingStart(BaseModel):
    level: Decimal = Field(ge=0, le=10)


class TinglingInterval(BaseModel):
    id: UUID
    entry_date: date
    level: Decimal
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None


class DayTingling(BaseModel):
    entry_date: date
    intervals: list[TinglingInterval] = Field(default_factory=list)
    running: TinglingInterval | None = None
