"""Автомат записи в боте: путь клиента, кнопки напоминания, гейты по статусу.

`dialogs.py` канал-агностичный, поэтому тесты дёргают его напрямую — ровно так
же, как это делает адаптер `telegram.py`. Никакого Telegram здесь не нужно.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.bots import dialogs
from app.models import Booking, Customer, DialogState, MessageLog
from tests.conftest import (
    make_booking, make_customer, make_service, make_staff, next_working_slot,
)

TG_ID = 424242


def _env(db, salon):
    return make_service(db, salon), make_staff(db, salon)


def _callbacks(reply) -> list[str]:
    return [cb for row in reply.buttons for _, cb in row]


def _local_day(salon, moment):
    return moment.astimezone(ZoneInfo(salon.timezone)).date()


def _cb(moment) -> str:
    """UTC-время в том виде, в каком оно едет в callback_data кнопки."""
    return moment.strftime("%Y-%m-%dT%H:%M")


# ── Гейты по статусу салона ───────────────────────────────────────────────
def test_start_shows_main_menu(db, salon_a):
    reply = dialogs.handle_start(db, salon_a, TG_ID, "Пётр", None)
    assert salon_a.name in reply.text
    assert "Пётр" in reply.text
    assert "m|book" in _callbacks(reply)


def test_onboarding_salon_does_not_take_bookings(db, salon_b):
    salon_b.status = "onboarding"
    reply = dialogs.handle_start(db, salon_b, TG_ID, None, None)
    assert "скоро откроется" in reply.text
    assert reply.buttons == []


def test_paused_salon_still_answers_and_books(db, salon_b):
    """Мягкое отключение: рассылки стоят, но бот отвечает — клиенты не виноваты."""
    salon_b.status = "paused"
    service, staff = _env(db, salon_b)
    make_customer(db, salon_b, tg_id=TG_ID)
    slot = next_working_slot(salon_b, duration_min=service.duration_min)

    assert "m|book" in _callbacks(dialogs.handle_start(db, salon_b, TG_ID, None, None))
    reply = dialogs.handle_callback(
        db, salon_b, TG_ID, None, f"t|{service.id}|{staff.id}|{_cb(slot)}")
    assert "Записал" in reply.text
    # запись создана, а вот подтверждение в paused не уходит — гейт в channels
    booking = db.scalars(select(Booking).where(Booking.salon_id == salon_b.id)).one()
    assert db.scalar(select(func.count(MessageLog.id)).where(
        MessageLog.booking_id == booking.id)) == 0


# ── Deep link из SMS ──────────────────────────────────────────────────────
def test_deep_link_binds_phone_customer_to_telegram(db, salon_a):
    customer = make_customer(db, salon_a, tg_id=None)
    dialogs.handle_start(db, salon_a, TG_ID, None, f"c_{customer.id}")
    assert customer.tg_id == TG_ID


def test_deep_link_of_foreign_salon_is_ignored(db, salon_a, salon_b):
    foreign = make_customer(db, salon_b, tg_id=None)
    dialogs.handle_start(db, salon_a, TG_ID, None, f"c_{foreign.id}")
    assert foreign.tg_id is None


def test_deep_link_does_not_steal_bound_customer(db, salon_a):
    customer = make_customer(db, salon_a, tg_id=999)
    dialogs.handle_start(db, salon_a, TG_ID, None, f"c_{customer.id}")
    assert customer.tg_id == 999


# ── Полный путь записи ────────────────────────────────────────────────────
def test_new_client_books_through_full_flow(db, salon_a):
    service, staff = _env(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    day = _local_day(salon_a, slot)

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, "m|book")
    assert f"s|{service.id}" in _callbacks(r)

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"s|{service.id}")
    assert f"st|{service.id}|{staff.id}" in _callbacks(r)
    assert f"st|{service.id}|0" in _callbacks(r)  # «любой мастер»

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"st|{service.id}|{staff.id}")
    assert any(cb.startswith(f"d|{service.id}|{staff.id}|") for cb in _callbacks(r))

    r = dialogs.handle_callback(
        db, salon_a, TG_ID, None, f"d|{service.id}|{staff.id}|{day.isoformat()}")
    slot_buttons = [cb for cb in _callbacks(r) if cb.startswith("t|")]
    assert slot_buttons, "в рабочий день должны быть свободные окна"

    # новый клиент: спрашиваем имя, потом телефон
    r = dialogs.handle_callback(db, salon_a, TG_ID, None, slot_buttons[0])
    assert "Как вас зовут" in r.text
    r = dialogs.handle_text(db, salon_a, TG_ID, None, "Пётр")
    assert r.request_contact is True
    r = dialogs.handle_text(db, salon_a, TG_ID, None, "+7 900 000-00-01")

    assert "Записал" in r.text
    assert r.admin_notify and "Новая запись" in r.admin_notify
    booking = db.scalars(select(Booking).where(Booking.salon_id == salon_a.id)).one()
    assert booking.status == "new" and booking.source == "bot"
    customer = db.get(Customer, booking.customer_id)
    assert customer.name == "Пётр"
    assert customer.phone == "+79000000001"  # нормализован
    assert customer.tg_id == TG_ID
    assert db.get(DialogState, (salon_a.id, "tg", TG_ID)) is None
    # подтверждение клиенту прошло через channels и попало в журнал
    confirm = db.scalars(select(MessageLog).where(
        MessageLog.booking_id == booking.id, MessageLog.kind == "confirm")).one()
    assert confirm.channel == "tg"


def test_known_client_books_without_extra_questions(db, salon_a):
    service, staff = _env(db, salon_a)
    make_customer(db, salon_a, tg_id=TG_ID)  # имя и телефон уже известны
    slot = next_working_slot(salon_a, duration_min=service.duration_min)

    r = dialogs.handle_callback(
        db, salon_a, TG_ID, None, f"t|{service.id}|{staff.id}|{_cb(slot)}")
    assert "Записал" in r.text
    assert db.get(DialogState, (salon_a.id, "tg", TG_ID)) is None
    assert db.scalars(select(Booking).where(Booking.salon_id == salon_a.id)).one().starts_at == slot


def test_unparsable_phone_asks_again_and_keeps_state(db, salon_a):
    service, staff = _env(db, salon_a)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    dialogs.handle_callback(db, salon_a, TG_ID, None, f"t|{service.id}|{staff.id}|{_cb(slot)}")
    dialogs.handle_text(db, salon_a, TG_ID, None, "Пётр")

    r = dialogs.handle_text(db, salon_a, TG_ID, None, "телефона не будет")
    assert "Не разобрал номер" in r.text
    state = db.get(DialogState, (salon_a.id, "tg", TG_ID))
    assert state is not None and state.step == "ask_phone"
    assert db.scalar(select(func.count(Booking.id))) == 0

    r = dialogs.handle_text(db, salon_a, TG_ID, None, "89000000001")
    assert "Записал" in r.text


def test_booking_without_services_is_graceful(db, salon_a):
    r = dialogs.handle_callback(db, salon_a, TG_ID, None, "m|book")
    assert "Пока нет доступных услуг" in r.text


def test_taken_slot_reported_instead_of_double_booking(db, salon_a):
    service, staff = _env(db, salon_a)
    first = make_customer(db, salon_a, tg_id=TG_ID)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    make_booking(db, salon_a, first, service, staff, starts_at=slot)

    make_customer(db, salon_a, name="Борис", tg_id=TG_ID + 1)
    r = dialogs.handle_callback(
        db, salon_a, TG_ID + 1, None, f"t|{service.id}|{staff.id}|{_cb(slot)}")
    assert "только что заняли" in r.text
    assert db.scalar(select(func.count(Booking.id)).where(
        Booking.salon_id == salon_a.id)) == 1


def test_busy_slot_is_not_offered(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    make_booking(db, salon_a, customer, service, staff, starts_at=slot)

    r = dialogs.handle_callback(
        db, salon_a, TG_ID, None,
        f"d|{service.id}|{staff.id}|{_local_day(salon_a, slot).isoformat()}")
    assert f"t|{service.id}|{staff.id}|{_cb(slot)}" not in _callbacks(r)


# ── Кнопки напоминания: Приду / Перенести / Отменить ──────────────────────
def test_confirm_button_sets_status(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    b = make_booking(db, salon_a, customer, service, staff, status="reminded_24h")

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"bk|confirm|{b.id}")
    assert b.status == "confirmed"
    assert "ждём вас" in r.text.lower()


def test_cancel_button_frees_the_slot_and_notifies_admin(db, salon_a):
    """Критерий AI-6: система освобождает слот заранее и сообщает админу."""
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    slot = next_working_slot(salon_a, duration_min=service.duration_min)
    b = make_booking(db, salon_a, customer, service, staff, starts_at=slot)
    day = _local_day(salon_a, slot)
    assert slot not in dialogs._slots_for(db, salon_a, service, staff.id, day)

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"bk|cancel|{b.id}")
    assert b.status == "cancelled"
    assert r.admin_notify and "слот освободился" in r.admin_notify
    assert slot in dialogs._slots_for(db, salon_a, service, staff.id, day)


def test_closed_booking_cannot_be_cancelled_again(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    b = make_booking(db, salon_a, customer, service, staff, status="cancelled")

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"bk|cancel|{b.id}")
    assert "уже нельзя отменить" in r.text
    assert r.admin_notify is None


def test_reschedule_moves_booking_and_links_it(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    b = make_booking(db, salon_a, customer, service, staff,
                     starts_at=next_working_slot(salon_a, duration_min=service.duration_min))

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"bk|resched|{b.id}")
    assert "На какой день" in r.text
    assert any(cb.startswith(f"rd|{b.id}|") for cb in _callbacks(r))

    new_slot = next_working_slot(salon_a, days_ahead=3, hour=15,
                                 duration_min=service.duration_min)
    r = dialogs.handle_callback(
        db, salon_a, TG_ID, None, f"rd|{b.id}|{_local_day(salon_a, new_slot).isoformat()}")
    assert any(cb.startswith(f"rt|{b.id}|") for cb in _callbacks(r))

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"rt|{b.id}|{_cb(new_slot)}")
    assert "Перенёс" in r.text
    assert r.admin_notify and "Перенос" in r.admin_notify
    assert b.status == "rescheduled" and b.rescheduled_to_id is not None
    new = db.get(Booking, b.rescheduled_to_id)
    assert new.starts_at == new_slot
    assert new.status == "new" and new.staff_id == staff.id


def test_reschedule_of_done_booking_refused(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    b = make_booking(db, salon_a, customer, service, staff, status="done")

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"bk|resched|{b.id}")
    assert "уже нельзя перенести" in r.text


def test_reschedule_onto_taken_slot_refused(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    mine = make_booking(db, salon_a, customer, service, staff,
                        starts_at=next_working_slot(salon_a, duration_min=service.duration_min))
    taken = next_working_slot(salon_a, days_ahead=3, hour=15,
                              duration_min=service.duration_min)
    make_booking(db, salon_a, make_customer(db, salon_a, name="Борис"),
                 service, staff, starts_at=taken)

    r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"rt|{mine.id}|{_cb(taken)}")
    assert "уже занято" in r.text
    assert mine.status == "new"


# ── Изоляция салонов на уровне бота ───────────────────────────────────────
def test_buttons_with_foreign_booking_id_are_dead(db, salon_a, salon_b):
    """Подделанный callback с чужим booking_id не должен ничего менять."""
    service_b, staff_b = _env(db, salon_b)
    customer_b = make_customer(db, salon_b, tg_id=TG_ID)
    foreign = make_booking(db, salon_b, customer_b, service_b, staff_b)

    for action in ("cancel", "confirm", "resched"):
        r = dialogs.handle_callback(db, salon_a, TG_ID, None, f"bk|{action}|{foreign.id}")
        assert "не найдена" in r.text
    assert foreign.status == "new"


# ── Прочие ветки меню ─────────────────────────────────────────────────────
def test_question_goes_to_admin(db, salon_a):
    make_customer(db, salon_a, name="Анна", tg_id=TG_ID)
    dialogs.handle_callback(db, salon_a, TG_ID, None, "m|ask")

    r = dialogs.handle_text(db, salon_a, TG_ID, None, "Во сколько вы закрываетесь?")
    assert r.admin_notify is not None
    assert "Во сколько вы закрываетесь?" in r.admin_notify
    assert "Анна" in r.admin_notify
    assert db.get(DialogState, (salon_a.id, "tg", TG_ID)) is None


def test_unsubscribe_sets_do_not_disturb(db, salon_a):
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    r = dialogs.handle_callback(db, salon_a, TG_ID, None, "m|unsub")
    assert customer.do_not_disturb is True
    # отписка от маркетинга, не от напоминаний о своих записях
    assert "Напоминания о ваших записях продолжат приходить" in r.text


def test_my_bookings_lists_only_upcoming_active(db, salon_a):
    service, staff = _env(db, salon_a)
    customer = make_customer(db, salon_a, tg_id=TG_ID)
    now = datetime.now(timezone.utc)
    upcoming = make_booking(db, salon_a, customer, service, staff,
                            starts_at=now + timedelta(days=2))
    make_booking(db, salon_a, customer, service, staff,
                 starts_at=now + timedelta(days=3), status="cancelled")
    make_booking(db, salon_a, customer, service, staff,
                 starts_at=now - timedelta(days=2), status="done")

    r = dialogs._my_bookings(db, salon_a, TG_ID)
    cancels = [cb for cb in _callbacks(r) if cb.startswith("bk|cancel|")]
    assert cancels == [f"bk|cancel|{upcoming.id}"]


def test_my_bookings_for_unknown_client(db, salon_a):
    r = dialogs._my_bookings(db, salon_a, TG_ID)
    assert "пока нет записей" in r.text.lower()


def test_broken_callback_falls_back_to_menu(db, salon_a):
    for data in ("", "мусор", "s|не-число", "bk|confirm|нет", "d|1|2|не-дата"):
        r = dialogs.handle_callback(db, salon_a, TG_ID, None, data)
        assert "Чем помочь?" in r.text


def test_text_without_dialog_state_returns_menu(db, salon_a):
    r = dialogs.handle_text(db, salon_a, TG_ID, None, "просто пишу боту")
    assert "Чем помочь?" in r.text
