"""Daily time-series for charts."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.db import Database
from app.models.stats import DailyStatPoint


def daily_stats(
    db: Database, user_id: UUID, date_from: date, date_to: date
) -> list[DailyStatPoint]:
    rows = db.query(
        """
        WITH posture AS (
            SELECT
                entry_date,
                CAST(COALESCE(SUM(duration_seconds) FILTER (WHERE posture='sitting'),0)/60
                     AS INTEGER) AS sitting_minutes,
                CAST(COALESCE(SUM(duration_seconds) FILTER (WHERE posture='standing'),0)/60
                     AS INTEGER) AS standing_minutes,
                CAST(COALESCE(SUM(duration_seconds) FILTER (WHERE posture='lying'),0)/60
                     AS INTEGER) AS lying_minutes,
                CAST(COALESCE(SUM(duration_seconds) FILTER (WHERE posture='walking'),0)/60
                     AS INTEGER) AS walking_minutes
            FROM sit_stand_sessions
            WHERE user_id = ?
            GROUP BY entry_date
        )
        SELECT
            d.entry_date,
            d.sharp_pain_episodes,
            d.worst_pain,
            d.tingling_level,
            d.session_intensity,
            COALESCE(p.sitting_minutes, 0) AS sitting_minutes,
            COALESCE(p.standing_minutes, 0) AS standing_minutes,
            COALESCE(p.lying_minutes, 0) AS lying_minutes,
            COALESCE(p.walking_minutes, 0) AS walking_minutes
        FROM daily_entries d
        LEFT JOIN posture p ON p.entry_date = d.entry_date
        WHERE d.user_id = ? AND d.entry_date >= ? AND d.entry_date <= ?
        ORDER BY d.entry_date
        """,
        [user_id, user_id, date_from, date_to],
    )
    return [DailyStatPoint(**r) for r in rows]
