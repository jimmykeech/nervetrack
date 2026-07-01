"""Document upload/list/download/edit/delete (files stored as SQLite BLOBs)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.auth import current_user
from app.deps import db_dep
from app.models.records import DocumentMeta, DocumentPatch
from app.services import documents as service
from app.services.documents import MAX_BYTES

router = APIRouter(tags=["documents"])


def _safe_filename(filename: str | None) -> str:
    """Strip CR/LF/quotes so the value is safe to embed in a header."""
    name = (filename or "").replace("\r", "").replace("\n", "").replace('"', "")
    return name or "document"


@router.post("/documents", response_model=DocumentMeta, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    owner_type: str = Form("profile"),
    notes: str | None = Form(None),
    instance_id: UUID | None = Form(None),
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    # Reject obviously-oversized uploads before buffering the whole body in memory.
    # `file.size` comes from the client-supplied content-length and may be absent,
    # so the service-level check below remains the authoritative defense.
    if file.size is not None and file.size > MAX_BYTES:
        raise HTTPException(400, "file too large")
    content = await file.read()
    try:
        return service.create_document(
            db, user_id,
            owner_type=owner_type,
            instance_id=instance_id,
            title=title,
            notes=notes,
            filename=file.filename,
            mime_type=file.content_type,
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/documents", response_model=list[DocumentMeta])
def list_documents(
    owner_type: str | None = None,
    instance_id: UUID | None = None,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    return service.list_documents(db, user_id, owner_type, instance_id)


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)
):
    blob = service.get_document_blob(db, user_id, doc_id)
    if blob is None:
        raise HTTPException(404, "No such document")
    content, mime, filename = blob
    headers = {"Content-Disposition": f'inline; filename="{_safe_filename(filename)}"'}
    return Response(content=content, media_type=mime or "application/octet-stream", headers=headers)


@router.patch("/documents/{doc_id}", response_model=DocumentMeta)
def patch_document(
    doc_id: UUID,
    data: DocumentPatch,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    updated = service.update_document(db, user_id, doc_id, data)
    if updated is None:
        raise HTTPException(404, "No such document")
    return updated


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: UUID, db=Depends(db_dep), user_id: UUID = Depends(current_user)):
    if not service.delete_document(db, user_id, doc_id):
        raise HTTPException(404, "No such document")
