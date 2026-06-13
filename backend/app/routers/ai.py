"""Phase 2 placeholder — AI insights over the recovery data.

Reserved now so the schema, service layer (see ``get_week_bundle``), and routing
accommodate the future Claude-powered chat without restructuring. Not wired up
in Phase 1; the ANTHROPIC_API_KEY env var is intentionally unused.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["ai"])


@router.get("/ai/status")
def ai_status() -> dict[str, str]:
    return {"status": "coming_soon", "phase": "2"}
