"""Единственная точка отправки сообщений (docs/08-data-model.md).

Сама решает канал по приоритету салона, пишет в message_log, уважает
do_not_disturb и лимит SMS. Никто больше не шлёт сообщения напрямую.
Транспорт Telegram инжектится (в тестах — фейк).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    SALON_SENDING_STATUSES,
    Booking,
    Customer,
    MessageLog,
    Salon,
)

# Транзакционные сообщения — о собственной записи клиента: идут даже при
# do_not_disturb (клиент отписался от маркетинга, не от своих записей).
TRANSACTIONAL_KINDS = ("reminder_24h", "reminder_3h", "sms_chase", "confirm")
MARKETING_KINDS = ("reactivation", "waitlist_offer")

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


class Transport(Protocol):
    def __call__(self, salon: Salon, customer: Customer, text: str,
                 *, booking_id: int | None = None, kind: str = "") -> bool: ...


def render(template: str, *, salon: Salon, customer: Customer | None = None,
           booking: Booking | None = None) -> str:
    subs = {"{салон}": salon.name}
    subs["{имя}"] = (customer.name if customer and customer.name else "Здравствуйте")
    if booking is not None:
        local = booking.starts_at.astimezone(ZoneInfo(salon.timezone))
        subs["{дата}"] = f"{local.day} {RU_MONTHS[local.month - 1]}"
        subs["{время}"] = local.strftime("%H:%M")
        subs["{услуга}"] = booking.service.name if booking.service else ""
        subs["{мастер}"] = booking.staff.name if booking.staff else "любой мастер"
    text = template
    for key, val in subs.items():
        text = text.replace(key, str(val))
    return text


def reminder_markup(booking_id: int):
    """Кнопки Приду / Перенести / Отменить (docs/09-interfaces.md)."""
    from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Приду", callback_data=f"bk|confirm|{booking_id}"))
    kb.add(
        InlineKeyboardButton("🔄 Перенести", callback_data=f"bk|resched|{booking_id}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"bk|cancel|{booking_id}"),
    )
    return kb


def telegram_transport(salon: Salon, customer: Customer, text: str,
                       *, booking_id: int | None = None, kind: str = "") -> bool:
    import telebot
    bot = telebot.TeleBot(salon.tg_bot_token, threaded=False)
    markup = reminder_markup(booking_id) if (
        kind in ("reminder_24h", "reminder_3h") and booking_id
    ) else None
    try:
        bot.send_message(customer.tg_id, text, reply_markup=markup)
        return True
    except Exception:
        return False


def sms_sent_this_month(db: Session, salon: Salon, now: datetime) -> int:
    local = now.astimezone(ZoneInfo(salon.timezone))
    month_start = datetime(local.year, local.month, 1, tzinfo=ZoneInfo(salon.timezone))
    return db.scalar(select(func.count(MessageLog.id)).where(
        MessageLog.salon_id == salon.id,
        MessageLog.channel == "sms",
        MessageLog.sent_at >= month_start.astimezone(timezone.utc),
    )) or 0


def send(
    db: Session, salon: Salon, customer: Customer, kind: str, text: str,
    *, booking: Booking | None = None,
    transport: Transport | None = None,
    now: datetime | None = None,
    force_channel: str | None = None,
) -> MessageLog | None:
    """Отправляет по каскаду приоритета салона, пишет в message_log.

    force_channel — пропустить каскад и слать только в этот канал (SMS-догон).
    Возвращает MessageLog или None, если отправка запрещена гейтами.
    """
    now = now or datetime.now(timezone.utc)
    if salon.status not in SALON_SENDING_STATUSES:
        return None  # onboarding/paused/archived — рассылки выключены
    if customer.do_not_disturb and kind in MARKETING_KINDS:
        return None
    transport = transport or telegram_transport

    channel_order = [force_channel] if force_channel else salon.channel_priority
    for channel in channel_order:
        if channel == "tg" and customer.tg_id and salon.tg_bot_token:
            ok = transport(salon, customer, text,
                           booking_id=booking.id if booking else None, kind=kind)
            return _log(db, salon, customer, booking, "tg", kind, text,
                        Decimal("0"), "sent" if ok else "failed")
        if channel == "max":
            continue  # MAX-канал вне скоупа
        if channel == "sms" and customer.phone:
            # При 100% лимита реактивационные SMS останавливаются,
            # напоминания продолжают идти в перерасход (docs/10-crm-logic.md)
            if kind in MARKETING_KINDS and sms_sent_this_month(db, salon, now) >= salon.sms_limit_month:
                return None
            # SMS-агрегатор вне скоупа: пишем заглушку в лог с реальной стоимостью
            return _log(db, salon, customer, booking, "sms", kind, text,
                        Decimal(str(settings.sms_cost)), "stub")
    return None


def _log(db: Session, salon: Salon, customer: Customer, booking: Booking | None,
         channel: str, kind: str, text: str, cost: Decimal, status: str) -> MessageLog:
    row = MessageLog(
        salon_id=salon.id, customer_id=customer.id,
        booking_id=booking.id if booking else None,
        channel=channel, kind=kind, text=text, cost=cost, delivery_status=status,
    )
    db.add(row)
    db.flush()
    return row
