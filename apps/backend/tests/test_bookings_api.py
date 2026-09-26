"""Ручная запись из кабинета: конфликты как предупреждение, а не запрет.

Ключевое требование 10-crm-logic.md — конфликт показывается владельцу
с кнопкой «всё равно записать», жёсткого запрета нет.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models import AuditLog, Booking, Customer, MessageLog
from tests.conftest import (
    login, make_booking, make_customer, make_service, make_staff, make_user,
    next_working_slot,
)


def _env(db, salon, client):
    service = make_service(db, salon)
    staff = make_staff(db, salon)
    login(client, make_user(db, salon))
    return service, staff


def _local(salon, moment) -> str:
    """Как время приходит из <input datetime-local> — наивная строка в поясе салона."""
    return moment.astimezone(ZoneInfo(salon.timezone)).strftime("%Y-%m-%dT%H:%M")


def test_create_booking_for_existing_customer(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "customer_id": customer.id, "service_id": service.id,
        "staff_id": staff.id, "starts_at": slot.isoformat(), "note": "по телефону",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "new"

    booking = db.get(Booking, body["id"])
    assert booking.source == "manual"  # запись из кабинета
    assert booking.note == "по телефону"
    assert booking.starts_at == slot


def test_naive_time_is_read_in_salon_timezone(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "customer_id": customer.id, "service_id": service.id,
        "staff_id": staff.id, "starts_at": _local(salon_a, slot),
    })
    assert r.status_code == 200, r.text
    assert db.get(Booking, r.json()["id"]).starts_at == slot


def test_manual_booking_joins_the_reminder_cascade(db, client, salon_a):
    """Телефонная запись должна жить по общим правилам: статус new и подтверждение."""
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a, tg_id=31337)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "customer_id": customer.id, "service_id": service.id,
        "staff_id": staff.id, "starts_at": slot.isoformat(),
    })
    booking_id = r.json()["id"]
    assert db.get(Booking, booking_id).status == "new"
    confirm = db.scalars(select(MessageLog).where(
        MessageLog.booking_id == booking_id, MessageLog.kind == "confirm")).one()
    assert confirm.channel == "tg"


def test_create_booking_with_new_customer_normalizes_phone(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "new_customer": {"name": "Пётр", "phone": "8 (900) 000-00-01"},
        "service_id": service.id, "staff_id": staff.id,
        "starts_at": slot.isoformat(),
    })
    assert r.status_code == 200, r.text
    customer = db.get(Customer, db.get(Booking, r.json()["id"]).customer_id)
    assert customer.name == "Пётр"
    assert customer.phone == "+79000000001"


def test_new_customer_with_known_phone_is_not_duplicated(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    existing = make_customer(db, salon_a, name="Анна", phone="+79000000001")
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "new_customer": {"name": "Анна", "phone": "+7 900 000-00-01"},
        "service_id": service.id, "staff_id": staff.id,
        "starts_at": slot.isoformat(),
    })
    assert r.status_code == 200, r.text
    assert db.get(Booking, r.json()["id"]).customer_id == existing.id
    assert db.scalar(select(func.count(Customer.id)).where(
        Customer.salon_id == salon_a.id)) == 1


def test_unparsable_phone_rejected(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "new_customer": {"name": "Пётр", "phone": "звоните в дверь"},
        "service_id": service.id, "staff_id": staff.id,
        "starts_at": slot.isoformat(),
    })
    assert r.status_code == 422


def test_booking_without_customer_rejected(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "service_id": service.id, "staff_id": staff.id,
        "starts_at": slot.isoformat(),
    })
    assert r.status_code == 422


# ── Конфликты: предупреждение, а не запрет ────────────────────────────────
def test_busy_slot_returns_warning_and_force_overrides_it(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    make_booking(db, salon_a, customer, service, staff, starts_at=slot)

    payload = {"customer_id": customer.id, "service_id": service.id,
               "staff_id": staff.id, "starts_at": slot.isoformat()}
    r = client.post("/api/bookings", json=payload)
    assert r.status_code == 409
    warnings = r.json()["detail"]["warnings"]
    assert any("пересекается" in w for w in warnings)

    r = client.post("/api/bookings", json={**payload, "force": True})
    assert r.status_code == 200, r.text
    assert db.scalar(select(func.count(Booking.id)).where(
        Booking.salon_id == salon_a.id)) == 2


def test_time_outside_work_hours_warns(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    # тот же рабочий день, но 07:00 — салон открывается в 10:00
    night = next_working_slot(salon_a, duration_min=service.duration_min) - timedelta(hours=5)

    payload = {"customer_id": customer.id, "service_id": service.id,
               "staff_id": staff.id, "starts_at": night.isoformat()}
    r = client.post("/api/bookings", json=payload)
    assert r.status_code == 409
    assert any("рабочих часов" in w for w in r.json()["detail"]["warnings"])

    r = client.post("/api/bookings", json={**payload, "force": True})
    assert r.status_code == 200, r.text


def test_slot_is_free_for_another_staff(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    other_staff = make_staff(db, salon_a, name="Ольга")
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    make_booking(db, salon_a, customer, service, staff, starts_at=slot)

    r = client.post("/api/bookings", json={
        "customer_id": customer.id, "service_id": service.id,
        "staff_id": other_staff.id, "starts_at": slot.isoformat(),
    })
    assert r.status_code == 200, r.text


# ── Свободные окна ────────────────────────────────────────────────────────
def test_free_slots_endpoint_hides_taken_time(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    day = slot.astimezone(ZoneInfo(salon_a.timezone)).date()
    params = {"service_id": service.id, "staff_id": staff.id, "date": day.isoformat()}

    before = client.get("/api/bookings/free-slots", params=params).json()["slots"]
    assert "12:00" in [s["label"] for s in before]

    make_booking(db, salon_a, customer, service, staff, starts_at=slot)
    after = client.get("/api/bookings/free-slots", params=params).json()["slots"]
    assert "12:00" not in [s["label"] for s in after]
    assert len(after) < len(before)


def test_free_slots_empty_on_day_off(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    salon_a.work_hours = {"mon": ["10:00", "20:00"]}
    db.flush()
    # при таких часах любое воскресенье — выходной
    today = datetime.now(ZoneInfo(salon_a.timezone)).date()
    sunday = today + timedelta(days=((6 - today.weekday()) % 7) or 7)

    r = client.get("/api/bookings/free-slots", params={
        "service_id": service.id, "staff_id": staff.id, "date": sunday.isoformat()})
    assert r.json()["slots"] == []


# ── Перенос и смена статуса ───────────────────────────────────────────────
def test_reschedule_closes_old_and_creates_new(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=next_working_slot(salon_a, duration_min=service.duration_min))
    new_slot = next_working_slot(salon_a, days_ahead=3, hour=15,
                                 duration_min=service.duration_min)

    r = client.post(f"/api/bookings/{b.id}/reschedule",
                    json={"starts_at": new_slot.isoformat()})
    assert r.status_code == 200, r.text
    assert b.status == "rescheduled"
    new = db.get(Booking, r.json()["id"])
    assert new.id == b.rescheduled_to_id
    assert new.starts_at == new_slot and new.status == "new"


def test_reschedule_of_closed_booking_is_422(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff, status="done")
    new_slot = next_working_slot(salon_a, days_ahead=3, duration_min=service.duration_min)

    r = client.post(f"/api/bookings/{b.id}/reschedule",
                    json={"starts_at": new_slot.isoformat()})
    assert r.status_code == 422


def test_system_status_cannot_be_set_by_hand(db, client, salon_a):
    """reminded_* ставит только воркер — иначе каскад и отчёт разъедутся."""
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff)

    assert client.patch(f"/api/bookings/{b.id}",
                        json={"status": "reminded_24h"}).status_code == 422
    assert client.patch(f"/api/bookings/{b.id}",
                        json={"status": "rescheduled"}).status_code == 422
    assert b.status == "new"
    assert client.patch(f"/api/bookings/{b.id}",
                        json={"status": "no_show"}).status_code == 200
    assert b.status == "no_show"


def test_marking_done_updates_last_visit(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    assert customer.last_visit_at is None
    b = make_booking(db, salon_a, customer, service, staff)

    assert client.patch(f"/api/bookings/{b.id}", json={"status": "done"}).status_code == 200
    assert customer.last_visit_at == b.starts_at.astimezone(
        ZoneInfo(salon_a.timezone)).date()
    assert customer.last_service_id == service.id


# ── Журнал и аудит ────────────────────────────────────────────────────────
def test_list_filters_by_date_status_and_pages(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    day = slot.astimezone(ZoneInfo(salon_a.timezone)).date()
    make_booking(db, salon_a, customer, service, staff, starts_at=slot)
    make_booking(db, salon_a, customer, service, staff,
                 starts_at=slot + timedelta(hours=2), status="cancelled")
    make_booking(db, salon_a, customer, service, staff,
                 starts_at=slot + timedelta(days=30))

    same_day = client.get("/api/bookings", params={
        "date_from": day.isoformat(), "date_to": day.isoformat()}).json()
    assert same_day["total"] == 2

    only_new = client.get("/api/bookings", params={
        "date_from": day.isoformat(), "date_to": day.isoformat(),
        "status": "new"}).json()
    assert only_new["total"] == 1

    paged = client.get("/api/bookings", params={"page_size": 1}).json()
    assert paged["total"] == 3 and len(paged["items"]) == 1


def test_creating_booking_is_audited(db, client, salon_a):
    service, staff = _env(db, salon_a, client)
    customer = make_customer(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = client.post("/api/bookings", json={
        "customer_id": customer.id, "service_id": service.id,
        "staff_id": staff.id, "starts_at": slot.isoformat()})
    row = db.scalars(select(AuditLog).where(
        AuditLog.entity == "booking", AuditLog.action == "create")).one()
    assert row.entity_id == r.json()["id"]
    assert row.salon_id == salon_a.id
    assert row.is_support is False
