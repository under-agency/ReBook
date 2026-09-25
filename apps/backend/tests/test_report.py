from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import MessageLog
from app.reports import month_report
from tests.conftest import make_booking, make_customer, make_service, make_staff

TZ = ZoneInfo("Europe/Moscow")
YEAR, MONTH = 2026, 7


def _at(day, hour):
    return datetime(YEAR, MONTH, day, hour, 0, tzinfo=TZ).astimezone(timezone.utc)


def _reminder(db, salon, booking, customer, channel="tg", status="sent"):
    db.add(MessageLog(salon_id=salon.id, customer_id=customer.id,
                      booking_id=booking.id, channel=channel, kind="reminder_24h",
                      cost=Decimal("0"), delivery_status=status,
                      sent_at=booking.starts_at - timedelta(hours=24)))
    db.flush()


def test_returned_formula(db, salon_a):
    """5 подтверждённых после напоминания × 0.15 × 2000 ₽ = 1500 ₽."""
    service = make_service(db, salon_a)
    staff = make_staff(db, salon_a)
    customer = make_customer(db, salon_a)
    for day in range(1, 6):
        b = make_booking(db, salon_a, customer, service, staff,
                         starts_at=_at(day, 12), status="done")
        _reminder(db, salon_a, b, customer)
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["confirmed"] == 5
    assert report["no_show_rate"] == 0.15
    assert report["returned_prevented"] == 5 * 0.15 * 2000
    assert report["returned_total"] == 1500.0


def test_done_without_reminder_not_counted(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    make_booking(db, salon_a, customer, service,
                 starts_at=_at(10, 12), status="done")  # напоминания не было
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["bookings_total"] == 1
    assert report["confirmed"] == 0
    assert report["returned_prevented"] == 0


def test_month_boundaries_in_salon_tz(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    # 1 июля 00:30 МСК = 30 июня 21:30 UTC — должна попасть в июль
    edge = datetime(YEAR, MONTH, 1, 0, 30, tzinfo=TZ).astimezone(timezone.utc)
    make_booking(db, salon_a, customer, service, starts_at=edge, status="done")
    assert month_report(db, salon_a, YEAR, MONTH)["bookings_total"] == 1
    assert month_report(db, salon_a, YEAR, 6)["bookings_total"] == 0


def test_reactivation_visits_counted(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    b = make_booking(db, salon_a, customer, service,
                     starts_at=_at(15, 12), status="done",
                     created_at=_at(12, 10))
    db.add(MessageLog(salon_id=salon_a.id, customer_id=customer.id,
                      channel="tg", kind="reactivation", cost=Decimal("0"),
                      delivery_status="sent", sent_at=_at(11, 10)))
    db.flush()
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["reactivation_visits"] == 1
    assert report["returned_reactivation"] == 2000.0


def test_sms_costs_aggregated(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    b = make_booking(db, salon_a, customer, service,
                     starts_at=_at(20, 12), status="no_show")
    db.add(MessageLog(salon_id=salon_a.id, customer_id=customer.id, booking_id=b.id,
                      channel="sms", kind="sms_chase", cost=Decimal("4.00"),
                      delivery_status="stub", sent_at=_at(19, 12)))
    db.flush()
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["sms_count"] == 1
    assert report["sms_cost"] == 4.0
    assert report["no_show"] == 1


def test_undelivered_reminder_not_counted(db, salon_a):
    """SMS-заглушка и сбой отправки визит не спасали — в «возвращено» не идут."""
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    for day, channel, status in ((3, "sms", "stub"), (4, "tg", "failed")):
        b = make_booking(db, salon_a, customer, service,
                         starts_at=_at(day, 12), status="done")
        _reminder(db, salon_a, b, customer, channel=channel, status=status)
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["bookings_total"] == 2
    assert report["confirmed"] == 0
    assert report["returned_prevented"] == 0


def test_delivered_reminder_counts_once_despite_stub(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    b = make_booking(db, salon_a, customer, service,
                     starts_at=_at(5, 12), status="done")
    _reminder(db, salon_a, b, customer, channel="sms", status="stub")
    _reminder(db, salon_a, b, customer, channel="tg", status="sent")
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["confirmed"] == 1
    assert report["returned_prevented"] == 0.15 * 2000


def test_undelivered_reactivation_not_counted(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    make_booking(db, salon_a, customer, service, starts_at=_at(15, 12),
                 status="done", created_at=_at(12, 10))
    db.add(MessageLog(salon_id=salon_a.id, customer_id=customer.id,
                      channel="sms", kind="reactivation", cost=Decimal("4.00"),
                      delivery_status="stub", sent_at=_at(11, 10)))
    db.flush()
    report = month_report(db, salon_a, YEAR, MONTH)
    assert report["reactivation_visits"] == 0
    assert report["returned_reactivation"] == 0


def test_waitlist_offer_counts_only_when_delivered(db, salon_a):
    service = make_service(db, salon_a)
    customer = make_customer(db, salon_a)
    for day, channel, status in ((6, "sms", "stub"), (7, "tg", "sent")):
        b = make_booking(db, salon_a, customer, service,
                         starts_at=_at(day, 12), status="done")
        db.add(MessageLog(salon_id=salon_a.id, customer_id=customer.id, booking_id=b.id,
                          channel=channel, kind="waitlist_offer", cost=Decimal("0"),
                          delivery_status=status, sent_at=_at(day - 1, 12)))
    db.flush()
    assert month_report(db, salon_a, YEAR, MONTH)["waitlist_visits"] == 1
