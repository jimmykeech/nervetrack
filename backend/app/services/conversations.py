"""Chat thread + message persistence, scoped per user."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.ai import ChatMessage, ConversationDetail, ConversationSummary


def create_conversation(
    db: Database, user_id: UUID, title: str | None = None
) -> ConversationSummary:
    with db.cursor():
        row = db.query_one(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?) "
            "RETURNING id, title, created_at, updated_at",
            [user_id, title],
        )
    return ConversationSummary(**row)


def list_conversations(db: Database, user_id: UUID) -> list[ConversationSummary]:
    rows = db.query(
        "SELECT id, title, created_at, updated_at FROM conversations "
        "WHERE user_id = ? ORDER BY updated_at DESC",
        [user_id],
    )
    return [ConversationSummary(**r) for r in rows]


def owns(db: Database, user_id: UUID, conv_id: UUID) -> bool:
    return db.query_one(
        "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", [conv_id, user_id]
    ) is not None


def get_conversation(
    db: Database, user_id: UUID, conv_id: UUID
) -> ConversationDetail | None:
    head = db.query_one(
        "SELECT id, title, created_at, updated_at FROM conversations "
        "WHERE id = ? AND user_id = ?",
        [conv_id, user_id],
    )
    if head is None:
        return None
    msgs = db.query(
        "SELECT id, role, content, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY created_at",
        [conv_id],
    )
    return ConversationDetail(**head, messages=[ChatMessage(**m) for m in msgs])


def delete_conversation(db: Database, user_id: UUID, conv_id: UUID) -> bool:
    with db.cursor() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?", [conv_id, user_id]
        )
        return cur.rowcount > 0


def add_message(
    db: Database,
    conv_id: UUID,
    role: str,
    content: str | None,
    tool_calls_json: str | None = None,
) -> UUID:
    with db.cursor():
        row = db.query_one(
            "INSERT INTO messages (conversation_id, role, content, tool_calls_json) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            [conv_id, role, content, tool_calls_json],
        )
        db.execute(
            "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%f','now') "
            "WHERE id = ?",
            [conv_id],
        )
    return row["id"]


def history_for_llm(db: Database, conv_id: UUID) -> list[dict]:
    rows = db.query(
        "SELECT role, content FROM messages WHERE conversation_id = ? "
        "AND role IN ('user','assistant') AND content IS NOT NULL ORDER BY created_at",
        [conv_id],
    )
    return [{"role": r["role"], "content": r["content"]} for r in rows]
