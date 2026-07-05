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
    Note,
    PainEvent,
)
from app.services import pain_instances as pain_instances_service
from app.services import sessions as sessions_service
from app.services import timer as timer_service
from app.services.timeutil import now_utc, to_utc_naive

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
)

# Checkbox column -> its completion-timestamp column.
_CHECKBOX_AT = {
    "strengthening_done": "strengthening_done_at",
    "stretches_morning": "stretches_morning_at",
    "stretches_night": "stretches_night_at",
    "iced": "iced_at",
}


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
        existing = db.query_one("SELECT * FROM daily_entries WHERE id = ?", [entry_id])
        assert existing is not None
        now = now_utc()
        assignments: list[str] = []
        params: list[Any] = []
        for col in fields:
            if col in _UPSERT_COLUMNS:
                assignments.append(f"{col} = ?")
                params.append(fields[col])
        for col, at_col in _CHECKBOX_AT.items():
            if col in fields:
                if fields[col] and not existing[col]:
                    assignments.append(f"{at_col} = ?")
                    params.append(now)
                elif not fields[col]:
                    assignments.append(f"{at_col} = ?")
                    params.append(None)
        if assignments:
            db.execute(
                f"UPDATE daily_entries SET {', '.join(assignments)}, updated_at = ? "
                "WHERE id = ?",
                [*params, now, entry_id],
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
        PainEvent(**e, instance_ids=_pain_event_instance_ids(db, e["id"]))
        for e in db.query(
            "SELECT * FROM pain_events WHERE daily_entry_id = ? ORDER BY occurred_at",
            [row["id"]],
        )
    ]
    notes = [
        Note(**n)
        for n in db.query(
            "SELECT * FROM notes WHERE daily_entry_id = ? ORDER BY occurred_at",
            [row["id"]],
        )
    ]
    day_timer = timer_service.day(db, user_id, entry_date)
    session = sessions_service.get_session_for_entry(db, row["id"])
    return DailyEntry(
        **row,
        pain_events=events,
        notes=notes,
        session=session,
        timer_totals=day_timer.totals,
        timer_intervals=day_timer.intervals,
    )


def _tag_pain_event(db: Database, event_id: UUID, instance_ids: list) -> None:
    for iid in dict.fromkeys(instance_ids):
        db.execute(
            "INSERT INTO pain_event_instances (pain_event_id, instance_id) VALUES (?, ?)",
            [event_id, iid],
        )


def _pain_event_instance_ids(db: Database, event_id: UUID) -> list:
    rows = db.query(
        "SELECT instance_id FROM pain_event_instances WHERE pain_event_id = ?", [event_id]
    )
    return [r["instance_id"] for r in rows]


def add_pain_event(
    db: Database,
    user_id: UUID,
    entry_date: date,
    occurred_at,
    pain_level,
    context,
    instance_ids: list | None = None,
) -> PainEvent:
    instance_ids = instance_ids or []
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        pain_instances_service.validate_instances(db, user_id, instance_ids)
        occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
        created = db.query_one(
            """
            INSERT INTO pain_events (daily_entry_id, occurred_at, pain_level, context)
            VALUES (?, ?, ?, ?)
            RETURNING *
            """,
            [entry_id, occurred, pain_level, context],
        )
        assert created is not None
        _tag_pain_event(db, created["id"], instance_ids)
        # Keep the day's summary count and worst-pain consistent with logged events.
        _recompute_pain_summary(db, entry_id)
    return PainEvent(**created, instance_ids=_pain_event_instance_ids(db, created["id"]))


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
        db.execute("DELETE FROM pain_event_instances WHERE pain_event_id = ?", [event_id])
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


def add_note(db: Database, user_id: UUID, entry_date: date, occurred_at, body: str) -> Note:
    with db.cursor():
        entry_id = ensure_entry(db, user_id, entry_date)
        occurred = to_utc_naive(occurred_at) if occurred_at else now_utc()
        created = db.query_one(
            "INSERT INTO notes (daily_entry_id, occurred_at, body) "
            "VALUES (?, ?, ?) RETURNING *",
            [entry_id, occurred, body],
        )
    assert created is not None
    return Note(**created)


def update_note(
    db: Database, user_id: UUID, note_id: UUID, body, occurred_at
) -> Note | None:
    owned = db.query_one(
        """
        SELECT n.id
        FROM notes n
        JOIN daily_entries d ON d.id = n.daily_entry_id
        WHERE n.id = ? AND d.user_id = ?
        """,
        [note_id, user_id],
    )
    if not owned:
        return None
    sets: list[str] = []
    params: list[Any] = []
    if body is not None:
        sets.append("body = ?")
        params.append(body)
    if occurred_at is not None:
        sets.append("occurred_at = ?")
        params.append(to_utc_naive(occurred_at))
    sets.append("updated_at = ?")
    params.append(now_utc())
    updated = db.query_one(
        f"UPDATE notes SET {', '.join(sets)} WHERE id = ? RETURNING *",
        [*params, note_id],
    )
    return Note(**updated) if updated else None


def delete_note(db: Database, user_id: UUID, note_id: UUID) -> bool:
    owned = db.query_one(
        """
        SELECT n.id
        FROM notes n
        JOIN daily_entries d ON d.id = n.daily_entry_id
        WHERE n.id = ? AND d.user_id = ?
        """,
        [note_id, user_id],
    )
    if not owned:
        return False
    db.execute("DELETE FROM notes WHERE id = ?", [note_id])
    return True
