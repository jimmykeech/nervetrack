"""Supporting documents stored as SQLite BLOBs, scoped per user."""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.records import DocumentMeta, DocumentPatch

MAX_BYTES = 20 * 1024 * 1024
ALLOWED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/heic",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_META_COLS = (
    "id, owner_type, instance_id, title, notes, filename, mime_type, size_bytes, created_at"
)


def create_document(
    db: Database,
    user_id: UUID,
    *,
    owner_type: str,
    instance_id: UUID | None,
    title: str,
    notes: str | None,
    filename: str | None,
    mime_type: str | None,
    content: bytes,
) -> DocumentMeta:
    if len(content) > MAX_BYTES:
        raise ValueError("file too large")
    if mime_type not in ALLOWED_MIME:
        raise ValueError(f"unsupported file type: {mime_type}")
    if owner_type == "condition":
        owned = db.query_one(
            "SELECT 1 FROM pain_instances WHERE id = ? AND user_id = ?", [instance_id, user_id]
        )
        if not owned:
            raise ValueError("pain instance does not belong to this account")
    else:
        owner_type = "profile"
        instance_id = None

    with db.cursor():
        created = db.query_one(
            f"""
            INSERT INTO documents
                (user_id, owner_type, instance_id, title, notes, filename, mime_type,
                 size_bytes, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING {_META_COLS}
            """,
            [user_id, owner_type, instance_id, title, notes, filename, mime_type,
             len(content), content],
        )
    assert created is not None
    return DocumentMeta(**created)


def list_documents(
    db: Database, user_id: UUID, owner_type: str | None = None,
    instance_id: UUID | None = None
) -> list[DocumentMeta]:
    where = ["user_id = ?"]
    params: list = [user_id]
    if owner_type is not None:
        where.append("owner_type = ?")
        params.append(owner_type)
    if instance_id is not None:
        where.append("instance_id = ?")
        params.append(instance_id)
    rows = db.query(
        f"SELECT {_META_COLS} FROM documents WHERE {' AND '.join(where)} ORDER BY created_at DESC",
        params,
    )
    return [DocumentMeta(**r) for r in rows]


def get_document_blob(
    db: Database, user_id: UUID, doc_id: UUID
) -> tuple[bytes, str | None, str | None] | None:
    row = db.query_one(
        "SELECT content, mime_type, filename FROM documents WHERE id = ? AND user_id = ?",
        [doc_id, user_id],
    )
    if row is None:
        return None
    return row["content"], row["mime_type"], row["filename"]


def update_document(
    db: Database, user_id: UUID, doc_id: UUID, patch: DocumentPatch
) -> DocumentMeta | None:
    fields = patch.model_dump(exclude_unset=True)
    if fields:
        assignments = ", ".join(f"{k} = ?" for k in fields)
        params = [*fields.values(), doc_id, user_id]
        with db.cursor():
            db.execute(
                f"UPDATE documents SET {assignments} WHERE id = ? AND user_id = ?", params
            )
    row = db.query_one(
        f"SELECT {_META_COLS} FROM documents WHERE id = ? AND user_id = ?", [doc_id, user_id]
    )
    return DocumentMeta(**row) if row else None


def delete_document(db: Database, user_id: UUID, doc_id: UUID) -> bool:
    with db.cursor() as conn:
        cur = conn.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?", [doc_id, user_id]
        )
        return cur.rowcount > 0
