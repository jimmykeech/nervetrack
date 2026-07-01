"""Pydantic schemas for the AI (chat + weekly-draft + settings) layer."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LlmSettingsIn(BaseModel):
    provider: str
    model: str
    # None = leave the stored key unchanged; "" = clear it; other = set it.
    api_key: str | None = None
    base_url: str | None = None


class LlmSettingsOut(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key_set: bool = False
    configured: bool = False


class ResolvedLlmConfig(BaseModel):
    """Internal: resolved config with the decrypted key, never sent to clients."""

    model: str
    api_key: str | None = None
    base_url: str | None = None


class ConversationSummary(BaseModel):
    id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    id: UUID
    role: str
    content: str | None = None
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage] = []


class ChatSendRequest(BaseModel):
    content: str


class WeeklyDraftResponse(BaseModel):
    key_observations: str
    next_steps: str
