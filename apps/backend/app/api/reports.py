from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, require_owner
from app.models import Booking, Salon
from app.reports import month_report

router = APIRouter()


@router.get("/months")
def months(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    """Месяцы, за которые есть записи (в поясе салона), новые сверху."""
    salon = db.get(Salon, ctx.salon_id)
    tz = ZoneInfo(salon.timezone)
    # агрегируем в базе: выгружать все starts_at ради списка месяцев не нужно
    local_month = func.to_char(
        func.date_trunc("month", func.timezone(salon.timezone, Booking.starts_at)),
        "YYYY-MM",
    )
    rows = db.scalars(
        select(local_month).where(Booking.salon_id == ctx.salon_id).distinct()
    ).all()
    months_set = set(rows)
    months_set.add(datetime.now(tz).strftime("%Y-%m"))
    return {"months": sorted(months_set, reverse=True)}


@router.get("/{month}")
def report(month: str, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    try:
        year, mon = int(month[:4]), int(month[5:7])
        assert month[4] == "-" and 1 <= mon <= 12
    except (ValueError, AssertionError, IndexError):
        raise HTTPException(422, "Формат месяца: YYYY-MM")
    salon = db.get(Salon, ctx.salon_id)
    result = month_report(db, salon, year, mon)
    result["salon_name"] = salon.name
    return result
