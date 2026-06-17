"""Posture totals shared by entries and timer models."""

from __future__ import annotations

from pydantic import BaseModel


class PostureTotals(BaseModel):
    sitting: int = 0
    standing: int = 0
    lying: int = 0
    walking: int = 0
