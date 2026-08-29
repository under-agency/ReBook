"""Каскад напоминаний: T-24 в мессенджер, T-3 SMS-догон, автозакрытие.

Каскад строится на «не подтвердил», а не «не прочитал» — read-статусов
у бот-API нет (docs/03-architecture.md). Идемпотентность — через статусную
модель записи: new → reminded_24h → reminded_sms.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, joinedload

from app import channels
from app.models import (
    SALON_SENDING_STATUSES, Booking, Customer, MessageLog, Salon,
)
from app.services.bookings import autoclose, set_status


def _offsets(salon: Salon) -> tuple[int, int]:
    offs = salon.remind_offsets_h or [24, 3]
    return offs[0], (offs[1] if len(offs) > 1 else 3)


def _bookings_in_window(db: Session, salon: Salon, status: str,
                        now: datetime, hours: int) -> list[Booking]:
    return db.scalars(
        select(Booking)
        .options(joinedload(Booking.customer), joinedload(Booking.service),
                 joinedload(Booking.staff))
        .where(
            Booking.salon_id == salon.id,
            Booking.status == status,
            Booking.starts_at > now,
            Booking.starts_at <= now + timedelta(hours=hours),
        )
    ).all()


def send_reminders(db: Session, now: datetime | None = None,
                   transport: channels.Transport | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stats = {"first": 0, "chase": 0}
    salons = db.scalars(select(Salon).where(Salon.status.in_(SALON_SENDING_STATUSES))).all()
    for salon in salons:
        off_first, off_chase = _offsets(salon)

        # Первое напоминание (T-24): бесплатный канал, кнопки Приду/Перенести/Отменить
        for b in _bookings_in_window(db, salon, "new", now, off_first):
            text = channels.render(salon.texts.get("reminder_24h", ""),
                                   salon=salon, customer=b.customer, booking=b)
            sent = channels.send(db, salon, b.customer, "reminder_24h", text,
                                 booking=b, transport=transport, now=now)
            if sent is not None:
                set_status(db, b, "reminded_24h", by_system=True)
                stats["first"] += 1

        # Догон (T-3): не подтвердил после мессенджера → SMS.
        # Тем, у кого первое касание уже было SMS, второе не шлём.
        for b in _bookings_in_window(db, salon, "reminded_24h", now, off_chase):
            had_tg_reminder = db.scalar(select(exists(select(MessageLog.id).where(
                MessageLog.booking_id == b.id,
                MessageLog.kind == "reminder_24h",
                MessageLog.channel == "tg",
            ))))
            if not had_tg_reminder:
                continue
            text = channels.render(salon.texts.get("sms_chase", ""),
                                   salon=salon, customer=b.customer, booking=b)
            sent = channels.send(db, salon, b.customer, "sms_chase", text,
                                 booking=b, transport=transport, now=now,
                                 force_channel="sms")
            if sent is not None:
                set_status(db, b, "reminded_sms", by_system=True)
                stats["chase"] += 1
    return stats


def run_autoclose(db: Session, now: datetime | None = None) -> int:
    return autoclose(db, now or datetime.now(timezone.utc))
