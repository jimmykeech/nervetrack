"""Compact patient/condition context injected into every LLM request."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.services import pain_instances as pain_instances_service
from app.services import profile as profile_service


def build(db: Database, user_id: UUID) -> str:
    p = profile_service.get_profile(db, user_id)
    lines: list[str] = []

    bg: list[str] = []
    if p.dob:
        bg.append(f"DOB: {p.dob.isoformat()}")
    if p.sex:
        bg.append(f"Sex: {p.sex}")
    if p.height_cm is not None:
        bg.append(f"Height: {p.height_cm} cm")
    if p.weight_kg is not None:
        bg.append(f"Weight: {p.weight_kg} kg")
    if bg or p.lifestyle or p.medical_history:
        lines.append("PATIENT BACKGROUND:")
        if bg:
            lines.append("- " + "; ".join(bg))
        if p.lifestyle:
            lines.append(f"- Lifestyle: {p.lifestyle}")
        if p.medical_history:
            lines.append(f"- Medical history: {p.medical_history}")

    conditions = [c for c in pain_instances_service.list_instances(db, user_id) if c.active]
    if conditions:
        lines.append("CONDITIONS:")
        for c in conditions:
            region = f" ({c.body_region})" if c.body_region else ""
            details = f": {c.background}" if c.background else ""
            lines.append(f"- {c.name}{region}{details}")

    return "\n".join(lines)
