"""Логика бота заявок: диалог и текст уведомления, без Telegram — чтобы тестировать.

Бот ничего не хранит: заявка живёт в памяти, пока человек отвечает на вопросы,
и сразу после последнего ответа уходит нам в личку.
"""
from dataclasses import dataclass, field
from html import escape

# Метка в ссылке t.me/<бот>?start=<метка>: откуда пришёл человек и какой тариф смотрел.
# По ней сравниваем две цены без счётчика на сайте.
SOURCES: dict[str, tuple[str, str | None]] = {
    "landing": ("лендинг", None),
    "tier_4900": ("лендинг, тариф «Старт» 4 900 ₽", None),
    "tier_9900": ("лендинг, тариф «Полный» 9 900 ₽", None),
    "avito_tmn": ("Avito", "Тюмень"),
    "avito_kzn": ("Avito", "Казань"),
}
CITIES = ("Тюмень", "Казань")
WRITE_HERE = "Пишите сюда, в Telegram"
MAX_LEN = 100

GREETING = ("Здравствуйте! Это ReBook — ИИ-администратор для салонов красоты.\n"
            "Оставьте заявку, и мы напишем вам в течение дня. Как вас зовут?")
ASK_SALON = "Как называется ваш салон?"


@dataclass
class Lead:
    source: str
    city: str | None = None
    name: str | None = None
    salon: str | None = None
    contact: str | None = None


@dataclass
class Reply:
    text: str
    buttons: list[str] = field(default_factory=list)
    ask_phone: bool = False  # показать кнопку «поделиться номером»
    done: bool = False


def source_label(payload: str | None) -> tuple[str, str | None]:
    if not payload:
        return "без метки", None
    return SOURCES.get(payload, (f"метка «{payload[:32]}»", None))


def start(payload: str | None) -> tuple[Lead, Reply]:
    label, city = source_label(payload)
    return Lead(source=label, city=city), Reply(GREETING)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())[:MAX_LEN]


def _ask_city() -> Reply:
    return Reply("В каком городе салон?", buttons=list(CITIES))


def _ask_contact() -> Reply:
    return Reply("Как с вами связаться? Поделитесь номером кнопкой ниже, напишите "
                 f"удобный контакт или выберите «{WRITE_HERE}».",
                 buttons=[WRITE_HERE], ask_phone=True)


def answer(lead: Lead, text: str | None = None, phone: str | None = None) -> Reply:
    """Следующий шаг диалога; заполняет lead на месте."""
    value = _clean(text)
    if lead.name is None:
        if not value:
            return Reply("Как вас зовут?")
        lead.name = value
        return Reply(ASK_SALON)
    if lead.salon is None:
        if not value:
            return Reply(ASK_SALON)
        lead.salon = value
        return _ask_city() if lead.city is None else _ask_contact()
    if lead.city is None:
        if not value:
            return _ask_city()
        lead.city = value
        return _ask_contact()
    if lead.contact is None:
        contact = _clean(phone) or value
        if not contact:
            return _ask_contact()
        lead.contact = "Telegram" if contact == WRITE_HERE else contact
        return Reply("Спасибо! Напишем вам в течение дня.", done=True)
    return Reply("Заявка уже у нас — скоро напишем.", done=True)


def notify_html(lead: Lead, user_id: int, username: str | None) -> str:
    """Уведомление нам в личку. Всё, что ввёл человек, экранируем: parse_mode=HTML."""
    tg = f"@{escape(username)}" if username else f'<a href="tg://user?id={int(user_id)}">открыть чат</a>'
    rows = (("Имя", lead.name), ("Салон", lead.salon), ("Город", lead.city),
            ("Контакт", lead.contact))
    body = "\n".join(f"{k}: {escape(v or '—')}" for k, v in rows)
    return f"🆕 <b>Заявка</b>\n{body}\nTelegram: {tg}\nОткуда: {escape(lead.source)}"
