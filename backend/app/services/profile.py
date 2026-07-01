"""Patient background profile: one row per user."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.records import PatientProfile, PatientProfileIn

_FIELDS = ("dob", "sex", "height_cm", "weight_kg", "lifestyle", "medical_history")


def get_profile(db: Database, user_id: UUID) -> PatientProfile:
    row = db.query_one("SELECT * FROM patient_profile WHERE user_id = ?", [user_id])
    if row is None:
        return PatientProfile()
    return PatientProfile(**{k: row[k] for k in _FIELDS})


def save_profile(db: Database, user_id: UUID, data: PatientProfileIn) -> PatientProfile:
    with db.cursor():
        db.execute(
            """
            INSERT INTO patient_profile
                (user_id, dob, sex, height_cm, weight_kg, lifestyle, medical_history, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f','now'))
            ON CONFLICT (user_id) DO UPDATE SET
                dob = excluded.dob,
                sex = excluded.sex,
                height_cm = excluded.height_cm,
                weight_kg = excluded.weight_kg,
                lifestyle = excluded.lifestyle,
                medical_history = excluded.medical_history,
                updated_at = excluded.updated_at
            """,
            [user_id, data.dob, data.sex, data.height_cm, data.weight_kg,
             data.lifestyle, data.medical_history],
        )
    return get_profile(db, user_id)
