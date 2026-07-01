"""Schemas for the Records feature: patient profile, condition notes, documents."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.pain_instances import PainInstance


class PatientProfile(BaseModel):
    dob: date | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    lifestyle: str | None = None
    medical_history: str | None = None


class PatientProfileIn(PatientProfile):
    """Same optional fields; used as the PUT body."""


class ConditionNoteIn(BaseModel):
    body: str = Field(min_length=1)
    occurred_at: datetime | None = None


class ConditionNoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1)
    occurred_at: datetime | None = None


class ConditionNote(BaseModel):
    id: UUID
    instance_id: UUID
    occurred_at: datetime
    body: str
    created_at: datetime | None = None


class DocumentMeta(BaseModel):
    id: UUID
    owner_type: str
    instance_id: UUID | None = None
    title: str
    notes: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    notes: str | None = None


class ConditionDetail(BaseModel):
    instance: PainInstance
    notes: list[ConditionNote] = []
    documents: list[DocumentMeta] = []
