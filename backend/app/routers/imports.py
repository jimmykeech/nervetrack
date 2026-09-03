"""Spreadsheet import endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth import current_user
from app.deps import db_dep
from app.services import xlsx_import as service
from app.services.xlsx_import import MAX_UPLOAD_BYTES

router = APIRouter(tags=["import"])


@router.post("/import/xlsx")
async def import_xlsx(
    file: UploadFile = File(...),
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Expected an .xlsx workbook")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Workbook is too large")

    # Read at most one byte beyond the limit. UploadFile may already be spooled to
    # disk by Starlette, so this keeps the application-level allocation bounded.
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Workbook is too large")
    try:
        result = service.import_workbook(db, user_id, content)
    except Exception as exc:  # noqa: BLE001 — surface a clean 400 to the UI
        raise HTTPException(400, f"Failed to parse workbook: {exc}") from exc
    return {"imported": result}
