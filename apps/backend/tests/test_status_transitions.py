from datetime import datetime, timedelta, timezone

import pytest

from app.services.bookings import (
    InvalidTransition, autoclose, reschedule, set_status,
)
from tests.conftest import make_booking, make_customer, make_service, make_staff


@pytest.fixture
def env(db, salon_a):
    service = make_service(db, salon_a)
    staff = make_staff(db, salon_a)
    customer = make_customer(db, salon_a)
    return salon_a, service, staff, customer


def test_manual_transitions_allowed(db, env):
    salon, service, staff, customer = env
    b = make_booking(db, salon, customer, service, staff)
    set_status(db, b, "confirmed")
    assert b.status == "confirmed"
    set_status(db, b, "done")
    assert b.status == "done"
    # автозакрытие обратимо: владелец может исправить итог
    set_status(db, b, "no_show")
    assert b.status == "no_show"


def test_reminded_only_by_system(db, env):
    salon, service, staff, customer = env
    b = make_booking(db, salon, customer, service, staff)
    with pytest.raises(InvalidTransition):
        set_status(db, b, "reminded_24h")
    set_status(db, b, "reminded_24h", by_system=True)
    assert b.status == "reminded_24h"


def test_done_marks_customer_visit(db, env):
    salon, service, staff, customer = env
    starts = datetime.now(timezone.utc) - timedelta(days=1)
    b = make_booking(db, salon, customer, service, staff, starts_at=starts)
    assert customer.last_visit_at is None
    set_status(db, b, "done")
    assert customer.last_visit_at is not None
    assert customer.last_service_id == service.id


def test_reschedule_links_old_and_new(db, env):
    salon, service, staff, customer = env
    b = make_booking(db, salon, customer, service, staff)
    new_starts = datetime.now(timezone.utc) + timedelta(days=5)
    new_b = reschedule(db, salon, b, new_starts_at=new_starts, staff=staff, force=True)
    assert b.status == "rescheduled"
    assert b.rescheduled_to_id == new_b.id
    assert new_b.status == "new"
    assert new_b.customer_id == customer.id


def test_reschedule_of_closed_booking_forbidden(db, env):
    salon, service, staff, customer = env
    b = make_booking(db, salon, customer, service, staff, status="done")
    with pytest.raises(InvalidTransition):
        reschedule(db, salon, b, new_starts_at=datetime.now(timezone.utc),
                   staff=staff, force=True)


def test_autoclose(db, env):
    salon, service, staff, customer = env
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=30)
    b_confirmed = make_booking(db, salon, customer, service, staff,
                               starts_at=old, status="confirmed")
    b_reminded = make_booking(db, salon, customer, service, staff,
                              starts_at=old, status="reminded_24h")
    b_new = make_booking(db, salon, customer, service, staff,
                         starts_at=old, status="new")
    b_recent = make_booking(db, salon, customer, service, staff,
                            starts_at=now - timedelta(hours=2), status="confirmed")
    n = autoclose(db, now)
    assert n == 3
    assert b_confirmed.status == "done"
    assert b_reminded.status == "no_show"
    assert b_new.status == "no_show"
    assert b_recent.status == "confirmed"  # ещё не прошло 24 ч
