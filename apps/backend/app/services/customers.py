"""Клиенты: вычисляемый статус (не хранится) и upsert без дублей."""
from datetime import date

from sqlalchemy import Date, case, cast, literal, or_, select
from sqlalchemy.orm import Session

from app.models import Customer, Service

SLEEP_MARGIN = 1.2   # цикл истёк + 20% запаса
LOST_CYCLES = 3      # больше трёх циклов — потерянный

STATUS_LABELS = {
    "active": "Активный", "sleeping": "Спящий",
    "lost": "Потерянный", "excluded": "Исключён",
}


def computed_status(customer: Customer, today: date) -> str:
    if customer.do_not_disturb:
        return "excluded"
    cycle = customer.last_service.repeat_cycle_days if customer.last_service else None
    if customer.last_visit_at is None or not cycle:
        return "active"
    days = (today - customer.last_visit_at).days
    if days > cycle * LOST_CYCLES:
        return "lost"
    if days > cycle * SLEEP_MARGIN:
        return "sleeping"
    return "active"


def status_expression(today: date):
    """Та же логика, что в computed_status, но выражением SQL.

    Нужна, чтобы фильтровать и пагинировать клиентов в базе, а не в памяти.
    Совпадение обеих веток закреплено тестом test_customer_status.py.
    """
    days = cast(literal(today), Date) - Customer.last_visit_at
    cycle = Service.repeat_cycle_days
    return case(
        (Customer.do_not_disturb.is_(True), "excluded"),
        (or_(Customer.last_visit_at.is_(None), cycle.is_(None)), "active"),
        (days > cycle * LOST_CYCLES, "lost"),
        (days > cycle * SLEEP_MARGIN, "sleeping"),
        else_="active",
    )


def upsert_customer(
    db: Session, salon_id: int, *,
    tg_id: int | None = None, phone: str | None = None, name: str | None = None,
) -> Customer:
    """Ищем сначала по tg_id, потом по phone — чтобы не плодить дубли
    после «поделиться контактом»."""
    customer = None
    if tg_id is not None:
        customer = db.scalar(select(Customer).where(
            Customer.salon_id == salon_id, Customer.tg_id == tg_id))
    if customer is None and phone:
        customer = db.scalar(select(Customer).where(
            Customer.salon_id == salon_id, Customer.phone == phone))
    if customer is None:
        customer = Customer(salon_id=salon_id, tg_id=tg_id, phone=phone, name=name)
        db.add(customer)
        db.flush()
        return customer
    # дозаполняем недостающее
    if tg_id is not None and customer.tg_id is None:
        customer.tg_id = tg_id
    if phone and not customer.phone:
        customer.phone = phone
    if name and not customer.name:
        customer.name = name
    return customer


def normalize_phone(raw: str) -> str | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "9":
        return "+7" + digits
    if raw.startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    return None
