"""Живой прогон разбора фраз на настоящей LLM: 20 формулировок «как пишут клиенты».

Без ключа пропускается. Запуск:
    LLM_API_KEY=... ./.venv/bin/python -m pytest tests/test_assistant_live.py -v
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.bots import assistant
from app.config import settings
from tests.conftest import make_salon, make_service, make_staff

pytestmark = pytest.mark.skipif(not settings.llm_api_key, reason="LLM_API_KEY не задан")

WD = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}

# (фраза, ожидание). day: +N — через N дней, «чт» — ближайший четверг, None — не назван.
# time: (from, to) — None-поля не проверяются, «-» — должно быть пусто.
PHRASES = [
    ("Запишите к Лене в четверг после 6 на маникюр",
     dict(intent="book", service="Маникюр с покрытием", staff="Елена", day="чт", time=("18:00", "-"))),
    # «подстричься» подходит и к женской, и к мужской — модель не угадывает, бот переспросит
    ("хочу подстричься завтра в 3",
     dict(intent="book", service=None, mentioned=None, day=1, time=("15:00", "15:00"))),
    ("Маша свободна в субботу утром? на окрашивание",
     dict(intent="book", service="Окрашивание", staff="Мария", day="сб")),
    ("мужская стрижка сегодня вечером, к любому мастеру",
     dict(intent="book", service="Мужская стрижка", staff=0, day=0)),
    ("можно на ноготочки к Вике послезавтра в 12:30",
     dict(intent="book", service="Маникюр с покрытием", staff="Виктория", day=2, time=("12:30", "12:30"))),
    ("здравствуйте! хочу покраситься", dict(intent="book", service="Окрашивание", day=None, time=("-", "-"))),
    ("а на пятницу до обеда есть что-нибудь на стрижку жен",
     dict(intent="book", service="Женская стрижка", day="пт")),
    ("запишите мужа на стрижку во вторник в 19", dict(intent="book", service="Мужская стрижка", day="вт", time=("19:00", "19:00"))),
    ("к Лене можно?", dict(intent="book", staff="Елена", day=None)),
    ("хочу на педикюр в среду", dict(intent="book", service=None, mentioned="педикюр", day="ср")),
    ("не смогу прийти завтра, отмените", dict(intent="cancel")),
    ("отмена записи", dict(intent="cancel")),
    ("можно перенести мою запись на субботу после 12?",
     dict(intent="reschedule", day="сб", time=("12:00", "-"))),
    ("опаздываю, давайте перенесём на пятницу", dict(intent="reschedule", day="пт")),
    ("сколько стоит маникюр?", dict(intent="question", answer=True)),
    ("где вы находитесь", dict(intent="question", answer=True)),
    ("до скольки работаете в субботу?", dict(intent="question", answer=True)),
    ("можно картой оплатить?", dict(intent="question", answer=True)),
    ("у вас есть скидки для студентов?", dict(intent="question", answer=False)),
    ("спасибо!", dict(intent="other")),
]


@pytest.fixture
def salon(db):
    s = make_salon(db, "Салон «Анна»", feature_flags={"llm_assistant": True})
    s.texts = {**s.texts, "faq": "Адрес: Москва, ул. Садовая, 12. Оплата: наличные, карта, СБП."}
    for name, price, dur in (("Женская стрижка", 2500, 60), ("Мужская стрижка", 1500, 45),
                             ("Маникюр с покрытием", 2200, 90), ("Окрашивание", 5000, 120)):
        make_service(db, s, name, duration_min=dur, price=price)
    for name in ("Мария", "Елена", "Виктория"):
        make_staff(db, s, name)
    return s


@pytest.mark.parametrize("phrase,exp", PHRASES, ids=[p for p, _ in PHRASES])
def test_phrase(db, salon, phrase, exp):
    from app.models import Service, Staff
    d = assistant.parse(db, salon, assistant.scrub(phrase).text)
    assert d.intent == exp["intent"], d
    if "service" in exp:
        got = db.get(Service, d.service_id).name if d.service_id else None
        assert got == exp["service"], d
    if "mentioned" in exp:
        got = (d.service_mentioned or "").lower() or None
        assert (got is None) == (exp["mentioned"] is None), d
        if got:
            assert exp["mentioned"] in got, d
    if "staff" in exp:
        got = 0 if d.staff_id == 0 else db.get(Staff, d.staff_id).name if d.staff_id else None
        assert got == exp["staff"], d
    if "day" in exp:
        today = datetime.now(ZoneInfo(salon.timezone)).date()
        want = exp["day"]
        if want is None:
            assert d.date is None, d
        elif isinstance(want, int):
            assert d.date == (today + timedelta(days=want)).isoformat(), d
        else:
            got = datetime.fromisoformat(d.date).date()
            assert got.weekday() == WD[want] and 0 <= (got - today).days <= 7, d
    if "time" in exp:
        for want, got in zip(exp["time"], (d.time_from, d.time_to)):
            if want == "-":
                assert got is None, d
            elif want is not None:
                assert got == want, d
    if "answer" in exp:
        assert bool(d.answer) == exp["answer"], d
