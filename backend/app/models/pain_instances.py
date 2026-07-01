"""Pain instance catalogue schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PainInstance(BaseModel):
    id: UUID
    name: str
    body_region: str | None = None
    background: str | None = None
    active: bool = True
    sort_order: int = 0


class PainInstanceCreate(BaseModel):
    name: str = Field(min_length=1)
    body_region: str | None = None
    background: str | None = None
    sort_order: int | None = None


class PainInstancePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    body_region: str | None = None
    background: str | None = None
    active: bool | None = None
    sort_order: int | None = None
