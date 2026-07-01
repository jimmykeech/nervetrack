"""Pain instance catalogue: schema, CRUD, and tagging."""

from __future__ import annotations

import sqlite3

import pytest


def test_schema_creates_tables_with_fk_enforcement(db, user_id):
    created = db.query_one(
        """
        INSERT INTO pain_instances (user_id, name, body_region, background)
        VALUES (?, ?, ?, ?)
        RETURNING *
        """,
        [user_id, "Left sciatic / piriformis", "Left glute/hip", "Started March 2026"],
    )
    assert created["active"] is True
    assert created["sort_order"] == 0

    ev = db.query_one(
        "INSERT INTO daily_entries (user_id, entry_date) VALUES (?, ?) RETURNING id",
        [user_id, "2026-07-01"],
    )
    event = db.query_one(
        "INSERT INTO pain_events (daily_entry_id, occurred_at, pain_level) "
        "VALUES (?, ?, ?) RETURNING id",
        [ev["id"], "2026-07-01T10:00:00", 4],
    )
    db.execute(
        "INSERT INTO pain_event_instances (pain_event_id, instance_id) VALUES (?, ?)",
        [event["id"], created["id"]],
    )

    # Deleting the pain_event while a join row still references it must fail
    # under PRAGMA foreign_keys=ON — this is the exact hazard callers must avoid.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM pain_events WHERE id = ?", [event["id"]])


def test_name_unique_per_user(db, user_id):
    db.execute(
        "INSERT INTO pain_instances (user_id, name) VALUES (?, ?)", [user_id, "Left sciatic"]
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO pain_instances (user_id, name) VALUES (?, ?)", [user_id, "Left sciatic"]
        )
