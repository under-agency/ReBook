"""Тестовая БД rebook_test: схема один раз, каждый тест — в транзакции с откатом."""
import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Base, Booking, Customer, Salon, Service, Staff, User
from app.services.salons import DEFAULT_TEXTS, DEFAULT_WORK_HOURS
from app.services.slots import within_work_hours

engine = create_engine(settings.database_url_test)

# один хэш на все тестовые учётки — argon2 медленный
PASSWORD = "test_password_123"
PASS_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    conn = engine.connect()
    trans = conn.begin()
    session = sessionmaker(bind=conn, expire_on_commit=False,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    trans.rollback()
    conn.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_salon(db, name="Салон А", status="active", **kw) -> Salon:
    salon = Salon(
        name=name, status=status, work_hours=DEFAULT_WORK_HOURS,
        texts=dict(DEFAULT_TEXTS), avg_check=kw.pop("avg_check", Decimal("2000")),
        tg_bot_token=kw.pop("tg_bot_token", "123:test"), **kw,
    )
    db.add(salon)
    db.flush()
    return salon


def make_user(db, salon, role="owner", email=None) -> User:
    user = User(
        salon_id=salon.id if salon else None,
        email=email or f"{role}-{uuid.uuid4().hex[:10]}@test.ru",
        pass_hash=PASS_HASH, role=role,
    )
    db.add(user)
    db.flush()
    return user


def make_service(db, salon, name="Стрижка", duration_min=60,
                 price=Decimal("2000"), repeat_cycle_days=30) -> Service:
    service = Service(salon_id=salon.id, name=name, price=price,
                      duration_min=duration_min, repeat_cycle_days=repeat_cycle_days)
    db.add(service)
    db.flush()
    return service


def make_staff(db, salon, name="Мария") -> Staff:
    staff = Staff(salon_id=salon.id, name=name)
    db.add(staff)
    db.flush()
    return staff


def make_customer(db, salon, name="Анна", phone=None, tg_id=None, **kw) -> Customer:
    customer = Customer(
        salon_id=salon.id, name=name,
        phone=phone or f"+79{uuid.uuid4().int % 10**9:09d}",
        tg_id=tg_id, **kw,
    )
    db.add(customer)
    db.flush()
    return customer


def make_booking(db, salon, customer, service, staff=None,
                 starts_at=None, status="new", **kw) -> Booking:
    booking = Booking(
        salon_id=salon.id, customer_id=customer.id, service_id=service.id,
        staff_id=staff.id if staff else None,
        starts_at=starts_at or datetime.now(timezone.utc) + timedelta(days=3),
        duration_min=service.duration_min, status=status, **kw,
    )
    db.add(booking)
    db.flush()
    return booking


def next_working_slot(salon, *, days_ahead=1, hour=12, duration_min=60) -> datetime:
    """Ближайшее рабочее окно салона не раньше чем через days_ahead суток → aware UTC.

    Тесты, которые идут через create_booking, не могут брать «сейчас + 3 дня»
    наугад: время должно попадать в рабочие часы, иначе валидация даст warning.
    Воскресенье в DEFAULT_WORK_HOURS выходной, поэтому день подбираем.
    """
    tz = ZoneInfo(salon.timezone)
    day = datetime.now(tz).date() + timedelta(days=days_ahead)
    for _ in range(14):
        starts_at = datetime.combine(day, time(hour), tzinfo=tz).astimezone(timezone.utc)
        if within_work_hours(work_hours=salon.work_hours, staff_hours=None,
                             starts_at=starts_at, duration_min=duration_min, tz=tz):
            return starts_at
        day += timedelta(days=1)
    raise AssertionError("у салона нет рабочего дня в ближайшие две недели")


def login(client, user) -> None:
    r = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 200, r.text


@pytest.fixture
def salon_a(db):
    return make_salon(db, "Салон А")


@pytest.fixture
def salon_b(db):
    return make_salon(db, "Салон Б")


class FakeTransport:
    """Копит отправленные сообщения вместо реального Telegram."""

    def __init__(self, ok=True):
        self.ok = ok
        self.sent: list[dict] = []

    def __call__(self, salon, customer, text, *, booking_id=None, kind=""):
        self.sent.append({"salon_id": salon.id, "customer_id": customer.id,
                          "text": text, "booking_id": booking_id, "kind": kind})
        return self.ok
