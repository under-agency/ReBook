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


class FakeAdmin:
    """Копит уведомления в чат администратора салона."""

    def __init__(self, ok=True):
        self.ok = ok
        self.sent: list[tuple[int, str]] = []

    def __call__(self, salon, text):
        self.sent.append((salon.id, text))
        return self.ok


def test_first_reminder_sent_once(db, salon_a):
    service, staff, customer = _env(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport, admin = FakeTransport(), FakeAdmin()
    stats = send_reminders(db, now=NOW, transport=transport, notify_admin=admin)
    assert stats["first"] == 1
    assert b.status == "reminded_24h"
    assert len(transport.sent) == 1
    assert transport.sent[0]["kind"] == "reminder_24h"
    assert admin.sent == []  # дошло — админа не дёргаем
    # повторный запуск идемпотентен: статус уже reminded_24h, окно T-3 не настало
    stats = send_reminders(db, now=NOW, transport=transport, notify_admin=admin)
    assert stats == {"first": 0, "chase": 0, "unreached": 0}
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


def test_client_without_tg_left_to_admin(db, salon_a):
    """Без мессенджера напоминание уходит SMS-заглушкой, то есть не доходит:
    запись не напомнена, админ получает «позвоните», второй SMS не шлём."""
    service, staff, _ = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=None)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport, admin = FakeTransport(), FakeAdmin()
    stats = send_reminders(db, now=NOW, transport=transport, notify_admin=admin)
    assert stats == {"first": 0, "chase": 0, "unreached": 1}
    assert b.status == "new"
    assert len(admin.sent) == 1
    send_reminders(db, now=NOW + timedelta(hours=21), transport=transport, notify_admin=admin)
    sms = db.scalars(select(MessageLog).where(
        MessageLog.booking_id == b.id, MessageLog.channel == "sms")).all()
    assert len(sms) == 1  # второй SMS не шлём
    assert len(admin.sent) == 1


def test_paused_salon_sends_nothing(db, salon_b):
    salon_b.status = "paused"
    service, staff, customer = _env(db, salon_b)
    b = make_booking(db, salon_b, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport, admin = FakeTransport(), FakeAdmin()
    stats = send_reminders(db, now=NOW, transport=transport, notify_admin=admin)
    assert stats == {"first": 0, "chase": 0, "unreached": 0}
    assert b.status == "new"
    assert transport.sent == [] and admin.sent == []


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


# ── Сбой доставки (AI-44) ─────────────────────────────────────────────────
def test_blocked_bot_falls_back_and_asks_admin_to_call(db, salon_a):
    """Клиент заблокировал бота: пробуем SMS, он тоже не дошёл (stub) —
    запись не напомнена, админ получает «позвоните», повторно не шлём."""
    service, staff, customer = _env(db, salon_a)
    customer.name, customer.phone = "Ольга", "+79001112233"
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    transport, admin = FakeTransport(ok=False), FakeAdmin()
    stats = send_reminders(db, now=NOW, transport=transport, notify_admin=admin)
    assert stats == {"first": 0, "chase": 0, "unreached": 1}
    assert b.status == "new"
    logs = db.scalars(select(MessageLog).where(MessageLog.booking_id == b.id)
                      .order_by(MessageLog.id)).all()
    assert [(m.channel, m.delivery_status) for m in logs] == [("tg", "failed"), ("sms", "stub")]
    [(salon_id, text)] = admin.sent
    assert salon_id == salon_a.id
    for part in ("Ольга", "+79001112233", "Стрижка", "8 сентября в 11:00", "Позвоните"):
        assert part in text
    # следующий запуск через 15 минут: ни нового сообщения, ни второго уведомления
    stats = send_reminders(db, now=NOW + timedelta(minutes=15),
                           transport=transport, notify_admin=admin)
    assert stats == {"first": 0, "chase": 0, "unreached": 0}
    assert len(transport.sent) == 1 and len(admin.sent) == 1


def test_blocked_bot_without_phone_asks_admin(db, salon_a):
    service, staff, customer = _env(db, salon_a)
    customer.phone = None
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=23))
    admin = FakeAdmin()
    stats = send_reminders(db, now=NOW, transport=FakeTransport(ok=False), notify_admin=admin)
    assert stats["unreached"] == 1 and b.status == "new"
    logs = db.scalars(select(MessageLog).where(MessageLog.booking_id == b.id)).all()
    assert [(m.channel, m.delivery_status) for m in logs] == [("tg", "failed")]
    assert len(admin.sent) == 1


def test_chase_needs_delivered_tg_reminder(db, salon_a):
    """Первое напоминание дошло SMS после сбоя Telegram — второе SMS не шлём.
    Пока SMS — заглушка, так выйдет, когда их подключат (stub → sent)."""
    service, staff, customer = _env(db, salon_a)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=NOW + timedelta(hours=2), status="reminded_24h")
    for channel, status in (("tg", "failed"), ("sms", "sent")):
        db.add(MessageLog(salon_id=salon_a.id, customer_id=customer.id, booking_id=b.id,
                          channel=channel, kind="reminder_24h", cost=Decimal("0"),
                          delivery_status=status, sent_at=NOW - timedelta(hours=21)))
    db.flush()
    stats = send_reminders(db, now=NOW, transport=FakeTransport(), notify_admin=FakeAdmin())
    assert stats["chase"] == 0
    assert b.status == "reminded_24h"


def test_send_tries_next_channel_after_tg_failure(db, salon_a):
    customer = make_customer(db, salon_a, tg_id=555)
    res = channels.send(db, salon_a, customer, "reminder_24h", "тест",
                        transport=FakeTransport(ok=False), now=NOW)
    assert (res.channel, res.delivery_status) == ("sms", "stub")
    tg = db.scalars(select(MessageLog.delivery_status).where(
        MessageLog.customer_id == customer.id, MessageLog.channel == "tg")).all()
    assert tg == ["failed"]


def test_admin_notify_needs_linked_chat(salon_a):
    """Чат админа не привязан (/admin в боте) — слать некуда, в Telegram не ходим."""
    assert salon_a.admin_tg_chat_id is None
    assert channels.telegram_admin_notify(salon_a, "тест") is False
