"""Exercise catalogue schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class Exercise(BaseModel):
    id: UUID
    name: str
    active: bool = True
    sort_order: int = 0


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=1)
    sort_order: int | None = None


class ExercisePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    active: bool | None = None
    sort_order: int | None = None
