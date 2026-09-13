"""User-owned reusable workout plans."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.workouts import Workout, WorkoutExercise, WorkoutIn


def _hydrate(db: Database, row: dict) -> Workout:
    exercises = db.query(
        """
        SELECT we.*, e.name AS exercise_name
        FROM workout_exercises we
        JOIN exercises e ON e.id = we.exercise_id
        WHERE we.workout_id = ?
        ORDER BY we.sort_order
        """,
        [row["id"]],
    )
    return Workout(**row, exercises=[WorkoutExercise(**exercise) for exercise in exercises])


def list_workouts(db: Database, user_id: UUID) -> list[Workout]:
    rows = db.query(
        "SELECT * FROM workouts WHERE user_id = ? ORDER BY lower(name), id", [user_id]
    )
    return [_hydrate(db, row) for row in rows]


def _validate_exercises(db: Database, user_id: UUID, exercises: list[WorkoutExercise]) -> None:
    for exercise in exercises:
        owned = db.query_one(
            "SELECT 1 AS ok FROM exercises WHERE id = ? AND user_id = ?",
            [exercise.exercise_id, user_id],
        )
        if not owned:
            raise ValueError(f"Exercise {exercise.exercise_id} does not belong to this account")


def _insert_exercises(db: Database, workout_id: UUID, exercises: list[WorkoutExercise]) -> None:
    for position, exercise in enumerate(exercises):
        db.execute(
            """
            INSERT INTO workout_exercises
                (workout_id, exercise_id, sort_order, sets, reps, hold_seconds,
                 weight_kg, modification, superset_group)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                workout_id,
                exercise.exercise_id,
                position,
                exercise.sets,
                exercise.reps,
                exercise.hold_seconds,
                exercise.weight_kg,
                exercise.modification,
                exercise.superset_group,
            ],
        )


def create_workout(db: Database, user_id: UUID, data: WorkoutIn) -> Workout:
    with db.cursor():
        _validate_exercises(db, user_id, data.exercises)
        row = db.query_one(
            "INSERT INTO workouts (user_id, name) VALUES (?, ?) RETURNING *",
            [user_id, data.name],
        )
        assert row is not None
        _insert_exercises(db, row["id"], data.exercises)
    return _hydrate(db, row)


def update_workout(
    db: Database, user_id: UUID, workout_id: UUID, data: WorkoutIn
) -> Workout | None:
    with db.cursor():
        existing = db.query_one(
            "SELECT * FROM workouts WHERE id = ? AND user_id = ?", [workout_id, user_id]
        )
        if not existing:
            return None
        _validate_exercises(db, user_id, data.exercises)
        row = db.query_one(
            "UPDATE workouts SET name = ? WHERE id = ? AND user_id = ? RETURNING *",
            [data.name, workout_id, user_id],
        )
        assert row is not None
        db.execute("DELETE FROM workout_exercises WHERE workout_id = ?", [workout_id])
        _insert_exercises(db, workout_id, data.exercises)
    return _hydrate(db, row)


def delete_workout(db: Database, user_id: UUID, workout_id: UUID) -> bool:
    row = db.query_one(
        "DELETE FROM workouts WHERE id = ? AND user_id = ? RETURNING id", [workout_id, user_id]
    )
    return row is not None
