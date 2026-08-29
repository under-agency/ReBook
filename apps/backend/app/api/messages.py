from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dto import message_dto
from app.db import get_db
from app.deps import Ctx, require_salon
from app.models import MessageLog, Salon

router = APIRouter()


@router.get("")
def list_messages(
    channel: str | None = None, kind: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db),
):
    salon = db.get(Salon, ctx.salon_id)
    tz = ZoneInfo(salon.timezone)
    q = select(MessageLog).where(MessageLog.salon_id == ctx.salon_id)
    if channel:
        q = q.where(MessageLog.channel == channel)
    if kind:
        q = q.where(MessageLog.kind == kind)
    if date_from:
        q = q.where(MessageLog.sent_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=tz))
    if date_to:
        q = q.where(MessageLog.sent_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=tz))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.options(joinedload(MessageLog.customer)).order_by(MessageLog.sent_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [message_dto(m) for m in rows], "total": total, "page": page}


@router.get("/stats")
def stats(ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    """Расход SMS против месячного лимита — прозрачность по счетам."""
    salon = db.get(Salon, ctx.salon_id)
    tz = ZoneInfo(salon.timezone)
    local_now = datetime.now(tz)
    month_start = datetime(local_now.year, local_now.month, 1, tzinfo=tz).astimezone(timezone.utc)
    rows = db.execute(select(
        MessageLog.channel, func.count(MessageLog.id), func.coalesce(func.sum(MessageLog.cost), 0),
    ).where(
        MessageLog.salon_id == ctx.salon_id, MessageLog.sent_at >= month_start,
    ).group_by(MessageLog.channel)).all()
    by_channel = {ch: {"count": cnt, "cost": float(cost)} for ch, cnt, cost in rows}
    sms = by_channel.get("sms", {"count": 0, "cost": 0.0})
    return {
        "month": local_now.strftime("%Y-%m"),
        "by_channel": by_channel,
        "sms_used": sms["count"],
        "sms_cost": sms["cost"],
        "sms_limit": salon.sms_limit_month,
    }
