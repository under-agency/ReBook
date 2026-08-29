"""Расчёт «возвращено ≈ N ₽»: формула и коэффициент показываются владельцу
открыто — честность продаёт продление (docs/08-data-model.md).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Booking, MessageLog, Salon

REMINDER_KINDS = ("reminder_24h", "reminder_3h", "sms_chase")


def month_bounds(salon: Salon, year: int, month: int) -> tuple[datetime, datetime]:
    """Границы месяца в поясе салона → aware UTC."""
    tz = ZoneInfo(salon.timezone)
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + 1, 1, 1, tzinfo=tz) if month == 12 else datetime(year, month + 1, 1, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _had_message(booking_alias, kinds: tuple[str, ...]):
    return exists(select(MessageLog.id).where(
        MessageLog.booking_id == booking_alias.id,
        MessageLog.kind.in_(kinds),
    ))


def month_report(db: Session, salon: Salon, year: int, month: int) -> dict:
    start, end = month_bounds(salon, year, month)
    in_month = and_(
        Booking.salon_id == salon.id,
        Booking.starts_at >= start,
        Booking.starts_at < end,
    )

    def count(*conds) -> int:
        return db.scalar(select(func.count(Booking.id)).where(in_month, *conds)) or 0

    total = count()
    # Подтверждено = confirmed|done ПОСЛЕ отправленного напоминания (10-crm-logic.md)
    confirmed_after_reminder = count(
        Booking.status.in_(("confirmed", "done")), _had_message(Booking, REMINDER_KINDS))
    done = count(Booking.status == "done")
    no_show = count(Booking.status == "no_show")
    cancelled = count(Booking.status == "cancelled")
    rescheduled = count(Booking.status == "rescheduled")

    # Визиты из листа ожидания: клиенту уходило waitlist_offer по этой записи
    waitlist_visits = count(
        Booking.status.in_(("confirmed", "done")), _had_message(Booking, ("waitlist_offer",)))
    # Визиты из реактивации: клиент получил reactivation в 30 дней до создания записи
    reactivation_visits = db.scalar(select(func.count(Booking.id)).where(
        in_month,
        Booking.status.in_(("confirmed", "done")),
        exists(select(MessageLog.id).where(
            MessageLog.customer_id == Booking.customer_id,
            MessageLog.kind == "reactivation",
            MessageLog.sent_at < Booking.created_at,
            MessageLog.sent_at > Booking.created_at - timedelta(days=30),
        )),
    )) or 0

    # Разбивка сообщений по каналам и типам
    msg_rows = db.execute(select(
        MessageLog.channel, MessageLog.kind,
        func.count(MessageLog.id), func.coalesce(func.sum(MessageLog.cost), 0),
    ).where(
        MessageLog.salon_id == salon.id,
        MessageLog.sent_at >= start, MessageLog.sent_at < end,
    ).group_by(MessageLog.channel, MessageLog.kind)).all()
    messages = [
        {"channel": ch, "kind": kind, "count": cnt, "cost": float(cost)}
        for ch, kind, cnt, cost in msg_rows
    ]
    sms_count = sum(m["count"] for m in messages if m["channel"] == "sms")
    sms_cost = sum(m["cost"] for m in messages if m["channel"] == "sms")

    avg_check = float(salon.avg_check or 0)
    rate = settings.no_show_rate
    returned_prevented = round(confirmed_after_reminder * rate * avg_check, 2)
    returned_waitlist = round(waitlist_visits * avg_check, 2)
    returned_reactivation = round(reactivation_visits * avg_check, 2)

    return {
        "month": f"{year:04d}-{month:02d}",
        "bookings_total": total,
        "confirmed": confirmed_after_reminder,
        "done": done,
        "no_show": no_show,
        "cancelled": cancelled,
        "rescheduled": rescheduled,
        "waitlist_visits": waitlist_visits,
        "reactivation_visits": reactivation_visits,
        "messages": messages,
        "sms_count": sms_count,
        "sms_cost": round(sms_cost, 2),
        "sms_limit": salon.sms_limit_month,
        # формула открыто
        "no_show_rate": rate,
        "avg_check": avg_check,
        "returned_prevented": returned_prevented,
        "returned_waitlist": returned_waitlist,
        "returned_reactivation": returned_reactivation,
        "returned_total": round(returned_prevented + returned_waitlist + returned_reactivation, 2),
    }
