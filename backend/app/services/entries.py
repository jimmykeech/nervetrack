"""Daily entry business logic. All access is scoped to a user_id."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app.db import Database
from app.models.entries import (
    DailyEntry,
    DailyEntrySummary,
    DailyEntryUpsert,
    PainEvent,
    PostureTotals,
)
from app.services import sessions as sessions_service
from app.services import timer as timer_service
from app.services.timeutil import now_utc

# Columns the upsert path may write.
_UPSERT_COLUMNS = (
    "status",
    "strengthening_done",
    "session_intensity",
    "sharp_pain_episodes",
    "worst_pain",
    "tingling_level",
    "tingling_duration_minutes",
    "stretches_morning",
    "stretches_night",
    "sitting_breaks",
    "sleep_quality",
    "iced",
    "notes",
)


def ensure_entry(db: Database, user_id: UUID, entry_date: date) -> UUID:
    """Return the id of the user's entry for ``entry_date``, creating one if needed."""
    row = db.query_one(
        "SELECT id FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, entry_date],
    )
    if row:
        return row["id"]
    created = db.query_one(
        "INSERT INTO daily_entries (user_id, entry_date) VALUES (?, ?) RETURNING id",
        [user_id, entry_date],
    )
    assert created is not None
    return created["id"]


def upsert_entry(
    db: Database, user_id: UUID, entry_date: date, data: DailyEntryUpsert
) -> DailyEntry:
    fields = data.model_dump(exclude_unset=True)
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        if fields:
            assignments = ", ".join(f"{col} = ?" for col in fields if col in _UPSERT_COLUMNS)
            params: list[Any] = [fields[col] for col in fields if col in _UPSERT_COLUMNS]
            if assignments:
                db.execute(
                    f"UPDATE daily_entries SET {assignments}, updated_at = ? WHERE id = ?",
                    [*params, now_utc(), entry_id],
                )
    detail = get_entry(db, user_id, entry_date)
    assert detail is not None
    return detail


def list_entries(
    db: Database, user_id: UUID, date_from: date | None, date_to: date | None
) -> list[DailyEntrySummary]:
    where = ["user_id = ?"]
    params: list[Any] = [user_id]
    if date_from:
        where.append("entry_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("entry_date <= ?")
        params.append(date_to)
    rows = db.query(
        f"""
        SELECT entry_date, status, strengthening_done, session_intensity,
               sharp_pain_episodes, worst_pain, tingling_level, sleep_quality, iced
        FROM daily_entries
        WHERE {' AND '.join(where)}
        ORDER BY entry_date DESC
        """,
        params,
    )
    return [DailyEntrySummary(**r) for r in rows]


def get_entry(db: Database, user_id: UUID, entry_date: date) -> DailyEntry | None:
    row = db.query_one(
        "SELECT * FROM daily_entries WHERE user_id = ? AND entry_date = ?",
        [user_id, entry_date],
    )
    if not row:
        return None
    events = [
        PainEvent(**e)
        for e in db.query(
            "SELECT * FROM pain_events WHERE daily_entry_id = ? ORDER BY occurred_at",
            [row["id"]],
        )
    ]
    session = sessions_service.get_session_for_entry(db, row["id"])
    totals = timer_service.posture_totals(db, user_id, entry_date)
    return DailyEntry(
        **row,
        pain_events=events,
        session=session,
        timer_totals=PostureTotals(**totals),
    )


def add_pain_event(
    db: Database, user_id: UUID, entry_date: date, occurred_at, pain_level, context
) -> PainEvent:
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        occurred = occurred_at or now_utc()
        created = db.query_one(
            """
            INSERT INTO pain_events (daily_entry_id, occurred_at, pain_level, context)
            VALUES (?, ?, ?, ?)
            RETURNING *
            """,
            [entry_id, occurred, pain_level, context],
        )
        # Keep the day's summary count and worst-pain consistent with logged events.
        _recompute_pain_summary(db, entry_id)
    assert created is not None
    return PainEvent(**created)


def delete_pain_event(db: Database, user_id: UUID, event_id: UUID) -> bool:
    # Verify ownership via the parent daily entry.
    row = db.query_one(
        """
        SELECT pe.daily_entry_id
        FROM pain_events pe
        JOIN daily_entries d ON d.id = pe.daily_entry_id
        WHERE pe.id = ? AND d.user_id = ?
        """,
        [event_id, user_id],
    )
    if not row:
        return False
    with db.cursor():
        db.execute("DELETE FROM pain_events WHERE id = ?", [event_id])
        _recompute_pain_summary(db, row["daily_entry_id"])
    return True


def _recompute_pain_summary(db: Database, entry_id: UUID) -> None:
    agg = db.query_one(
        "SELECT COUNT(*) AS n, MAX(pain_level) AS worst FROM pain_events WHERE daily_entry_id = ?",
        [entry_id],
    )
    assert agg is not None
    db.execute(
        "UPDATE daily_entries SET sharp_pain_episodes = ?, worst_pain = ?, updated_at = ? "
        "WHERE id = ?",
        [agg["n"], agg["worst"], now_utc(), entry_id],
    )
