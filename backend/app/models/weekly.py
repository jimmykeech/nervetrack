"""Weekly summary schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class WeeklyComputed(BaseModel):
    strengthening_sessions: int = 0
    avg_pain_episodes_per_day: Decimal | None = None
    avg_tingling_level: Decimal | None = None
    worst_pain: Decimal | None = None
    days_logged: int = 0
    red_days: int = 0
    amber_days: int = 0
    green_days: int = 0
    suggested_status: str | None = None
    sitting_minutes: int = 0
    standing_minutes: int = 0


class WeeklyUserFields(BaseModel):
    overall_status: str | None = Field(default=None, pattern="^[GAR]$")
    key_observations: str | None = None
    trend_vs_last_week: str | None = Field(
        default=None, pattern="^(Better|Same|Slightly Worse|Worse)$"
    )
    next_steps: str | None = None


class WeeklySummary(WeeklyUserFields):
    week_start: date
    week_end: date
    computed: WeeklyComputed
