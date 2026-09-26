"""Жизненный цикл салона: onboarding → active → grace → paused.

Смысл статусной модели в том, какие рассылки в каком статусе идут
(docs/10-crm-logic.md), поэтому переходы проверяются вместе с channels.
"""
from datetime import date, timedelta

from sqlalchemy import select

from app import channels
from app.models import AuditLog, Salon
from app.worker.billing import update_billing_statuses
from tests.conftest import (
    FakeTransport, login, make_customer, make_salon, make_service, make_user,
)


# ── Онбординг-мастер ──────────────────────────────────────────────────────
def test_steps_are_saved_and_never_go_back(db, client):
    salon = make_salon(db, "Новый", status="onboarding")
    login(client, make_user(db, salon))

    assert client.post("/api/onboarding/step", json={"step": 2}).json()["onboarding_step"] == 2
    # возврат на шаг назад в мастере не должен терять прогресс
    assert client.post("/api/onboarding/step", json={"step": 1}).json()["onboarding_step"] == 2
    assert client.post("/api/onboarding/step", json={"step": 4}).json()["onboarding_step"] == 4


def test_step_out_of_range_rejected(db, client):
    salon = make_salon(db, "Новый", status="onboarding")
    login(client, make_user(db, salon))

    assert client.post("/api/onboarding/step", json={"step": 0}).status_code == 422
    assert client.post("/api/onboarding/step", json={"step": 5}).status_code == 422


def test_cannot_finish_onboarding_without_services(db, client):
    salon = make_salon(db, "Новый", status="onboarding")
    login(client, make_user(db, salon))

    r = client.post("/api/onboarding/complete")
    assert r.status_code == 422
    assert "услугу" in r.json()["detail"]
    assert salon.status == "onboarding"


def test_inactive_service_does_not_count_as_ready(db, client):
    salon = make_salon(db, "Новый", status="onboarding")
    service = make_service(db, salon)
    service.is_active = False
    db.flush()
    login(client, make_user(db, salon))

    assert client.post("/api/onboarding/complete").status_code == 422


def test_completing_onboarding_activates_salon_and_is_audited(db, client):
    salon = make_salon(db, "Новый", status="onboarding")
    make_service(db, salon)
    login(client, make_user(db, salon))

    r = client.post("/api/onboarding/complete")
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert salon.status == "active"
    assert salon.onboarding_step == 4

    row = db.scalars(select(AuditLog).where(
        AuditLog.action == "status_change", AuditLog.entity == "salon")).one()
    assert row.before == {"status": "onboarding"}
    assert row.after == {"status": "active"}


def test_completing_twice_is_idempotent(db, client):
    salon = make_salon(db, "Новый", status="onboarding")
    make_service(db, salon)
    login(client, make_user(db, salon))

    client.post("/api/onboarding/complete")
    r = client.post("/api/onboarding/complete")
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert len(db.scalars(select(AuditLog).where(
        AuditLog.action == "status_change")).all()) == 1


def test_onboarding_blocks_sending_until_completed(db, client):
    """До прохождения мастера рассылки заблокированы — главный смысл статуса."""
    salon = make_salon(db, "Новый", status="onboarding")
    make_service(db, salon)
    customer = make_customer(db, salon, tg_id=1234)
    transport = FakeTransport()

    assert channels.send(db, salon, customer, "reminder_24h", "тест",
                         transport=transport) is None
    assert transport.sent == []

    login(client, make_user(db, salon))
    client.post("/api/onboarding/complete")

    sent = channels.send(db, salon, customer, "reminder_24h", "тест", transport=transport)
    assert sent is not None and sent.channel == "tg"


# ── Биллинг-статусы ───────────────────────────────────────────────────────
TODAY = date(2026, 9, 15)


def _salon_due(db, name, status, days_overdue):
    return make_salon(db, name, status=status,
                      next_payment_at=TODAY - timedelta(days=days_overdue))


def test_one_day_overdue_moves_active_to_grace(db):
    salon = _salon_due(db, "Просрочка 1", "active", 1)
    assert update_billing_statuses(db, TODAY) == [(salon.id, "grace")]
    assert salon.status == "grace"


def test_paid_salon_untouched(db):
    salon = _salon_due(db, "Оплачен", "active", -3)  # платёж ещё впереди
    assert update_billing_statuses(db, TODAY) == []
    assert salon.status == "active"


def test_due_today_is_not_overdue(db):
    salon = _salon_due(db, "Сегодня", "active", 0)
    assert update_billing_statuses(db, TODAY) == []
    assert salon.status == "active"


def test_eight_days_overdue_pauses(db):
    salon = _salon_due(db, "Просрочка 8", "grace", 8)
    assert update_billing_statuses(db, TODAY) == [(salon.id, "paused")]
    assert salon.status == "paused"


def test_grace_does_not_flip_back_and_forth(db):
    salon = _salon_due(db, "В grace", "grace", 3)
    assert update_billing_statuses(db, TODAY) == []
    assert salon.status == "grace"


def test_salon_without_payment_date_is_skipped(db):
    salon = make_salon(db, "Без платежа", status="active", next_payment_at=None)
    assert update_billing_statuses(db, TODAY) == []
    assert salon.status == "active"


def test_paused_and_archived_are_not_reprocessed(db):
    paused = _salon_due(db, "Уже paused", "paused", 30)
    archived = _salon_due(db, "Архив", "archived", 30)
    assert update_billing_statuses(db, TODAY) == []
    assert paused.status == "paused" and archived.status == "archived"


def test_billing_change_is_audited(db):
    salon = _salon_due(db, "Просрочка", "active", 10)
    update_billing_statuses(db, TODAY)
    db.flush()

    row = db.scalars(select(AuditLog).where(
        AuditLog.action == "billing_status", AuditLog.salon_id == salon.id)).one()
    assert row.before == {"status": "active"}
    assert row.after == {"status": "paused", "overdue_days": 10}


def test_grace_still_sends_but_paused_does_not(db):
    """Мягкое отключение: в grace клиент салона ничего не замечает."""
    grace = _salon_due(db, "Grace", "grace", 3)
    paused = _salon_due(db, "Paused", "paused", 30)
    transport = FakeTransport()

    in_grace = make_customer(db, grace, tg_id=555)
    in_paused = make_customer(db, paused, tg_id=556)

    assert channels.send(db, grace, in_grace, "reminder_24h", "тест",
                         transport=transport) is not None
    assert channels.send(db, paused, in_paused, "reminder_24h", "тест",
                         transport=transport) is None


def test_billing_run_is_idempotent(db):
    salon = _salon_due(db, "Просрочка", "active", 1)
    assert update_billing_statuses(db, TODAY) == [(salon.id, "grace")]
    assert update_billing_statuses(db, TODAY) == []
    assert db.scalar(select(Salon).where(Salon.id == salon.id)).status == "grace"
