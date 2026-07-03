"""Read-only tools the LLM may call, plus a user-scoped dispatcher.

Every tool executes with the session ``user_id`` injected by the caller; any
``user_id`` the model puts in the arguments is ignored, so the model cannot read
another account's data. Results are JSON-serialisable (dicts/lists).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app.db import Database
from app.services import condition_notes as condition_notes_service
from app.services import documents as documents_service
from app.services import entries as entries_service
from app.services import pain_instances as pain_instances_service
from app.services import sessions as sessions_service
from app.services import stats as stats_service
from app.services import timer as timer_service
from app.services import weekly as weekly_service

_DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}
_RANGE = {
    "type": "object",
    "properties": {"from": _DATE, "to": _DATE},
    "required": ["from", "to"],
}

TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {
        "name": "list_weeks",
        "description": "List all tracking weeks (start/end + computed stats) newest first.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_week_summary",
        "description": "Full data bundle for one week: daily entries, pain events, "
                       "sessions, and timer aggregates.",
        "parameters": {"type": "object", "properties": {"week_start": _DATE},
                       "required": ["week_start"]},
    }},
    {"type": "function", "function": {
        "name": "get_daily_entry",
        "description": "One day in full: metrics, pain events, note log, session, "
                       "and sit/stand timer intervals.",
        "parameters": {"type": "object", "properties": {"date": _DATE}, "required": ["date"]},
    }},
    {"type": "function", "function": {
        "name": "get_daily_entries",
        "description": "Daily summary rows over a date range (inclusive).",
        "parameters": _RANGE,
    }},
    {"type": "function", "function": {
        "name": "get_pain_events",
        "description": "All pain/flare events (with context) over a date range.",
        "parameters": _RANGE,
    }},
    {"type": "function", "function": {
        "name": "get_timer_day",
        "description": "The sit/stand/lying/walking interval timeline for one day.",
        "parameters": {"type": "object", "properties": {"date": _DATE}, "required": ["date"]},
    }},
    {"type": "function", "function": {
        "name": "get_posture_totals",
        "description": "Per-posture minute totals per day over a date range.",
        "parameters": _RANGE,
    }},
    {"type": "function", "function": {
        "name": "get_tingling_totals",
        "description": "Per-day tingling: highest level and total minutes over a date range.",
        "parameters": _RANGE,
    }},
    {"type": "function", "function": {
        "name": "get_strengthening_sessions",
        "description": "Strengthening/exercise session logs over a date range.",
        "parameters": _RANGE,
    }},
    {"type": "function", "function": {
        "name": "get_stats",
        "description": "Daily stat points (pain, tingling, posture minutes) for charts "
                       "over a date range.",
        "parameters": _RANGE,
    }},
    {"type": "function", "function": {
        "name": "list_pain_instances",
        "description": "The user's catalogue of named nerve-pain issues (id, name, body "
                       "region, background). Use it to resolve the instance_ids tagged on "
                       "pain events and sessions to human-readable names.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_condition_notes",
        "description": "The dated notes log for one condition (pain instance), newest first.",
        "parameters": {"type": "object", "properties": {"instance_id": {
            "type": "string", "description": "pain instance UUID"}},
            "required": ["instance_id"]},
    }},
    {"type": "function", "function": {
        "name": "list_documents",
        "description": "The user's supporting documents (medical reports/imaging) as metadata: "
                       "title, the user's notes/summary, which condition (if any), and filename. "
                       "The file contents are NOT available.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def dispatch(db: Database, user_id: UUID, name: str, arguments: dict[str, Any]) -> Any:
    a = arguments or {}
    if name == "list_weeks":
        return [w.model_dump(mode="json") for w in weekly_service.list_weeks(db, user_id)]
    if name == "get_week_summary":
        return weekly_service.get_week_bundle(db, user_id, _d(a["week_start"]))
    if name == "get_daily_entry":
        entry = entries_service.get_entry(db, user_id, _d(a["date"]))
        return entry.model_dump(mode="json") if entry else None
    if name == "get_daily_entries":
        rows = entries_service.list_entries(db, user_id, _d(a["from"]), _d(a["to"]))
        return [r.model_dump(mode="json") for r in rows]
    if name == "get_pain_events":
        return _pain_events(db, user_id, _d(a["from"]), _d(a["to"]))
    if name == "get_timer_day":
        return timer_service.day(db, user_id, _d(a["date"])).model_dump(mode="json")
    if name == "get_posture_totals":
        return _posture_totals(db, user_id, _d(a["from"]), _d(a["to"]))
    if name == "get_tingling_totals":
        return _tingling_totals(db, user_id, _d(a["from"]), _d(a["to"]))
    if name == "get_strengthening_sessions":
        return _sessions(db, user_id, _d(a["from"]), _d(a["to"]))
    if name == "get_stats":
        pts = stats_service.daily_stats(db, user_id, _d(a["from"]), _d(a["to"]))
        return [p.model_dump(mode="json") for p in pts]
    if name == "list_pain_instances":
        instances = pain_instances_service.list_instances(db, user_id)
        return [i.model_dump(mode="json") for i in instances]
    if name == "get_condition_notes":
        notes = condition_notes_service.list_notes(db, user_id, UUID(a["instance_id"]))
        return [n.model_dump(mode="json") for n in notes]
    if name == "list_documents":
        return [d.model_dump(mode="json") for d in documents_service.list_documents(db, user_id)]
    raise ValueError(f"unknown tool: {name}")


def _pain_events(db: Database, user_id: UUID, lo: date, hi: date) -> list[dict]:
    rows = db.query(
        """
        SELECT pe.id, d.entry_date, pe.occurred_at, pe.pain_level, pe.context
        FROM pain_events pe
        JOIN daily_entries d ON d.id = pe.daily_entry_id
        WHERE d.user_id = ? AND d.entry_date >= ? AND d.entry_date <= ?
        ORDER BY pe.occurred_at
        """,
        [user_id, lo, hi],
    )
    # Attach the pain-instance tags each event carries (PR #11). Low-volume range,
    # so a per-row lookup is fine; resolve names via list_pain_instances.
    for r in rows:
        tags = db.query(
            "SELECT instance_id FROM pain_event_instances WHERE pain_event_id = ?", [r["id"]]
        )
        r["instance_ids"] = [t["instance_id"] for t in tags]
        del r["id"]
    return rows


def _posture_totals(db: Database, user_id: UUID, lo: date, hi: date) -> list[dict]:
    return db.query(
        """
        SELECT entry_date, posture,
               CAST(SUM(duration_seconds) / 60 AS INTEGER) AS minutes
        FROM sit_stand_sessions
        WHERE user_id = ? AND entry_date >= ? AND entry_date <= ? AND ended_at IS NOT NULL
        GROUP BY entry_date, posture
        ORDER BY entry_date
        """,
        [user_id, lo, hi],
    )


def _tingling_totals(db: Database, user_id: UUID, lo: date, hi: date) -> list[dict]:
    return db.query(
        """
        SELECT entry_date,
               MAX(level) AS max_level,
               CAST(SUM(duration_seconds) / 60 AS INTEGER) AS minutes
        FROM tingling_sessions
        WHERE user_id = ? AND entry_date >= ? AND entry_date <= ? AND ended_at IS NOT NULL
        GROUP BY entry_date
        ORDER BY entry_date
        """,
        [user_id, lo, hi],
    )


def _sessions(db: Database, user_id: UUID, lo: date, hi: date) -> list[dict]:
    rows = db.query(
        "SELECT id FROM strength_sessions WHERE user_id = ? AND entry_date >= ? "
        "AND entry_date <= ? ORDER BY entry_date",
        [user_id, lo, hi],
    )
    out = []
    for r in rows:
        detail = sessions_service.get_session(db, user_id, r["id"])
        if detail is not None:
            out.append(detail.model_dump(mode="json"))
    return out
