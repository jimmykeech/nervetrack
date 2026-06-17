"""Note log schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    body: str = Field(min_length=1)
    occurred_at: datetime | None = None


class NoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1)
    occurred_at: datetime | None = None


class Note(BaseModel):
    id: UUID
    daily_entry_id: UUID
    occurred_at: datetime
    body: str
    source: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
