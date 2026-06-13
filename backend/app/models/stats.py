"""Stats / time-series schemas for charts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DailyStatPoint(BaseModel):
    entry_date: date
    sharp_pain_episodes: int = 0
    worst_pain: Decimal | None = None
    tingling_level: Decimal | None = None
    session_intensity: Decimal | None = None
    sitting_minutes: int = 0
    standing_minutes: int = 0
    lying_minutes: int = 0
    walking_minutes: int = 0
