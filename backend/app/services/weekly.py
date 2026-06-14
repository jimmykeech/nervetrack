"""Weekly aggregation, scoped per user.

Computed numeric fields are derived from daily data; qualitative fields
(key observations, overall status, trend) are user-written and persisted.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.db import Database
from app.models.weekly import WeeklyComputed, WeeklySummary, WeeklyUserFields
from app.services.timeutil import week_start_for


def configured_week_start_day(db: Database, user_id: UUID) -> int:
    row = db.query_one(
        "SELECT value FROM app_settings WHERE user_id = ? AND key = 'week_start_day'",
        [user_id],
    )
    return int(row["value"]) if row and row["value"] is not None else 4


def suggest_status(red: int, amber: int) -> str:
    """R if any red day, A if >=3 amber days, else G."""
    if red > 0:
        return "R"
    if amber >= 3:
        return "A"
    return "G"


def compute_week(db: Database, user_id: UUID, week_start: date) -> WeeklyComputed:
    week_end = week_start + timedelta(days=6)
    agg = db.query_one(
        """
        SELECT
            COUNT(*) AS days_logged,
            COUNT(*) FILTER (WHERE strengthening_done) AS sessions,
            AVG(sharp_pain_episodes) AS avg_episodes,
            AVG(tingling_level) AS avg_tingling,
            MAX(worst_pain) AS worst,
            COUNT(*) FILTER (WHERE status = 'R') AS red,
            COUNT(*) FILTER (WHERE status = 'A') AS amber,
            COUNT(*) FILTER (WHERE status = 'G') AS green
        FROM daily_entries
        WHERE user_id = ? AND entry_date >= ? AND entry_date <= ?
        """,
        [user_id, week_start, week_end],
    )
    assert agg is not None
    postures = db.query_one(
        """
        SELECT
            CAST(COALESCE(SUM(duration_seconds) FILTER (WHERE posture = 'sitting'), 0) / 60
                 AS INTEGER) AS sitting_min,
            CAST(COALESCE(SUM(duration_seconds) FILTER (WHERE posture = 'standing'), 0) / 60
                 AS INTEGER) AS standing_min
        FROM sit_stand_sessions
        WHERE user_id = ? AND entry_date >= ? AND entry_date <= ?
        """,
        [user_id, week_start, week_end],
    )
    assert postures is not None
    red, amber, green = agg["red"] or 0, agg["amber"] or 0, agg["green"] or 0

    def dec(v: Any) -> Decimal | None:
        return Decimal(str(round(float(v), 2))) if v is not None else None

    return WeeklyComputed(
        strengthening_sessions=agg["sessions"] or 0,
        avg_pain_episodes_per_day=dec(agg["avg_episodes"]),
        avg_tingling_level=dec(agg["avg_tingling"]),
        worst_pain=agg["worst"],
        days_logged=agg["days_logged"] or 0,
        red_days=red,
        amber_days=amber,
        green_days=green,
        suggested_status=suggest_status(red, amber),
        sitting_minutes=postures["sitting_min"] or 0,
        standing_minutes=postures["standing_min"] or 0,
    )


def get_week(db: Database, user_id: UUID, week_start: date) -> WeeklySummary:
    computed = compute_week(db, user_id, week_start)
    saved = db.query_one(
        "SELECT * FROM weekly_summaries WHERE user_id = ? AND week_start = ?",
        [user_id, week_start],
    )
    user = WeeklyUserFields(
        overall_status=(saved or {}).get("overall_status"),
        key_observations=(saved or {}).get("key_observations"),
        trend_vs_last_week=(saved or {}).get("trend_vs_last_week"),
    )
    return WeeklySummary(
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        computed=computed,
        **user.model_dump(),
    )


def save_week(
    db: Database, user_id: UUID, week_start: date, fields: WeeklyUserFields
) -> WeeklySummary:
    computed = compute_week(db, user_id, week_start)
    with db.cursor():
        db.execute(
            """
            INSERT INTO weekly_summaries
                (user_id, week_start, strengthening_sessions, avg_pain_episodes_per_day,
                 avg_tingling_level, worst_pain, overall_status, key_observations,
                 trend_vs_last_week)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, week_start) DO UPDATE SET
                strengthening_sessions = excluded.strengthening_sessions,
                avg_pain_episodes_per_day = excluded.avg_pain_episodes_per_day,
                avg_tingling_level = excluded.avg_tingling_level,
                worst_pain = excluded.worst_pain,
                overall_status = excluded.overall_status,
                key_observations = excluded.key_observations,
                trend_vs_last_week = excluded.trend_vs_last_week
            """,
            [
                user_id,
                week_start,
                computed.strengthening_sessions,
                computed.avg_pain_episodes_per_day,
                computed.avg_tingling_level,
                computed.worst_pain,
                fields.overall_status,
                fields.key_observations,
                fields.trend_vs_last_week,
            ],
        )
    return get_week(db, user_id, week_start)


def list_weeks(db: Database, user_id: UUID) -> list[WeeklySummary]:
    """All tracking weeks spanned by the user's logged daily data."""
    bounds = db.query_one(
        "SELECT MIN(entry_date) AS lo, MAX(entry_date) AS hi FROM daily_entries WHERE user_id = ?",
        [user_id],
    )
    if not bounds or bounds["lo"] is None:
        return []
    lo = bounds["lo"]
    hi = bounds["hi"]
    lo = date.fromisoformat(lo) if isinstance(lo, str) else lo
    hi = date.fromisoformat(hi) if isinstance(hi, str) else hi
    start_day = configured_week_start_day(db, user_id)
    cursor = week_start_for(lo, start_day)
    last = week_start_for(hi, start_day)
    weeks: list[WeeklySummary] = []
    while cursor <= last:
        weeks.append(get_week(db, user_id, cursor))
        cursor += timedelta(days=7)
    weeks.sort(key=lambda w: w.week_start, reverse=True)
    return weeks


def get_week_bundle(db: Database, user_id: UUID, week_start: date) -> dict[str, Any]:
    """Serialisable bundle of a user's week of data.

    Phase 2 will feed this into the Claude API as context; keeping it as one
    clean service function now means the AI layer needs no new queries.
    """
    from app.services import entries as entries_service

    week_end = week_start + timedelta(days=6)
    days = []
    cursor = week_start
    while cursor <= week_end:
        entry = entries_service.get_entry(db, user_id, cursor)
        if entry is not None:
            days.append(entry.model_dump(mode="json"))
        cursor += timedelta(days=1)
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "summary": get_week(db, user_id, week_start).model_dump(mode="json"),
        "days": days,
    }
