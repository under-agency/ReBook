from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dto import booking_dto
from app.db import get_db
from app.deps import Ctx, require_salon
from app.models import Booking, Salon
from app.reports import month_report

router = APIRouter()


@router.get("/summary")
def summary(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db),
):
    salon = db.get(Salon, ctx.salon_id)
    if month:
        year, mon = int(month[:4]), int(month[5:7])
    else:
        local_now = datetime.now(ZoneInfo(salon.timezone))
        year, mon = local_now.year, local_now.month
    return month_report(db, salon, year, mon)


@router.get("/upcoming")
def upcoming(ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    """Записи на сегодня и завтра со статусами (docs/09-interfaces.md)."""
    salon = db.get(Salon, ctx.salon_id)
    tz = ZoneInfo(salon.timezone)
    today_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today_local.astimezone(timezone.utc)
    end = (today_local + timedelta(days=2)).astimezone(timezone.utc)
    rows = db.scalars(
        select(Booking)
        .options(joinedload(Booking.customer), joinedload(Booking.service), joinedload(Booking.staff))
        .where(Booking.salon_id == ctx.salon_id, Booking.starts_at >= start, Booking.starts_at < end)
        .order_by(Booking.starts_at)
    ).all()
    today, tomorrow = [], []
    for b in rows:
        target = today if b.starts_at.astimezone(tz).date() == today_local.date() else tomorrow
        target.append(booking_dto(b))
    return {"today": today, "tomorrow": tomorrow}
