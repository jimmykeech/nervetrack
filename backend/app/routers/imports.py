"""Spreadsheet import endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth import current_user
from app.deps import db_dep
from app.services import xlsx_import as service

router = APIRouter(tags=["import"])


@router.post("/import/xlsx")
async def import_xlsx(
    file: UploadFile = File(...),
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Expected an .xlsx workbook")
    content = await file.read()
    try:
        result = service.import_workbook(db, user_id, content)
    except Exception as exc:  # noqa: BLE001 — surface a clean 400 to the UI
        raise HTTPException(400, f"Failed to parse workbook: {exc}") from exc
    return {"imported": result}
