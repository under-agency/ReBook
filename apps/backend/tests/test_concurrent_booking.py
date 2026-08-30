"""Гонка при записи: два клиента жмут одно и то же время одновременно.

Тест работает с настоящими параллельными сессиями и коммитами (фикстура `db`
из conftest живёт в одной транзакции и такую гонку воспроизвести не может),
поэтому создаёт и убирает свои данные сам.
"""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base, Booking, Customer, Salon, Service, Staff
from app.services.bookings import BookingConflict, create_booking
from app.services.salons import DEFAULT_TEXTS, DEFAULT_WORK_HOURS

engine = create_engine(settings.database_url_test)
Session = sessionmaker(bind=engine, expire_on_commit=False)

SLOT = (datetime.now(timezone.utc) + timedelta(days=30)).replace(
    hour=9, minute=0, second=0, microsecond=0)


@pytest.fixture
def fixture_ids():
    Base.metadata.create_all(engine)
    s = Session()
    salon = Salon(name="Гонка", status="active", work_hours=DEFAULT_WORK_HOURS,
                  texts=dict(DEFAULT_TEXTS))
    s.add(salon)
    s.flush()
    service = Service(salon_id=salon.id, name="Стрижка", price=1000, duration_min=60)
    staff = Staff(salon_id=salon.id, name="Мастер")
    s.add_all([service, staff])
    s.flush()
    customers = [Customer(salon_id=salon.id, name=f"К{i}", phone=f"+7900000{salon.id:02d}{i}")
                 for i in range(2)]
    s.add_all(customers)
    s.commit()
    ids = (salon.id, service.id, staff.id, [c.id for c in customers])
    yield ids
    cleanup = Session()
    cleanup.execute(delete(Booking).where(Booking.salon_id == salon.id))
    cleanup.execute(delete(Customer).where(Customer.salon_id == salon.id))
    cleanup.execute(delete(Service).where(Service.salon_id == salon.id))
    cleanup.execute(delete(Staff).where(Staff.salon_id == salon.id))
    cleanup.execute(delete(Salon).where(Salon.id == salon.id))
    cleanup.commit()
    cleanup.close()
    s.close()


def test_same_slot_taken_once(fixture_ids):
    salon_id, service_id, staff_id, customer_ids = fixture_ids
    barrier = threading.Barrier(len(customer_ids))
    outcomes: list[str] = []

    def attempt(customer_id: int):
        s = Session()
        try:
            salon = s.get(Salon, salon_id)
            barrier.wait(timeout=10)
            create_booking(s, salon, customer=s.get(Customer, customer_id),
                           service=s.get(Service, service_id),
                           staff=s.get(Staff, staff_id),
                           starts_at=SLOT, source="bot")
            s.commit()
            outcomes.append("created")
        except BookingConflict:
            s.rollback()
            outcomes.append("conflict")
        finally:
            s.close()

    threads = [threading.Thread(target=attempt, args=(cid,)) for cid in customer_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check = Session()
    taken = check.scalars(select(Booking).where(
        Booking.salon_id == salon_id, Booking.starts_at == SLOT)).all()
    check.close()
    assert len(taken) == 1, f"слот заняли дважды: {outcomes}"
    assert sorted(outcomes) == ["conflict", "created"]
