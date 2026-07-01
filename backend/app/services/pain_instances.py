"""Pain instance catalogue logic (mirrors the exercises catalogue pattern)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db import Database
from app.models.pain_instances import PainInstance, PainInstanceCreate, PainInstancePatch


def list_instances(db: Database, user_id: UUID) -> list[PainInstance]:
    rows = db.query(
        "SELECT * FROM pain_instances WHERE user_id = ? ORDER BY sort_order, name", [user_id]
    )
    return [PainInstance(**r) for r in rows]


def create_instance(db: Database, user_id: UUID, data: PainInstanceCreate) -> PainInstance:
    existing = db.query_one(
        "SELECT id FROM pain_instances WHERE user_id = ? AND lower(name) = lower(?)",
        [user_id, data.name],
    )
    if existing:
        raise ValueError("Pain instance already exists")
    order = data.sort_order
    if order is None:
        row = db.query_one(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM pain_instances WHERE user_id = ?",
            [user_id],
        )
        order = row["n"]
    created = db.query_one(
        """
        INSERT INTO pain_instances (user_id, name, body_region, background, active, sort_order)
        VALUES (?, ?, ?, ?, TRUE, ?)
        RETURNING *
        """,
        [user_id, data.name, data.body_region, data.background, order],
    )
    assert created is not None
    return PainInstance(**created)


def patch_instance(
    db: Database, user_id: UUID, instance_id: UUID, data: PainInstancePatch
) -> PainInstance | None:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        existing = db.query_one(
            "SELECT * FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
        )
        return PainInstance(**existing) if existing else None
    assignments = ", ".join(f"{k} = ?" for k in fields)
    params: list[Any] = [*fields.values(), instance_id, user_id]
    updated = db.query_one(
        f"UPDATE pain_instances SET {assignments} WHERE id = ? AND user_id = ? RETURNING *",
        params,
    )
    return PainInstance(**updated) if updated else None


def validate_instances(db: Database, user_id: UUID, instance_ids: list[UUID]) -> None:
    """Ensure every referenced instance belongs to the user."""
    for iid in set(instance_ids):
        owned = db.query_one(
            "SELECT 1 AS ok FROM pain_instances WHERE id = ? AND user_id = ?", [iid, user_id]
        )
        if not owned:
            raise ValueError(f"Pain instance {iid} does not belong to this account")
