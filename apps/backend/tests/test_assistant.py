"""ИИ-ассистент бота: разбор фразы подменён фейком, проверяется всё вокруг LLM —
досборка записи из уточнений, слоты, перенос/отмена, ответы и защита ПДн."""
import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app import llm
from app.bots import assistant, dialogs
from app.config import settings
from app.models import Booking, Customer, DialogState

from tests.conftest import make_booking, make_customer, make_salon, make_service, make_staff

TZ = ZoneInfo("Europe/Moscow")
TG = 555_000_111


def _next_weekday(wd: int, min_ahead: int = 2):
    d = datetime.now(TZ).date() + timedelta(days=min_ahead)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


DAY = _next_weekday(2)  # среда: салон работает 10–20


def _at(hh: int, mm: int = 0, day=DAY) -> datetime:
    return datetime.combine(day, time(hh, mm), TZ).astimezone(timezone.utc)


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[list[dict]] = []

    def __call__(self, messages):
        self.calls.append(messages)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return json.dumps(a, ensure_ascii=False)

    def sent_text(self) -> str:
        return json.dumps(self.calls, ensure_ascii=False)


@pytest.fixture
def salon(db, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    s = make_salon(db, "Салон ИИ", feature_flags={"llm_assistant": True})
    s.texts = {**s.texts, "faq": "Адрес: ул. Садовая, 12."}
    return s


@pytest.fixture
def cat(db, salon):
    return {
        "cut": make_service(db, salon, "Женская стрижка", duration_min=60),
        "nails": make_service(db, salon, "Маникюр", duration_min=90),
        "lena": make_staff(db, salon, "Елена"),
        "masha": make_staff(db, salon, "Мария"),
    }


def _fake(monkeypatch, *answers) -> FakeLLM:
    fake = FakeLLM(*answers)
    monkeypatch.setattr(llm, "complete", fake)
    return fake


def _say(db, salon, text, name_hint="Аня"):
    reply = dialogs.handle_text(db, salon, TG, name_hint, text)
    db.flush()
    return reply


def _book(**kw):
    return {"intent": "book", **kw}


def _bookings(db, salon):
    return db.scalars(select(Booking).where(Booking.salon_id == salon.id)).all()


def _state(db, salon):
    return db.get(DialogState, (salon.id, "tg", TG))


# ── Запись одной фразой ───────────────────────────────────────────────────
def test_known_customer_books_in_one_phrase(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch, _book(service_id=cat["nails"].id, staff_id=cat["lena"].id,
                             date=DAY.isoformat(), time_from="18:00"))
    reply = _say(db, salon, "к Лене на маникюр в среду после 6")
    [b] = _bookings(db, salon)
    assert b.starts_at == _at(18) and b.staff_id == cat["lena"].id
    assert b.service_id == cat["nails"].id and b.source == "bot"
    assert "Записал" in reply.text and reply.admin_notify
    assert _state(db, salon) is None


def test_window_skips_busy_slot(db, salon, cat, monkeypatch):
    other = make_customer(db, salon, "Ольга")
    make_booking(db, salon, other, cat["cut"], cat["lena"], starts_at=_at(18))
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch, _book(service_id=cat["cut"].id, staff_id=cat["lena"].id,
                             date=DAY.isoformat(), time_from="18:00"))
    _say(db, salon, "стрижка к Лене в среду после шести")
    mine = [b for b in _bookings(db, salon) if b.customer.tg_id == TG]
    assert [b.starts_at for b in mine] == [_at(19)]


def test_new_customer_phone_and_name_in_phrase_stay_local(db, salon, cat, monkeypatch):
    fake = _fake(monkeypatch, _book(service_id=cat["cut"].id, staff_id=0,
                                    date=DAY.isoformat(), time_from="12:00", time_to="12:00"))
    reply = _say(db, salon, "Здравствуйте, меня зовут Ксения, запишите на стрижку в среду "
                            "в 12, мой номер 8 (900) 123-45-67", name_hint="TgNick")
    [b] = _bookings(db, salon)
    assert b.starts_at == _at(12) and b.staff_id is None
    cust = db.get(Customer, b.customer_id)
    assert (cust.phone, cust.name, cust.tg_id) == ("+79001234567", "Ксения", TG)
    assert "Записал" in reply.text
    sent = fake.sent_text()
    for secret in ("Ксения", "123-45-67", "900", "TgNick"):
        assert secret not in sent


def test_new_customer_without_phone_is_asked_for_it(db, salon, cat, monkeypatch):
    _fake(monkeypatch, _book(service_id=cat["cut"].id, date=DAY.isoformat(),
                             time_from="11:00", time_to="11:00"))
    reply = _say(db, salon, "стрижку в среду в 11")
    assert reply.request_contact and "11:00" in reply.text
    assert _state(db, salon).step == "ask_phone" and not _bookings(db, salon)
    reply = _say(db, salon, "+7 900 555-44-33")
    [b] = _bookings(db, salon)
    assert b.starts_at == _at(11) and db.get(Customer, b.customer_id).name == "Аня"


# ── Уточнения ─────────────────────────────────────────────────────────────
def test_missing_day_is_asked_and_answer_merged(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    fake = _fake(monkeypatch,
                 _book(service_id=cat["cut"].id, staff_id=cat["masha"].id),
                 {"intent": "other", "date": DAY.isoformat(), "time_from": "15:00",
                  "time_to": "15:00"})
    reply = _say(db, salon, "хочу подстричься у Маши")
    assert "какой день" in reply.text and reply.buttons  # кнопки — запасной путь
    assert _state(db, salon).step == "ai_book"
    reply = _say(db, salon, "в среду в 3")
    [b] = _bookings(db, salon)
    assert (b.starts_at, b.staff_id, b.service_id) == (_at(15), cat["masha"].id, cat["cut"].id)
    assert "уже известно" in fake.sent_text().lower()


def test_missing_service_is_asked(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch,
          _book(date=DAY.isoformat(), time_from="10:00", time_to="10:00"),
          _book(service_id=cat["nails"].id))
    reply = _say(db, salon, "запишите меня на среду в 10")
    assert "услугу" in reply.text and not _bookings(db, salon)
    _say(db, salon, "на ноготочки")
    [b] = _bookings(db, salon)
    assert (b.service_id, b.starts_at) == (cat["nails"].id, _at(10))


def test_busy_exact_time_offers_alternatives(db, salon, cat, monkeypatch):
    other = make_customer(db, salon, "Ольга")
    make_booking(db, salon, other, cat["cut"], cat["lena"], starts_at=_at(14))
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch,
          _book(service_id=cat["cut"].id, staff_id=cat["lena"].id, date=DAY.isoformat(),
                time_from="14:00", time_to="14:00"),
          {"intent": "other", "time_from": "16:00", "time_to": "16:00"})
    reply = _say(db, salon, "к Лене на стрижку в среду в 14")
    assert "свободного нет" in reply.text and len(_bookings(db, salon)) == 1
    assert any(label == "16:00" for row in reply.buttons for label, _ in row)
    _say(db, salon, "давайте в 16")
    mine = [b for b in _bookings(db, salon) if b.customer.tg_id == TG]
    assert [b.starts_at for b in mine] == [_at(16)]


def test_unknown_master_and_invalid_ids_are_not_trusted(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch, _book(service_id=cat["cut"].id, staff_id=None, staff_mentioned="Света",
                             date=DAY.isoformat(), time_from="12:00"),
          _book(service_id=999_999, staff_id=888_888, date="1999-01-01"))
    reply = _say(db, salon, "к Свете на стрижку в среду")
    assert "мастера" in reply.text and "Елена" in reply.text and not _bookings(db, salon)
    dialogs._clear_state(db, salon, TG)
    reply = _say(db, salon, "что-то странное")
    assert "услугу" in reply.text and not _bookings(db, salon)


# ── Перенос и отмена ──────────────────────────────────────────────────────
def test_cancel_confirmed_by_text(db, salon, cat, monkeypatch):
    me = make_customer(db, salon, "Анна", tg_id=TG)
    b = make_booking(db, salon, me, cat["cut"], cat["lena"], starts_at=_at(12))
    fake = _fake(monkeypatch, {"intent": "cancel"})
    reply = _say(db, salon, "не смогу прийти, отмените пожалуйста")
    assert "Отменить запись" in reply.text and b.status == "new"
    reply = _say(db, salon, "да")
    assert b.status == "cancelled" and reply.admin_notify
    assert len(fake.calls) == 1  # «да» разбирается локально


def test_reschedule_to_new_time(db, salon, cat, monkeypatch):
    me = make_customer(db, salon, "Анна", tg_id=TG)
    b = make_booking(db, salon, me, cat["cut"], cat["lena"], starts_at=_at(12))
    _fake(monkeypatch, {"intent": "reschedule", "date": DAY.isoformat(),
                        "time_from": "17:00"})
    reply = _say(db, salon, "можно перенести на вечер, после 5?")
    assert b.status == "rescheduled" and "Перенёс" in reply.text
    new = db.get(Booking, b.rescheduled_to_id)
    assert new.starts_at == _at(17) and new.staff_id == cat["lena"].id


def test_reschedule_without_bookings(db, salon, cat, monkeypatch):
    _fake(monkeypatch, {"intent": "reschedule"})
    assert "предстоящих записей" in _say(db, salon, "перенесите запись").text


# ── Вопросы ───────────────────────────────────────────────────────────────
def test_question_answered_from_salon_data(db, salon, cat, monkeypatch):
    fake = _fake(monkeypatch, {"intent": "question", "answer": "Мы на ул. Садовой, 12."})
    reply = _say(db, salon, "а где вы находитесь?")
    assert reply.text == "Мы на ул. Садовой, 12." and reply.admin_notify is None
    prompt = fake.calls[0][0]["content"]
    assert "Садовая, 12" in prompt and "Маникюр" in prompt and "Елена" in prompt


def test_unanswerable_question_goes_to_admin(db, salon, cat, monkeypatch):
    _fake(monkeypatch, {"intent": "question", "answer": None})
    reply = _say(db, salon, "а у вас можно с собакой?")
    assert "администратор" in reply.text and "с собакой" in reply.admin_notify


# ── Отказоустойчивость ────────────────────────────────────────────────────
def test_truncated_answer_is_retried_once(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    fake = _fake(monkeypatch, llm.LLMError("обрыв"),
                 _book(service_id=cat["cut"].id, date=DAY.isoformat(),
                       time_from="12:00", time_to="12:00"))
    assert "Записал" in _say(db, salon, "стрижка в среду в 12").text
    assert len(fake.calls) == 2


def test_llm_failure_falls_back_to_buttons(db, salon, cat, monkeypatch):
    _fake(monkeypatch, llm.LLMError("timeout"), llm.LLMError("timeout"))
    reply = _say(db, salon, "запишите на стрижку")
    assert reply.buttons and "Чем помочь" in reply.text and _state(db, salon) is None


def test_disabled_flag_never_calls_llm(db, salon, cat, monkeypatch):
    salon.feature_flags = {"llm_assistant": False}
    fake = _fake(monkeypatch)
    reply = _say(db, salon, "запишите на стрижку")
    assert fake.calls == [] and "Можно просто написать" not in reply.text


def test_no_api_key_never_calls_llm(db, salon, cat, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    fake = _fake(monkeypatch)
    _say(db, salon, "запишите на стрижку")
    assert fake.calls == []


def test_button_press_drops_ai_draft(db, salon, cat, monkeypatch):
    _fake(monkeypatch, _book(service_id=cat["cut"].id))
    _say(db, salon, "на стрижку")
    assert _state(db, salon).step == "ai_book"
    dialogs.handle_callback(db, salon, TG, "Аня", "m|my")
    db.flush()
    assert _state(db, salon) is None


def test_service_button_keeps_day_and_time_from_phrase(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    fake = _fake(monkeypatch, _book(date=DAY.isoformat(), time_from="18:00"))
    reply = _say(db, salon, "хочу записаться в среду после 6")
    assert "услугу" in reply.text
    reply = dialogs.handle_callback(db, salon, TG, "Аня", f"s|{cat['cut'].id}")
    db.flush()
    [b] = _bookings(db, salon)
    assert (b.service_id, b.starts_at) == (cat["cut"].id, _at(18))
    assert "Записал" in reply.text and len(fake.calls) == 1


def test_day_button_keeps_time_window(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch, _book(service_id=cat["cut"].id, staff_id=cat["lena"].id,
                             time_from="18:00"))
    reply = _say(db, salon, "к Лене на стрижку после 6")
    assert "какой день" in reply.text
    dialogs.handle_callback(db, salon, TG, "Аня",
                            f"d|{cat['cut'].id}|{cat['lena'].id}|{DAY.isoformat()}")
    db.flush()
    [b] = _bookings(db, salon)
    assert (b.staff_id, b.starts_at) == (cat["lena"].id, _at(18))


def test_forged_button_id_does_not_reach_draft(db, salon, cat, monkeypatch):
    other = make_salon(db, "Чужой")
    foreign = make_service(db, other, "Чужая услуга")
    _fake(monkeypatch, _book(date=DAY.isoformat(), time_from="18:00"))
    _say(db, salon, "в среду после 6")
    dialogs.handle_callback(db, salon, TG, "Аня", f"s|{foreign.id}")
    db.flush()
    assert not _bookings(db, salon) and _state(db, salon) is None


# ── ПДн ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,phone,name", [
    ("мой номер +7 900 123-45-67", "+79001234567", None),
    ("89001234567 перезвоните", "+79001234567", None),
    ("меня зовут катя, почта kate@mail.ru", None, "Катя"),
    ("к Лене в четверг после 6", None, None),
    ("в 18:30, 2 человека", None, None),
])
def test_scrub(text, phone, name):
    s = assistant.scrub(text)
    assert (s.phone, s.name) == (phone, name)
    assert "123-45-67" not in s.text and "kate@" not in s.text
    if name:
        assert name.lower() not in s.text.lower()


def test_parse_json_tolerates_code_fence():
    assert llm.parse_json('```json\n{"intent": "book"}\n```') == {"intent": "book"}
    with pytest.raises(llm.LLMError):
        llm.parse_json("не знаю")


def test_draft_survives_second_clarification(db, salon, cat, monkeypatch):
    make_customer(db, salon, "Анна", tg_id=TG)
    _fake(monkeypatch, _book(staff_id=cat["lena"].id), {"intent": "other"},
          _book(service_id=cat["cut"].id, date=DAY.isoformat(), time_from="13:00",
                time_to="13:00"))
    _say(db, salon, "к Лене хочу")
    reply = _say(db, salon, "ммм")
    assert "услугу" in reply.text and _state(db, salon).step == "ai_book"
    _say(db, salon, "стрижка в среду в час")
    [b] = _bookings(db, salon)
    assert (b.staff_id, b.starts_at) == (cat["lena"].id, _at(13))
