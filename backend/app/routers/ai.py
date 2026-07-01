"""AI endpoints: per-user provider settings, chat threads (SSE streaming over
the tool-calling loop), and the weekly-review drafter."""

from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.auth import current_user
from app.deps import db_dep
from app.models.ai import (
    ChatSendRequest,
    ConversationDetail,
    ConversationSummary,
    LlmSettingsIn,
    LlmSettingsOut,
    WeeklyDraftResponse,
)
from app.services import ai_tools, conversations, llm, llm_settings
from app.services import weekly as weekly_service

router = APIRouter(tags=["ai"])


@router.get("/ai/settings", response_model=LlmSettingsOut)
def get_settings_endpoint(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return llm_settings.get_settings_out(db, user_id)


@router.put("/ai/settings", response_model=LlmSettingsOut)
def put_settings(
    data: LlmSettingsIn, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    return llm_settings.save_settings(db, user_id, data)


@router.get("/ai/conversations", response_model=list[ConversationSummary])
def list_convs(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return conversations.list_conversations(db, user_id)


@router.post("/ai/conversations", response_model=ConversationSummary)
def new_conv(db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    return conversations.create_conversation(db, user_id)


@router.get("/ai/conversations/{conv_id}", response_model=ConversationDetail)
def get_conv(conv_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    detail = conversations.get_conversation(db, user_id, conv_id)
    if detail is None:
        raise HTTPException(404, "conversation not found")
    return detail


@router.delete("/ai/conversations/{conv_id}", status_code=204)
def del_conv(conv_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    if not conversations.delete_conversation(db, user_id, conv_id):
        raise HTTPException(404, "conversation not found")


@router.post("/ai/conversations/{conv_id}/messages")
async def send_message(
    conv_id: UUID,
    body: ChatSendRequest,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    if not conversations.owns(db, user_id, conv_id):
        raise HTTPException(404, "conversation not found")
    config = llm_settings.resolve_config(db, user_id)
    if config is None:
        raise HTTPException(409, "llm_not_configured")

    # Short write txn: persist the user's turn + title the thread if it's new.
    conversations.add_message(db, conv_id, "user", body.content)
    detail = conversations.get_conversation(db, user_id, conv_id)
    if detail is not None and not detail.title:
        title = body.content.strip()[:60] or "New chat"
        with db.cursor():
            db.execute("UPDATE conversations SET title = ? WHERE id = ?", [title, conv_id])

    history = conversations.history_for_llm(db, conv_id)

    def run_tool(name: str, args: dict):
        # Runs synchronous DB reads in short transactions, scoped to this user.
        return ai_tools.dispatch(db, user_id, name, args)

    async def event_stream():
        final_content = ""
        async for event in llm.stream_chat(config, history, run_tool):
            if event["type"] == "final":
                final_content = event["content"]
            yield f"data: {json.dumps(event)}\n\n"
        # Short write txn after the stream completes — no lock held while streaming.
        await run_in_threadpool(
            conversations.add_message, db, conv_id, "assistant", final_content
        )
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/ai/weekly-draft/{week_start}", response_model=WeeklyDraftResponse)
async def weekly_draft(
    week_start: date, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    config = llm_settings.resolve_config(db, user_id)
    if config is None:
        raise HTTPException(409, "llm_not_configured")
    bundle = weekly_service.get_week_bundle(db, user_id, week_start)
    return await llm.draft_weekly(config, bundle)
