"""Reusable workout schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator


class WorkoutExercise(BaseModel):
    exercise_id: UUID
    exercise_name: str | None = None
    sets: int | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    hold_seconds: int | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    modification: str | None = None


class WorkoutIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    exercises: list[WorkoutExercise] = Field(min_length=1)

    @field_validator("exercises")
    @classmethod
    def unique_exercises(cls, exercises: list[WorkoutExercise]) -> list[WorkoutExercise]:
        if len({exercise.exercise_id for exercise in exercises}) != len(exercises):
            raise ValueError("Each exercise can only appear once in a workout")
        return exercises


class Workout(WorkoutIn):
    id: UUID
