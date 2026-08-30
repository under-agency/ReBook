"""Статус клиента считается дважды: в Python (карточка) и в SQL (список с фильтром).
Эти две ветки обязаны давать одинаковый результат — иначе фильтр покажет одно,
а карточка другое.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Customer, Service
from app.services.customers import computed_status, status_expression
from tests.conftest import make_customer, make_service

TODAY = date(2026, 9, 15)


@pytest.mark.parametrize("cycle,days_ago,dnd", [
    (30, 0, False),      # только что был
    (30, 35, False),     # 30*1.2 = 36 → ещё активный
    (30, 37, False),     # спящий
    (30, 91, False),     # > 3 циклов → потерянный
    (21, 26, False),     # 21*1.2 = 25.2 — дробный порог
    (23, 28, False),     # 23*1.2 = 27.6 — округление не должно менять ответ
    (30, 40, True),      # исключён перевешивает всё
    (None, 400, False),  # услуга без цикла → всегда активный
])
def test_sql_matches_python(db, salon_a, cycle, days_ago, dnd):
    service = make_service(db, salon_a, repeat_cycle_days=cycle)
    customer = make_customer(db, salon_a, do_not_disturb=dnd)
    customer.last_visit_at = TODAY - timedelta(days=days_ago)
    customer.last_service_id = service.id
    db.flush()
    db.expire(customer)

    sql_status = db.execute(
        select(status_expression(TODAY))
        .select_from(Customer)
        .outerjoin(Service, Customer.last_service_id == Service.id)
        .where(Customer.id == customer.id)
    ).scalar_one()
    assert computed_status(customer, TODAY) == sql_status


def test_customer_without_visits_is_active(db, salon_a):
    customer = make_customer(db, salon_a)
    db.flush()
    sql_status = db.execute(
        select(status_expression(TODAY))
        .select_from(Customer)
        .outerjoin(Service, Customer.last_service_id == Service.id)
        .where(Customer.id == customer.id)
    ).scalar_one()
    assert sql_status == "active" == computed_status(customer, TODAY)
