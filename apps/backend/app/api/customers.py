from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager, joinedload

from app.audit import audit
from app.api.dto import booking_dto, customer_dto, message_dto
from app.db import get_db
from app.deps import Ctx, get_owned_or_404, require_salon
from app.models import Booking, Customer, MessageLog, Salon, Service
from app.services.customers import computed_status, normalize_phone, status_expression

router = APIRouter()


def _today(db: Session, ctx: Ctx):
    salon = db.get(Salon, ctx.salon_id)
    return datetime.now(ZoneInfo(salon.timezone)).date()


@router.get("")
def list_customers(
    q: str | None = None, status: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db),
):
    today = _today(db, ctx)
    # статус вычисляется в SQL — иначе пришлось бы тянуть всю базу салона в память
    status_col = status_expression(today).label("status")
    query = (
        select(Customer, status_col)
        .outerjoin(Service, Customer.last_service_id == Service.id)
        .options(contains_eager(Customer.last_service))
        .where(Customer.salon_id == ctx.salon_id)
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    if status:
        query = query.where(status_col == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(Customer.name.nullslast(), Customer.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [customer_dto(c, st) for c, st in rows],
        "total": total, "page": page,
    }


class CustomerCreateIn(BaseModel):
    name: str
    phone: str | None = None


@router.post("")
def create_customer(body: CustomerCreateIn, ctx: Ctx = Depends(require_salon),
                    db: Session = Depends(get_db)):
    phone = None
    if body.phone:
        phone = normalize_phone(body.phone)
        if phone is None:
            raise HTTPException(422, "Телефон не распознан")
        dup = db.scalar(select(Customer).where(
            Customer.salon_id == ctx.salon_id, Customer.phone == phone))
        if dup:
            raise HTTPException(409, f"Клиент с этим телефоном уже есть: {dup.name or dup.phone}")
    customer = Customer(salon_id=ctx.salon_id, name=body.name.strip(), phone=phone)
    db.add(customer)
    db.flush()
    audit(db, ctx, "create", "customer", customer.id, after={"name": customer.name, "phone": phone})
    db.commit()
    return customer_dto(customer, "active")


@router.get("/{customer_id}")
def get_customer(customer_id: int, ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    customer = get_owned_or_404(db, Customer, customer_id, ctx.salon_id)
    customer = db.scalars(select(Customer).options(joinedload(Customer.last_service))
                          .where(Customer.id == customer.id)).one()
    visits = db.scalars(
        select(Booking)
        .options(joinedload(Booking.customer), joinedload(Booking.service), joinedload(Booking.staff))
        .where(Booking.customer_id == customer.id)
        .order_by(Booking.starts_at.desc()).limit(100)
    ).all()
    # вся переписка бота с клиентом — важно при спорах «мне ничего не приходило»
    messages = db.scalars(
        select(MessageLog).options(joinedload(MessageLog.customer))
        .where(MessageLog.customer_id == customer.id)
        .order_by(MessageLog.sent_at.desc()).limit(200)
    ).all()
    dto = customer_dto(customer, computed_status(customer, _today(db, ctx)))
    dto["visits"] = [booking_dto(b) for b in visits]
    dto["messages"] = [message_dto(m) for m in messages]
    return dto


class CustomerPatchIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    do_not_disturb: bool | None = None


@router.patch("/{customer_id}")
def patch_customer(customer_id: int, body: CustomerPatchIn,
                   ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    customer = get_owned_or_404(db, Customer, customer_id, ctx.salon_id)
    before = {"name": customer.name, "phone": customer.phone,
              "do_not_disturb": customer.do_not_disturb}
    if body.name is not None:
        customer.name = body.name.strip()
    if body.phone is not None:
        phone = normalize_phone(body.phone) if body.phone else None
        if body.phone and phone is None:
            raise HTTPException(422, "Телефон не распознан")
        customer.phone = phone
    if body.do_not_disturb is not None:
        customer.do_not_disturb = body.do_not_disturb
    audit(db, ctx, "update", "customer", customer.id, before=before,
          after={"name": customer.name, "phone": customer.phone,
                 "do_not_disturb": customer.do_not_disturb})
    db.commit()
    return customer_dto(customer, computed_status(customer, _today(db, ctx)))
