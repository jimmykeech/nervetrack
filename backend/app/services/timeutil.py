"""Timezone helpers.

Timestamps are stored in UTC. Calendar dates (which day a 23:00 sitting
interval belongs to, etc.) are derived in the configured local timezone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(dt: datetime) -> datetime:
    """Normalise an aware-or-naive datetime to a naive UTC datetime for storage."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def local_date(dt: datetime | None = None) -> date:
    """The calendar date of a UTC timestamp in the configured local timezone."""
    if dt is None:
        dt = now_utc()
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    return aware.astimezone(local_tz()).date()


def week_start_for(d: date, week_start_day: int) -> date:
    """The start date of the tracking week containing ``d``.

    ``week_start_day`` follows ``date.weekday()`` (Mon=0 .. Sun=6).
    """
    delta = (d.weekday() - week_start_day) % 7
    return date.fromordinal(d.toordinal() - delta)
