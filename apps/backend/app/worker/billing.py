"""Биллинг-статусы: просрочка 1 день → grace, 8 дней → paused.

Мягкое отключение: в paused бот отвечает и записывает, рассылки остановлены —
клиенты салона не виноваты в неоплате (docs/10-crm-logic.md).
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Salon


def update_billing_statuses(db: Session, today: date) -> list[tuple[int, str]]:
    changes = []
    salons = db.scalars(select(Salon).where(
        Salon.status.in_(("active", "grace")),
        Salon.next_payment_at.is_not(None),
    )).all()
    for salon in salons:
        overdue = (today - salon.next_payment_at).days
        new_status = None
        if overdue >= 8:
            new_status = "paused"
        elif overdue >= 1 and salon.status == "active":
            new_status = "grace"
        if new_status and new_status != salon.status:
            db.add(AuditLog(salon_id=salon.id, action="billing_status", entity="salon",
                            entity_id=salon.id, before={"status": salon.status},
                            after={"status": new_status, "overdue_days": overdue}))
            salon.status = new_status
            changes.append((salon.id, new_status))
    return changes
