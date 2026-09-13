"""Saved workouts retain planned exercises without changing logged sessions."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.workouts import WorkoutIn
from app.services import workouts as service


def test_workout_crud_preserves_order_and_session_independence(auth_client, db):
    exercises = auth_client.get("/api/v1/exercises").json()[:2]
    payload = {
        "name": "  Recovery A  ",
        "exercises": [
            {
                "exercise_id": exercises[1]["id"],
                "sets": 3,
                "reps": 12,
                "hold_seconds": 5,
                "weight_kg": "2.5",
                "modification": "Use a band",
            },
            {"exercise_id": exercises[0]["id"]},
        ],
    }
    created = auth_client.post("/api/v1/workouts", json=payload)
    assert created.status_code == 201
    workout = created.json()
    assert workout["name"] == "Recovery A"
    assert [ex["exercise_id"] for ex in workout["exercises"]] == [
        exercises[1]["id"], exercises[0]["id"],
    ]
    assert workout["exercises"][0]["exercise_name"] == exercises[1]["name"]
    for key in ("sets", "reps", "hold_seconds", "modification"):
        assert workout["exercises"][0][key] == payload["exercises"][0][key]
    assert Decimal(workout["exercises"][0]["weight_kg"]) == Decimal("2.5")
    assert workout["exercises"][1]["sets"] is None
    assert auth_client.get("/api/v1/workouts").json() == [workout]
    assert db.query_one("SELECT COUNT(*) AS n FROM strength_sessions")["n"] == 0
    assert db.query_one("SELECT COUNT(*) AS n FROM daily_entries")["n"] == 0

    logged = auth_client.post(
        "/api/v1/entries/2026-09-08/session",
        json={"logs": [{**ex, "difficulty": 4} for ex in workout["exercises"]]},
    )
    assert logged.status_code == 201
    session = logged.json()
    changed = {"name": "Recovery B", "exercises": [{"exercise_id": exercises[0]["id"], "sets": 5}]}
    updated = auth_client.put(f"/api/v1/workouts/{workout['id']}", json=changed)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Recovery B"
    assert len(updated.json()["exercises"]) == 1
    assert updated.json()["exercises"][0]["sets"] == 5
    assert auth_client.get("/api/v1/entries/2026-09-08/sessions").json() == [session]
    assert auth_client.delete(f"/api/v1/workouts/{workout['id']}").status_code == 204
    assert auth_client.get("/api/v1/workouts").json() == []
    assert db.query_one("SELECT COUNT(*) AS n FROM workout_exercises")["n"] == 0
    assert auth_client.get("/api/v1/entries/2026-09-08/sessions").json() == [session]
    assert auth_client.delete(f"/api/v1/workouts/{workout['id']}").status_code == 404


@pytest.mark.parametrize("change", [
    {"name": "  "},
    {"name": "x" * 201},
    {"exercises": []},
    {"sets": -1},
    {"reps": -1},
    {"hold_seconds": -1},
    {"weight_kg": "-0.1"},
    {"sets": 1.5},
    {"duplicate": True},
])
def test_workout_rejects_invalid_plan(auth_client, change):
    exercise_id = auth_client.get("/api/v1/exercises").json()[0]["id"]
    payload = {"name": "Recovery", "exercises": [{"exercise_id": exercise_id}]}
    if "name" in change or "exercises" in change:
        payload.update(change)
    elif "duplicate" in change:
        payload["exercises"] *= 2
    else:
        payload["exercises"][0].update(change)
    assert auth_client.post("/api/v1/workouts", json=payload).status_code == 422
    assert auth_client.get("/api/v1/workouts").json() == []


def test_workouts_are_user_scoped_and_validate_exercises(auth_client, db, make_user):
    other = make_user()
    foreign_exercise = db.query_one("SELECT id FROM exercises WHERE user_id = ?", [other])["id"]
    foreign_plan = WorkoutIn(name="Other plan", exercises=[{"exercise_id": foreign_exercise}])
    foreign_workout = service.create_workout(db, other, foreign_plan)
    assert auth_client.get("/api/v1/workouts").json() == []
    assert auth_client.put(
        f"/api/v1/workouts/{foreign_workout.id}", json=foreign_plan.model_dump(mode="json")
    ).status_code == 404
    assert auth_client.delete(f"/api/v1/workouts/{foreign_workout.id}").status_code == 404

    own_exercise = auth_client.get("/api/v1/exercises").json()[0]["id"]
    plan = {"name": "Own plan", "exercises": [{"exercise_id": own_exercise}]}
    created = auth_client.post("/api/v1/workouts", json=plan).json()
    for invalid_id in [foreign_exercise, uuid4()]:
        invalid = {"name": "Invalid", "exercises": [{"exercise_id": str(invalid_id)}]}
        assert auth_client.post("/api/v1/workouts", json=invalid).status_code == 422
        assert auth_client.put(f"/api/v1/workouts/{created['id']}", json=invalid).status_code == 422
        assert auth_client.get("/api/v1/workouts").json() == [created]
    assert service.list_workouts(db, other) == [foreign_workout]


def test_workout_preserves_multiple_supersets(auth_client):
    exercises = auth_client.get("/api/v1/exercises").json()[:5]
    payload = {
        "name": "Two supersets",
        "exercises": [
            {"exercise_id": exercise["id"], "superset_group": group}
            for exercise, group in zip(exercises, [1, 1, 2, 2, None], strict=True)
        ],
    }
    created = auth_client.post("/api/v1/workouts", json=payload)
    assert created.status_code == 201
    assert [item["superset_group"] for item in created.json()["exercises"]] == [1, 1, 2, 2, None]

    invalid = {
        "name": "Incomplete superset",
        "exercises": [{"exercise_id": exercises[0]["id"], "superset_group": 1}],
    }
    rejected = auth_client.post("/api/v1/workouts", json=invalid)
    assert rejected.status_code == 422
    assert "at least two exercises" in rejected.text


def test_workout_can_reuse_owned_inactive_exercise(auth_client):
    exercise_id = auth_client.get("/api/v1/exercises").json()[0]["id"]
    assert auth_client.patch(
        f"/api/v1/exercises/{exercise_id}", json={"active": False}
    ).status_code == 200
    response = auth_client.post(
        "/api/v1/workouts",
        json={"name": "Archived routine", "exercises": [{"exercise_id": exercise_id}]},
    )
    assert response.status_code == 201
    assert auth_client.get("/api/v1/workouts").json() == [response.json()]
