"""Админка: онбординг салона формой и мониторинг здоровья.

Смысл раздела — подключить клиента без правки базы руками (docs/10-crm-logic.md),
поэтому тесты идут через HTTP ровно так, как это делает SalonNewPage.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import AuditLog, MessageLog, Payment, Salon, Service, User
from tests.conftest import login, make_customer, make_salon, make_user

NOW = datetime.now(timezone.utc)


def _admin(db, client):
    admin = make_user(db, None, role="superadmin")
    login(client, admin)
    return admin


def _find(items, salon_id):
    return next(i for i in items if i["id"] == salon_id)


def _msg(db, salon, customer, **kw):
    row = MessageLog(salon_id=salon.id, customer_id=customer.id,
                     channel=kw.pop("channel", "tg"), kind=kw.pop("kind", "reminder_24h"),
                     cost=kw.pop("cost", Decimal("0")),
                     delivery_status=kw.pop("delivery_status", "sent"), **kw)
    db.add(row)
    return row


# ── Форма нового салона ───────────────────────────────────────────────────
def test_create_salon_produces_ready_tenant(db, client):
    _admin(db, client)

    r = client.post("/api/admin/salons", json={
        "name": "Барбершоп на Ленина", "niche": "салон",
        "owner_email": "owner@example.com", "tg_bot_token": "111:aaa",
        "avg_check": 2500, "sms_limit_month": 150, "timezone": "Asia/Yekaterinburg",
    })
    assert r.status_code == 200, r.text
    body = r.json()

    salon = db.get(Salon, body["salon"]["id"])
    assert salon.status == "onboarding", "новый салон не должен сразу рассылать"
    assert salon.timezone == "Asia/Yekaterinburg"
    assert salon.sms_limit_month == 150
    assert salon.texts, "тексты сообщений заполняются заготовкой"

    # ниша подтянула заготовки услуг — владельцу не с нуля
    services = db.scalars(select(Service).where(Service.salon_id == salon.id)).all()
    assert len(services) == 4
    assert "Женская стрижка" in [s.name for s in services]

    # владелец приглашён одноразовой ссылкой, пароля у него ещё нет
    owner = db.scalars(select(User).where(User.salon_id == salon.id)).one()
    assert owner.role == "owner" and owner.pass_hash is None
    assert owner.invite_token_hash and owner.invite_expires_at > NOW
    assert body["invite_link"].startswith("/invite/")


def test_salon_without_niche_has_no_preset_services(db, client):
    _admin(db, client)
    r = client.post("/api/admin/salons",
                    json={"name": "Без ниши", "owner_email": "a@example.com"})
    assert r.status_code == 200, r.text
    salon_id = r.json()["salon"]["id"]
    assert db.scalars(select(Service).where(Service.salon_id == salon_id)).all() == []


def test_duplicate_owner_email_rejected(db, client):
    _admin(db, client)
    client.post("/api/admin/salons", json={"name": "Первый", "owner_email": "one@example.com"})

    r = client.post("/api/admin/salons", json={"name": "Второй", "owner_email": "ONE@example.com"})
    assert r.status_code == 409, "почта владельца сверяется без учёта регистра"


def test_niches_expose_service_presets(db, client):
    _admin(db, client)
    niches = {n["key"]: n for n in client.get("/api/admin/niches").json()["niches"]}
    assert {"салон", "автосервис", "стоматология"} <= set(niches)
    oil = next(s for s in niches["автосервис"]["services"] if s["name"] == "Замена масла")
    assert oil["duration_min"] == 30 and oil["repeat_cycle_days"] == 180


def test_invite_can_be_reissued(db, client, salon_a):
    _admin(db, client)
    owner = make_user(db, salon_a)
    old_hash = owner.invite_token_hash

    r = client.post(f"/api/admin/salons/{salon_a.id}/invite")
    assert r.status_code == 200, r.text
    assert r.json()["owner_email"] == owner.email
    assert owner.invite_token_hash != old_hash


# ── Мониторинг здоровья салонов ───────────────────────────────────────────
def test_salon_list_reports_health(db, client, salon_a):
    _admin(db, client)
    customer = make_customer(db, salon_a)
    _msg(db, salon_a, customer, sent_at=NOW - timedelta(hours=1))
    _msg(db, salon_a, customer, delivery_status="failed", sent_at=NOW - timedelta(hours=2))
    _msg(db, salon_a, customer, delivery_status="failed", sent_at=NOW - timedelta(hours=30))
    _msg(db, salon_a, customer, channel="sms", cost=Decimal("4"),
         delivery_status="stub", sent_at=NOW - timedelta(hours=3))
    db.flush()

    health = _find(client.get("/api/admin/salons").json()["items"], salon_a.id)["health"]
    assert health["errors_24h"] == 1, "ошибка старше суток не должна учитываться"
    assert health["sms_used"] == 1
    assert health["last_activity"] is not None


def test_sms_counter_covers_current_month_only(db, client, salon_a):
    _admin(db, client)
    customer = make_customer(db, salon_a)
    _msg(db, salon_a, customer, channel="sms", cost=Decimal("4"),
         delivery_status="stub", sent_at=NOW)
    _msg(db, salon_a, customer, channel="sms", cost=Decimal("4"),
         delivery_status="stub", sent_at=NOW - timedelta(days=45))
    db.flush()

    health = _find(client.get("/api/admin/salons").json()["items"], salon_a.id)["health"]
    assert health["sms_used"] == 1


def test_salon_without_activity_reports_empty_health(db, client, salon_a):
    _admin(db, client)
    health = _find(client.get("/api/admin/salons").json()["items"], salon_a.id)["health"]
    assert health == {"last_activity": None, "errors_24h": 0, "sms_used": 0}


def test_problem_salons_are_listed_first(db, client):
    _admin(db, client)
    healthy = make_salon(db, "Здоровый", status="active")
    broken = make_salon(db, "Сломанный", status="active")
    _msg(db, broken, make_customer(db, broken),
         delivery_status="failed", sent_at=NOW - timedelta(hours=1))
    db.flush()

    ids = [i["id"] for i in client.get("/api/admin/salons").json()["items"]]
    assert ids.index(broken.id) < ids.index(healthy.id)


# ── Статус салона и оплата ────────────────────────────────────────────────
def test_payment_lifts_paused_salon(db, client):
    _admin(db, client)
    salon = make_salon(db, "Должник", status="paused")

    r = client.post(f"/api/admin/salons/{salon.id}/payments", json={
        "amount": 5000, "period_start": "2026-09-01",
        "period_end": "2026-10-01", "paid_at": "2026-09-02",
    })
    assert r.status_code == 200, r.text
    assert r.json()["salon_status"] == "active"
    assert salon.status == "active"
    assert salon.next_payment_at.isoformat() == "2026-10-01"
    assert db.scalars(select(Payment).where(Payment.salon_id == salon.id)).one().amount == 5000


def test_unpaid_invoice_does_not_change_status(db, client):
    _admin(db, client)
    salon = make_salon(db, "Счёт выставлен", status="grace")

    r = client.post(f"/api/admin/salons/{salon.id}/payments", json={
        "amount": 5000, "period_start": "2026-09-01", "period_end": "2026-10-01",
    })
    assert r.status_code == 200, r.text
    assert salon.status == "grace"


def test_status_change_and_feature_flags_are_audited(db, client, salon_a):
    _admin(db, client)

    r = client.patch(f"/api/admin/salons/{salon_a.id}", json={
        "status": "paused", "feature_flags": {"waitlist": True}})
    assert r.status_code == 200, r.text
    assert salon_a.status == "paused"
    assert salon_a.feature_flags == {"waitlist": True}

    row = db.scalars(select(AuditLog).where(
        AuditLog.entity == "salon", AuditLog.action == "update")).one()
    assert row.before["status"] == "active"
    assert row.after["status"] == "paused"
    assert row.is_support is False, "правка из админки — не режим поддержки"


def test_unknown_salon_is_404(db, client):
    _admin(db, client)
    assert client.get("/api/admin/salons/999999").status_code == 404
    assert client.patch("/api/admin/salons/999999", json={"status": "paused"}).status_code == 404


# ── Режим поддержки ───────────────────────────────────────────────────────
def test_leaving_support_mode_revokes_access_and_is_audited(db, client, salon_a):
    admin = _admin(db, client)
    client.post(f"/api/admin/salons/{salon_a.id}/impersonate")
    assert client.get("/api/bookings").status_code == 200

    assert client.post("/api/admin/impersonate/stop").status_code == 200
    assert client.get("/api/bookings").status_code == 403, "выход не снял доступ к салону"

    actions = [r.action for r in db.scalars(select(AuditLog).where(
        AuditLog.salon_id == salon_a.id, AuditLog.user_id == admin.id)).all()]
    assert "support_enter" in actions and "support_exit" in actions


def test_support_can_switch_between_salons(db, client, salon_a, salon_b):
    _admin(db, client)
    client.post(f"/api/admin/salons/{salon_a.id}/impersonate")
    client.post(f"/api/admin/salons/{salon_b.id}/impersonate")

    make_customer(db, salon_b, name="Из салона Б")
    db.flush()
    names = [c["name"] for c in client.get("/api/customers").json()["items"]]
    assert names == ["Из салона Б"]
