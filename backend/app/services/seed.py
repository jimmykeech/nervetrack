"""Per-user reference data, seeded when an account is first created."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.db import Database

# Exercise catalogue from the original spreadsheet, in display order.
EXERCISE_SEED: list[str] = [
    "Glute Bridges",
    "Clamshells",
    "Side-Lying Hip Abduction",
    "Standing Hip Hinge",
    "Goblet Squats",
    "Step-Ups",
    "Dead Bug",
    "Bird Dog",
    "Dumbbell Rows",
    "Forearm Plank",
    "Side Plank",
    "Hollowbody Hold",
    "Pelvic Tilts",
    "Dumbbell Curls",
]

# Default app settings. Week start day: 4 = Friday (Mon=0).
SETTINGS_SEED: dict[str, str] = {
    "week_start_day": "4",
    "timezone": "Australia/Sydney",
    "sitting_nudge_minutes": "45",
}


def seed_user(db: Database, user_id: UUID) -> None:
    """Seed a new account with the exercise catalogue and default settings."""
    with db.cursor():
        for order, name in enumerate(EXERCISE_SEED):
            db.execute(
                """
                INSERT INTO exercises (id, user_id, name, active, sort_order)
                VALUES (gen_random_uuid(), ?, ?, TRUE, ?)
                ON CONFLICT (user_id, name) DO NOTHING
                """,
                [user_id, name, order],
            )
        for key, value in SETTINGS_SEED.items():
            db.execute(
                """
                INSERT INTO app_settings (user_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT (user_id, key) DO NOTHING
                """,
                [user_id, key, value],
            )
