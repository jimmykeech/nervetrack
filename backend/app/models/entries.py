"""Daily entry and pain event schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.postures import PostureTotals  # noqa: F401 (re-exported)


class PainEventIn(BaseModel):
    occurred_at: datetime | None = None
    pain_level: Decimal | None = Field(default=None, ge=0, le=10)
    context: str | None = None


class PainEvent(BaseModel):
    id: UUID
    daily_entry_id: UUID
    occurred_at: datetime
    pain_level: Decimal | None = None
    context: str | None = None


class DailyEntryUpsert(BaseModel):
    """Fields the user can write via PUT /entries/{date}."""

    status: str | None = Field(default=None, pattern="^[GAR]$")
    strengthening_done: bool | None = None
    session_intensity: Decimal | None = Field(default=None, ge=1, le=10)
    sharp_pain_episodes: int | None = Field(default=None, ge=0)
    worst_pain: Decimal | None = Field(default=None, ge=0, le=10)
    tingling_level: Decimal | None = Field(default=None, ge=0, le=10)
    tingling_duration_minutes: int | None = Field(default=None, ge=0)
    stretches_morning: bool | None = None
    stretches_night: bool | None = None
    sitting_breaks: str | None = None
    sleep_quality: Decimal | None = Field(default=None, ge=1, le=5)
    iced: bool | None = None


class DailyEntrySummary(BaseModel):
    entry_date: date
    status: str | None = None
    strengthening_done: bool = False
    session_intensity: Decimal | None = None
    sharp_pain_episodes: int = 0
    worst_pain: Decimal | None = None
    tingling_level: Decimal | None = None
    sleep_quality: Decimal | None = None
    iced: bool = False


class DailyEntry(BaseModel):
    id: UUID
    entry_date: date
    status: str | None = None
    strengthening_done: bool = False
    session_intensity: Decimal | None = None
    sharp_pain_episodes: int = 0
    worst_pain: Decimal | None = None
    tingling_level: Decimal | None = None
    tingling_duration_minutes: int | None = None
    stretches_morning: bool = False
    stretches_night: bool = False
    sitting_breaks: str | None = None
    sleep_quality: Decimal | None = None
    iced: bool = False
    strengthening_done_at: datetime | None = None
    stretches_morning_at: datetime | None = None
    stretches_night_at: datetime | None = None
    iced_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pain_events: list[PainEvent] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)
    session: SessionDetail | None = None
    timer_totals: PostureTotals = Field(default_factory=PostureTotals)
    timer_intervals: list[Interval] = Field(default_factory=list)


from app.models.notes import Note  # noqa: E402
from app.models.sessions import SessionDetail  # noqa: E402
from app.models.timer import Interval  # noqa: E402

DailyEntry.model_rebuild()
