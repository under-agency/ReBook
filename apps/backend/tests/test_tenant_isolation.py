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
