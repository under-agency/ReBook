"""Ядро CRM-логики: создание записей, конфликты, статусная модель, перенос."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, Customer, Salon, Service, Staff
from app.services.slots import overlaps, within_work_hours

# Статусы, занимающие слот
ACTIVE_STATUSES = ("new", "reminded_24h", "reminded_sms", "confirmed")

# Ручные переходы: владелец может исправить любой итог (автозакрытие обратимо),
# reminded_* выставляет только система, rescheduled — только через перенос.
MANUAL_TARGET_STATUSES = ("new", "confirmed", "done", "cancelled", "no_show")


class BookingConflict(Exception):
    def __init__(self, warnings: list[str]):
        self.warnings = warnings
        super().__init__("; ".join(warnings))


class InvalidTransition(Exception):
    pass


def _busy_for(db: Session, salon_id: int, staff_id: int | None, day_start: datetime,
              day_end: datetime, exclude_id: int | None = None) -> list[tuple[datetime, int]]:
    q = select(Booking).where(
        Booking.salon_id == salon_id,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.starts_at >= day_start - timedelta(hours=6),
        Booking.starts_at < day_end + timedelta(hours=6),
    )
    if staff_id is not None:
        q = q.where(Booking.staff_id == staff_id)
    rows = db.scalars(q).all()
    return [(b.starts_at, b.duration_min) for b in rows if b.id != exclude_id]


def validate_slot(
    db: Session, salon: Salon, *, service: Service, staff: Staff | None,
    starts_at: datetime, exclude_id: int | None = None,
) -> list[str]:
    """Проверки при сохранении (10-crm-logic.md). Возвращает список предупреждений."""
    warnings: list[str] = []
    tz = ZoneInfo(salon.timezone)
    if not within_work_hours(
        work_hours=salon.work_hours, staff_hours=staff.work_hours if staff else None,
        starts_at=starts_at, duration_min=service.duration_min, tz=tz,
    ):
        warnings.append("Время вне рабочих часов")
    busy = _busy_for(
        db, salon.id, staff.id if staff else None,
        starts_at, starts_at + timedelta(minutes=service.duration_min), exclude_id,
    )
    if any(overlaps(starts_at, service.duration_min, b_start, b_dur) for b_start, b_dur in busy):
        warnings.append("Слот пересекается с другой записью" + (f" (мастер {staff.name})" if staff else ""))
    return warnings


def create_booking(
    db: Session, salon: Salon, *, customer: Customer, service: Service,
    staff: Staff | None, starts_at: datetime, source: str = "manual",
    note: str | None = None, force: bool = False,
) -> Booking:
    warnings = validate_slot(db, salon, service=service, staff=staff, starts_at=starts_at)
    if warnings and not force:
        # не блокируем жёстко — фронт показывает предупреждение с «всё равно записать»
        raise BookingConflict(warnings)
    booking = Booking(
        salon_id=salon.id, customer_id=customer.id, service_id=service.id,
        staff_id=staff.id if staff else None, starts_at=starts_at,
        duration_min=service.duration_min, status="new", source=source, note=note,
    )
    db.add(booking)
    db.flush()
    return booking


def set_status(db: Session, booking: Booking, new_status: str, *, by_system: bool = False) -> None:
    if not by_system and new_status not in MANUAL_TARGET_STATUSES:
        raise InvalidTransition(f"Статус «{new_status}» нельзя выставить вручную")
    if booking.status == new_status:
        return
    booking.status = new_status
    if new_status == "done":
        _mark_visit(db, booking)


def _mark_visit(db: Session, booking: Booking) -> None:
    customer = db.get(Customer, booking.customer_id)
    salon = db.get(Salon, booking.salon_id)
    visit_date = booking.starts_at.astimezone(ZoneInfo(salon.timezone)).date()
    if customer.last_visit_at is None or customer.last_visit_at < visit_date:
        customer.last_visit_at = visit_date
        customer.last_service_id = booking.service_id


def reschedule(
    db: Session, salon: Salon, booking: Booking, *,
    new_starts_at: datetime, staff: Staff | None, force: bool = False,
) -> Booking:
    """Старая запись закрывается как rescheduled, создаётся новая (10-crm-logic.md)."""
    if booking.status in ("done", "cancelled", "rescheduled"):
        raise InvalidTransition("Эту запись нельзя перенести")
    service = db.get(Service, booking.service_id)
    customer = db.get(Customer, booking.customer_id)
    new_booking = create_booking(
        db, salon, customer=customer, service=service, staff=staff,
        starts_at=new_starts_at, source=booking.source, note=booking.note, force=force,
    )
    booking.status = "rescheduled"
    booking.rescheduled_to_id = new_booking.id
    return new_booking


def autoclose(db: Session, now: datetime) -> int:
    """Через 24 ч после starts_at: confirmed → done, напомненные/новые → no_show.

    Допущение обратимо: владелец может переключить статус вручную,
    и отчёт пересчитается (docs/10-crm-logic.md).
    """
    cutoff = now - timedelta(hours=24)
    rows = db.scalars(select(Booking).where(
        Booking.status.in_(ACTIVE_STATUSES), Booking.starts_at < cutoff,
    )).all()
    for b in rows:
        set_status(db, b, "done" if b.status == "confirmed" else "no_show", by_system=True)
    return len(rows)


def display_status(status: str) -> str:
    """Человеческие статусы для дашборда (docs/09-interfaces.md)."""
    return {
        "new": "Новая", "reminded_24h": "Ждём ответ", "reminded_sms": "Ждём ответ",
        "confirmed": "Придёт", "done": "Состоялась", "rescheduled": "Перенесена",
        "cancelled": "Отменена", "no_show": "Неявка",
    }.get(status, status)
