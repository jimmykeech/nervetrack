"""Split a UTC interval into per-local-day segments.

Timestamps are naive UTC (storage convention). Local calendar-day boundaries
are computed in the given timezone, so an interval crossing local midnight is
attributed to each day it covers. Pure and DB-free so the midnight math is
unit-testable in one place.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo


class DaySegment(NamedTuple):
    entry_date: date
    started_at: datetime  # naive UTC
    ended_at: datetime  # naive UTC
    duration_seconds: int


def local_midnight_utc(d: date, tz: ZoneInfo) -> datetime:
    """The naive-UTC instant of local 00:00 on ``d``."""
    return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC).replace(tzinfo=None)


def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.replace(tzinfo=UTC).astimezone(tz).date()


def day_segments(started_at: datetime, end: datetime, tz: ZoneInfo) -> list[DaySegment]:
    """Split ``[started_at, end)`` (naive UTC) into one segment per local day."""
    if end <= started_at:
        return []
    segments: list[DaySegment] = []
    d = _local_date(started_at, tz)
    last = _local_date(end, tz)
    while d <= last:
        day_start = local_midnight_utc(d, tz)
        day_end = local_midnight_utc(d + timedelta(days=1), tz)
        seg_start = max(started_at, day_start)
        seg_end = min(end, day_end)
        if seg_end > seg_start:
            segments.append(
                DaySegment(d, seg_start, seg_end, int((seg_end - seg_start).total_seconds()))
            )
        d += timedelta(days=1)
    return segments
