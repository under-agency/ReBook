"""Сериализация в JSON для фронта."""
from datetime import date, datetime

from app.models import AuditLog, Booking, Customer, MessageLog
from app.services.bookings import display_status

KIND_LABELS = {
    "reminder_24h": "Напоминание за 24 ч", "reminder_3h": "Напоминание за 3 ч",
    "sms_chase": "SMS-догон", "reactivation": "Реактивация", "confirm": "Подтверждение",
    "waitlist_offer": "Предложение окна", "report": "Отчёт", "faq": "FAQ", "test": "Тест",
}


def iso(dt: datetime | date | None) -> str | None:
    return dt.isoformat() if dt else None


def booking_dto(b: Booking) -> dict:
    return {
        "id": b.id,
        "starts_at": iso(b.starts_at),
        "duration_min": b.duration_min,
        "status": b.status,
        "status_display": display_status(b.status),
        "source": b.source,
        "note": b.note,
        "rescheduled_to_id": b.rescheduled_to_id,
        "customer": {
            "id": b.customer.id, "name": b.customer.name, "phone": b.customer.phone,
            "has_tg": b.customer.tg_id is not None,
        } if b.customer else None,
        "service": {
            "id": b.service.id, "name": b.service.name, "price": float(b.service.price),
        } if b.service else None,
        "staff": {"id": b.staff.id, "name": b.staff.name} if b.staff else None,
        "created_at": iso(b.created_at),
    }


def customer_dto(c: Customer, status: str | None = None) -> dict:
    return {
        "id": c.id, "name": c.name, "phone": c.phone,
        "has_tg": c.tg_id is not None, "has_max": c.max_id is not None,
        "last_visit_at": iso(c.last_visit_at),
        "last_service": c.last_service.name if c.last_service else None,
        "do_not_disturb": c.do_not_disturb,
        "status": status,
        "created_at": iso(c.created_at),
    }


def message_dto(m: MessageLog) -> dict:
    return {
        "id": m.id, "channel": m.channel, "kind": m.kind,
        "kind_display": KIND_LABELS.get(m.kind, m.kind),
        "text": m.text, "cost": float(m.cost),
        "delivery_status": m.delivery_status,
        "booking_id": m.booking_id,
        "customer": {"id": m.customer.id, "name": m.customer.name} if m.customer else None,
        "sent_at": iso(m.sent_at),
    }


def audit_dto(a: AuditLog) -> dict:
    return {
        "id": a.id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
        "before": a.before, "after": a.after, "is_support": a.is_support,
        "user_email": a.user.email if a.user else None,
        "ip": a.ip, "created_at": iso(a.created_at),
    }
