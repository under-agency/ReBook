"""Главный тест безопасности: пользователь салона А не видит данные салона Б.

Чужой объект — 404, не 403: не подтверждаем существование (docs/10-crm-logic.md).
"""
from tests.conftest import (
    login, make_booking, make_customer, make_service, make_staff, make_user,
)


def _fixtures(db, salon):
    service = make_service(db, salon)
    staff = make_staff(db, salon)
    customer = make_customer(db, salon)
    booking = make_booking(db, salon, customer, service, staff)
    return service, staff, customer, booking


def test_owner_cannot_access_foreign_objects(db, client, salon_a, salon_b):
    _fixtures(db, salon_a)
    service_b, staff_b, customer_b, booking_b = _fixtures(db, salon_b)
    owner_a = make_user(db, salon_a)
    login(client, owner_a)

    assert client.get(f"/api/bookings/{booking_b.id}").status_code == 404
    assert client.patch(f"/api/bookings/{booking_b.id}",
                        json={"status": "confirmed"}).status_code == 404
    assert client.get(f"/api/customers/{customer_b.id}").status_code == 404
    assert client.patch(f"/api/customers/{customer_b.id}",
                        json={"do_not_disturb": True}).status_code == 404
    assert client.patch(f"/api/settings/services/{service_b.id}",
                        json={"price": 1}).status_code == 404
    assert client.patch(f"/api/settings/staff/{staff_b.id}",
                        json={"name": "x"}).status_code == 404


def test_lists_contain_only_own_rows(db, client, salon_a, salon_b):
    _, _, customer_a, booking_a = _fixtures(db, salon_a)
    _, _, customer_b, booking_b = _fixtures(db, salon_b)
    owner_a = make_user(db, salon_a)
    login(client, owner_a)

    ids = {b["id"] for b in client.get("/api/bookings").json()["items"]}
    assert booking_a.id in ids and booking_b.id not in ids

    ids = {c["id"] for c in client.get("/api/customers").json()["items"]}
    assert customer_a.id in ids and customer_b.id not in ids


def test_staff_role_restrictions(db, client, salon_a):
    staff_user = make_user(db, salon_a, role="staff")
    login(client, staff_user)
    assert client.get("/api/settings").status_code == 403
    assert client.get("/api/reports/2026-01").status_code == 403
    assert client.get("/api/bookings").status_code == 200  # записи ведёт


def test_owner_cannot_access_admin(db, client, salon_a):
    owner = make_user(db, salon_a)
    login(client, owner)
    assert client.get("/api/admin/salons").status_code == 403


def test_superadmin_needs_impersonation_for_salon_data(db, client, salon_a):
    admin = make_user(db, None, role="superadmin")
    login(client, admin)
    assert client.get("/api/bookings").status_code == 403
    r = client.post(f"/api/admin/salons/{salon_a.id}/impersonate")
    assert r.status_code == 200
    assert client.get("/api/bookings").status_code == 200


def test_impersonation_is_audited_as_support(db, client, salon_a):
    make_user(db, salon_a)  # владелец существует
    admin = make_user(db, None, role="superadmin")
    login(client, admin)
    client.post(f"/api/admin/salons/{salon_a.id}/impersonate")
    client.patch("/api/settings", json={"avg_check": 3000})
    from app.models import AuditLog
    from sqlalchemy import select
    rows = db.scalars(select(AuditLog).where(
        AuditLog.salon_id == salon_a.id, AuditLog.action == "update")).all()
    assert rows and all(r.is_support for r in rows)


def test_aggregates_count_only_own_salon(db, client, salon_a, salon_b):
    """Дашборд и отчёт не должны видеть чужие записи."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from app.models import MessageLog

    for salon, count in ((salon_a, 1), (salon_b, 5)):
        service = make_service(db, salon)
        customer = make_customer(db, salon)
        salon.avg_check = Decimal("2000")
        for i in range(count):
            b = make_booking(db, salon, customer, service,
                             starts_at=datetime.now(timezone.utc) - timedelta(days=i + 1),
                             status="done")
            db.add(MessageLog(salon_id=salon.id, customer_id=customer.id, booking_id=b.id,
                              channel="tg", kind="reminder_24h", cost=Decimal("0"),
                              delivery_status="sent", sent_at=b.starts_at))
    db.flush()

    login(client, make_user(db, salon_a))
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    summary = client.get(f"/api/dashboard/summary?month={month}").json()
    assert summary["bookings_total"] <= 1, "в сводку попали записи чужого салона"

    report = client.get(f"/api/reports/{month}").json()
    assert report["bookings_total"] == summary["bookings_total"]


def test_every_list_endpoint_is_scoped(db, client, salon_a, salon_b):
    """Списочные эндпоинты не отдают объекты чужого салона."""
    from app.models import MessageLog

    _fixtures(db, salon_a)
    service_b, staff_b, customer_b, booking_b = _fixtures(db, salon_b)
    message_b = MessageLog(salon_id=salon_b.id, customer_id=customer_b.id,
                           booking_id=booking_b.id, channel="tg", kind="reminder_24h",
                           text="чужое", delivery_status="sent")
    db.add(message_b)
    db.flush()
    login(client, make_user(db, salon_a))

    foreign = {
        "/api/bookings": booking_b.id,
        "/api/customers": customer_b.id,
        "/api/settings/services": service_b.id,
        "/api/settings/staff": staff_b.id,
        "/api/messages": message_b.id,
    }
    for path, foreign_id in foreign.items():
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}"
        ids = {item["id"] for item in r.json()["items"]}
        assert foreign_id not in ids, f"{path} отдал объект чужого салона"


def test_customer_status_filter_is_scoped(db, client, salon_a, salon_b):
    """Фильтр статуса считается в SQL — проверяем, что он не выходит за салон."""
    make_customer(db, salon_b, name="Чужой")
    make_customer(db, salon_a, name="Свой")
    login(client, make_user(db, salon_a))
    names = {c["name"] for c in client.get("/api/customers?status=active").json()["items"]}
    assert "Чужой" not in names
