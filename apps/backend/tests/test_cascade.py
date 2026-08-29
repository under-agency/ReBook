from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app import channels
from app.models import MessageLog
from app.worker.reminders import send_reminders
from tests.conftest import (
    FakeTransport, make_booking, make_customer, make_service, make_staff,
)

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)


def _env(db, salon, tg_id=555):
    service = make_service(db, salon)
    staff = make_staff(db, salon)
    customer = make_customer(db, salon, tg_id=tg_id)
    return service, staff, customer


def test_first_reminder_sent_once(db, salon_a):
    service, staff, customer = _env(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport = FakeTransport()
    stats = send_reminders(db, now=NOW, transport=transport)
    assert stats["first"] == 1
    assert b.status == "reminded_24h"
    assert len(transport.sent) == 1
    assert transport.sent[0]["kind"] == "reminder_24h"
    # повторный запуск идемпотентен: статус уже reminded_24h, окно T-3 не настало
    stats = send_reminders(db, now=NOW, transport=transport)
    assert stats == {"first": 0, "chase": 0}
    assert len(transport.sent) == 1


def test_chase_goes_to_sms_stub(db, salon_a):
    service, staff, customer = _env(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport = FakeTransport()
    send_reminders(db, now=NOW, transport=transport)
    # прошло 21 ч, до визита 2 ч, клиент не подтвердил
    later = NOW + timedelta(hours=21)
    stats = send_reminders(db, now=later, transport=transport)
    assert stats["chase"] == 1
    assert b.status == "reminded_sms"
    sms = db.scalars(select(MessageLog).where(
        MessageLog.booking_id == b.id, MessageLog.channel == "sms")).all()
    assert len(sms) == 1
    assert sms[0].delivery_status == "stub"
    assert sms[0].cost > 0


def test_sms_first_client_gets_no_second_sms(db, salon_a):
    service, staff, _ = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=None)  # без мессенджера → сразу SMS
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport = FakeTransport()
    send_reminders(db, now=NOW, transport=transport)
    assert b.status == "reminded_24h"
    send_reminders(db, now=NOW + timedelta(hours=21), transport=transport)
    sms = db.scalars(select(MessageLog).where(
        MessageLog.booking_id == b.id, MessageLog.channel == "sms")).all()
    assert len(sms) == 1  # второй SMS не шлём


def test_paused_salon_sends_nothing(db, salon_b):
    salon_b.status = "paused"
    service, staff, customer = _env(db, salon_b)
    b = make_booking(db, salon_b, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport = FakeTransport()
    stats = send_reminders(db, now=NOW, transport=transport)
    assert stats == {"first": 0, "chase": 0}
    assert b.status == "new"
    assert transport.sent == []


def test_do_not_disturb_blocks_marketing_not_reminders(db, salon_a):
    service, staff, _ = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=777, do_not_disturb=True)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport = FakeTransport()
    # напоминание о собственной записи — транзакционное, идёт
    stats = send_reminders(db, now=NOW, transport=transport)
    assert stats["first"] == 1
    # реактивация — маркетинг, блокируется
    res = channels.send(db, salon_a, customer, "reactivation", "тест",
                        transport=transport, now=NOW)
    assert res is None


def test_sms_limit_stops_reactivation_not_reminders(db, salon_a):
    salon_a.sms_limit_month = 2
    service, staff, _ = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=None)
    for _ in range(2):
        db.add(MessageLog(salon_id=salon_a.id, customer_id=customer.id,
                          channel="sms", kind="sms_chase", cost=Decimal("4"),
                          delivery_status="stub", sent_at=NOW))
    db.flush()
    transport = FakeTransport()
    # реактивация при 100% лимита — стоп
    res = channels.send(db, salon_a, customer, "reactivation", "тест",
                        transport=transport, now=NOW)
    assert res is None
    # напоминание — идёт в перерасход
    res = channels.send(db, salon_a, customer, "reminder_24h", "тест",
                        transport=transport, now=NOW)
    assert res is not None and res.channel == "sms"
