"""Strengthening session and exercise log schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ExerciseLogIn(BaseModel):
    exercise_id: UUID
    sets: int | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    hold_seconds: int | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    difficulty: Decimal | None = Field(default=None, ge=1, le=10)
    nerve_response: str | None = None
    modification: str | None = None
    superset_group: int | None = Field(default=None, ge=1)


class ExerciseLog(ExerciseLogIn):
    id: UUID
    session_id: UUID
    exercise_name: str | None = None


class SessionIn(BaseModel):
    performed_at: datetime | None = None
    intensity: Decimal | None = Field(default=None, ge=1, le=10)
    notes: str | None = None
    logs: list[ExerciseLogIn] = Field(default_factory=list)
    instance_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def supersets_have_multiple_exercises(self) -> SessionIn:
        counts: dict[int, int] = {}
        for log in self.logs:
            if log.superset_group is not None:
                counts[log.superset_group] = counts.get(log.superset_group, 0) + 1
        if any(count < 2 for count in counts.values()):
            raise ValueError("Each superset must contain at least two exercises")
        return self


class SessionDetail(BaseModel):
    id: UUID
    daily_entry_id: UUID
    performed_at: datetime
    intensity: Decimal | None = None
    notes: str | None = None
    logs: list[ExerciseLog] = Field(default_factory=list)
    instance_ids: list[UUID] = Field(default_factory=list)
