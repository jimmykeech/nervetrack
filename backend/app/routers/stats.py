"""Stats endpoints for charts."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth import current_user
from app.deps import db_dep
from app.models.stats import DailyStatPoint
from app.services import stats as service

router = APIRouter(tags=["stats"])


@router.get("/stats/daily", response_model=list[DailyStatPoint])
def daily_stats(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    db=Depends(db_dep),
    user_id: UUID = Depends(current_user),
):
    today = date.today()
    date_to = to or today
    date_from = from_ or (date_to - timedelta(days=90))
    return service.daily_stats(db, user_id, date_from, date_to)
