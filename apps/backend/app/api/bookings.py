from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.audit import audit
from app.api.dto import booking_dto, message_dto
from app.db import get_db
from app.deps import Ctx, get_owned_or_404, require_salon
from app.models import Booking, Customer, MessageLog, Salon, Service, Staff
from app.services import bookings as svc
from app.services.customers import normalize_phone, upsert_customer
from app.services.slots import free_slots
from app import channels

router = APIRouter()

_LOAD = (
    joinedload(Booking.customer), joinedload(Booking.service), joinedload(Booking.staff),
)


def to_utc(dt: datetime, salon: Salon) -> datetime:
    """Наивное время трактуем в поясе салона (из <input datetime-local>)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(salon.timezone))
    return dt.astimezone(timezone.utc)


def _salon(db: Session, ctx: Ctx) -> Salon:
    return db.get(Salon, ctx.salon_id)


@router.get("")
def list_bookings(
    ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db),
    date_from: date | None = None, date_to: date | None = None,
    staff_id: int | None = None, status: str | None = None,
    customer_id: int | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
):
    salon = _salon(db, ctx)
    tz = ZoneInfo(salon.timezone)
    q = select(Booking).where(Booking.salon_id == ctx.salon_id)
    if date_from:
        q = q.where(Booking.starts_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=tz))
    if date_to:
        q = q.where(Booking.starts_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=tz))
    if staff_id is not None:
        q = q.where(Booking.staff_id == staff_id)
    if status:
        q = q.where(Booking.status.in_(status.split(",")))
    if customer_id is not None:
        q = q.where(Booking.customer_id == customer_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.options(*_LOAD).order_by(Booking.starts_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [booking_dto(b) for b in rows], "total": total, "page": page}


@router.get("/free-slots")
def get_free_slots(
    service_id: int, on_date: date = Query(alias="date"), staff_id: int | None = None,
    ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db),
):
    salon = _salon(db, ctx)
    service = get_owned_or_404(db, Service, service_id, ctx.salon_id)
    staff = get_owned_or_404(db, Staff, staff_id, ctx.salon_id) if staff_id else None
    tz = ZoneInfo(salon.timezone)
    day_start = datetime.combine(on_date, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    busy = svc._busy_for(db, ctx.salon_id, staff.id if staff else None,
                         day_start, day_start + timedelta(days=1))
    slots = free_slots(
        work_hours=salon.work_hours, staff_hours=staff.work_hours if staff else None,
        duration_min=service.duration_min, day=on_date, tz=tz, busy=busy,
        now=datetime.now(timezone.utc),
    )
    return {"slots": [
        {"starts_at": s.isoformat(), "label": s.astimezone(tz).strftime("%H:%M")}
        for s in slots
    ]}


class NewCustomerIn(BaseModel):
    name: str
    phone: str | None = None


class BookingCreateIn(BaseModel):
    customer_id: int | None = None
    new_customer: NewCustomerIn | None = None
    service_id: int
    staff_id: int | None = None
    starts_at: datetime
    note: str | None = None
    force: bool = False


@router.post("")
def create_booking(body: BookingCreateIn, ctx: Ctx = Depends(require_salon),
                   db: Session = Depends(get_db)):
    salon = _salon(db, ctx)
    service = get_owned_or_404(db, Service, body.service_id, ctx.salon_id)
    staff = get_owned_or_404(db, Staff, body.staff_id, ctx.salon_id) if body.staff_id else None
    if body.customer_id:
        customer = get_owned_or_404(db, Customer, body.customer_id, ctx.salon_id)
    elif body.new_customer:
        phone = None
        if body.new_customer.phone:
            phone = normalize_phone(body.new_customer.phone)
            if phone is None:
                raise HTTPException(422, "Телефон не распознан, формат: +7 900 000-00-00")
        customer = upsert_customer(db, ctx.salon_id, phone=phone, name=body.new_customer.name)
    else:
        raise HTTPException(422, "Укажите клиента")
    try:
        booking = svc.create_booking(
            db, salon, customer=customer, service=service, staff=staff,
            starts_at=to_utc(body.starts_at, salon), source="manual",
            note=body.note, force=body.force,
        )
    except svc.BookingConflict as e:
        raise HTTPException(409, {"warnings": e.warnings})
    audit(db, ctx, "create", "booking", booking.id, after={"starts_at": booking.starts_at.isoformat(),
          "service": service.name, "customer_id": customer.id})
    # подтверждение клиенту — запись из кабинета живёт по общим правилам
    booking.customer, booking.service, booking.staff = customer, service, staff
    text = channels.render(salon.texts.get("confirm", ""), salon=salon,
                           customer=customer, booking=booking)
    if text:
        channels.send(db, salon, customer, "confirm", text, booking=booking)
    db.commit()
    return booking_dto(db.scalars(select(Booking).options(*_LOAD).where(Booking.id == booking.id)).one())


@router.get("/{booking_id}")
def get_booking(booking_id: int, ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    booking = get_owned_or_404(db, Booking, booking_id, ctx.salon_id)
    booking = db.scalars(select(Booking).options(*_LOAD).where(Booking.id == booking.id)).one()
    messages = db.scalars(
        select(MessageLog).options(joinedload(MessageLog.customer))
        .where(MessageLog.booking_id == booking.id).order_by(MessageLog.sent_at)
    ).all()
    dto = booking_dto(booking)
    dto["messages"] = [message_dto(m) for m in messages]
    return dto


class BookingPatchIn(BaseModel):
    status: str | None = None
    note: str | None = None
    staff_id: int | None = None


@router.patch("/{booking_id}")
def patch_booking(booking_id: int, body: BookingPatchIn,
                  ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    booking = get_owned_or_404(db, Booking, booking_id, ctx.salon_id)
    before = {"status": booking.status, "note": booking.note, "staff_id": booking.staff_id}
    if body.status:
        try:
            svc.set_status(db, booking, body.status)
        except svc.InvalidTransition as e:
            raise HTTPException(422, str(e))
    if body.note is not None:
        booking.note = body.note
    if body.staff_id is not None:
        staff = get_owned_or_404(db, Staff, body.staff_id, ctx.salon_id)
        booking.staff_id = staff.id
    audit(db, ctx, "update", "booking", booking.id, before=before,
          after={"status": booking.status, "note": booking.note, "staff_id": booking.staff_id})
    db.commit()
    return booking_dto(db.scalars(select(Booking).options(*_LOAD).where(Booking.id == booking.id)).one())


class RescheduleIn(BaseModel):
    starts_at: datetime
    staff_id: int | None = None
    force: bool = False


@router.post("/{booking_id}/reschedule")
def reschedule_booking(booking_id: int, body: RescheduleIn,
                       ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    booking = get_owned_or_404(db, Booking, booking_id, ctx.salon_id)
    salon = _salon(db, ctx)
    staff = get_owned_or_404(db, Staff, body.staff_id, ctx.salon_id) if body.staff_id \
        else db.get(Staff, booking.staff_id) if booking.staff_id else None
    try:
        new_booking = svc.reschedule(
            db, salon, booking, new_starts_at=to_utc(body.starts_at, salon),
            staff=staff, force=body.force,
        )
    except svc.BookingConflict as e:
        raise HTTPException(409, {"warnings": e.warnings})
    except svc.InvalidTransition as e:
        raise HTTPException(422, str(e))
    audit(db, ctx, "reschedule", "booking", booking.id,
          before={"starts_at": booking.starts_at.isoformat()},
          after={"new_booking_id": new_booking.id, "starts_at": new_booking.starts_at.isoformat()})
    db.commit()
    return booking_dto(db.scalars(select(Booking).options(*_LOAD).where(Booking.id == new_booking.id)).one())
