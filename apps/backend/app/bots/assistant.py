"""ИИ-ассистент бота: запись, перенос, отмена и вопросы свободным текстом.

LLM только разбирает фразу в намерение и поля («к Лене в четверг после 6» →
book, мастер, дата, окно времени). Всё остальное детерминированно: слоты
считает services/slots.py, записи создаёт тот же код, что и у кнопок
(dialogs.py). Кнопки остаются запасным путём на каждом шаге.

ПДн в LLM не уходят: телефон, email и представление клиента («меня зовут …»)
вырезаются из текста до отправки и разбираются локально; имя клиента из
профиля и Telegram в промпт не попадают. В промпт идут только данные салона.
"""
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import channels, llm
from app.bots import dialogs
from app.bots.dialogs import Reply
from app.models import Booking, Salon, Service, Staff
from app.services import bookings as svc
from app.services.customers import normalize_phone, upsert_customer
from app.services.slots import DAY_KEYS

log = logging.getLogger("rebook.assistant")

FLAG = "llm_assistant"
INTENTS = ("book", "reschedule", "cancel", "question", "other")
HORIZON_DAYS = 60
WEEKDAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
YES = re.compile(r"^\s*(да|ага|угу|конечно|верно|отменя\w*|подтверждаю|yes|ок|окей)\b",
                 re.IGNORECASE)


def active(salon: Salon) -> bool:
    return llm.enabled() and bool((salon.feature_flags or {}).get(FLAG))


# ── ПДн: вырезаем до LLM, разбираем локально ─────────────────────────────
PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NAME_RE = re.compile(r"\b(?:меня зовут|зовут меня|моё имя|мое имя)\s+([А-ЯЁA-Z][а-яёa-z]+)",
                     re.IGNORECASE)


@dataclass
class Scrubbed:
    text: str              # безопасно отдавать в LLM
    phone: str | None      # E.164, если был в тексте
    name: str | None


def scrub(text: str) -> Scrubbed:
    phone = None

    def _phone(m: re.Match) -> str:
        nonlocal phone
        normalized = normalize_phone(m.group(0).strip())
        if normalized is None:
            return m.group(0)
        phone = phone or normalized
        return "[телефон]"

    out = PHONE_RE.sub(_phone, text)
    out = EMAIL_RE.sub("[email]", out)
    name = None
    if (m := NAME_RE.search(out)):
        name = m.group(1).capitalize()
        out = out[:m.start(1)] + "[имя]" + out[m.end(1):]
    return Scrubbed(out, phone, name)


# ── Разбор фразы LLM ──────────────────────────────────────────────────────
@dataclass
class Draft:
    """Что известно о желании клиента. Живёт в dialog_state между репликами."""
    intent: str = "other"
    service_id: int | None = None
    staff_id: int | None = None      # 0 — клиенту всё равно
    date: str | None = None          # YYYY-MM-DD, локальная дата салона
    time_from: str | None = None     # HH:MM
    time_to: str | None = None       # HH:MM; равен time_from — точное время
    answer: str | None = None
    service_mentioned: str | None = None
    staff_mentioned: str | None = None

    def merged(self, new: "Draft") -> "Draft":
        """Уточнение дополняет черновик: новые непустые поля перекрывают старые."""
        out = Draft(**asdict(self))
        for k, v in asdict(new).items():
            if v is not None and k != "intent":
                setattr(out, k, v)
        # «а лучше к Ольге» после отказа — прошлый «неизвестный мастер» больше не актуален
        if new.staff_id is not None:
            out.staff_mentioned = new.staff_mentioned
        if new.service_id is not None:
            out.service_mentioned = new.service_mentioned
        if new.time_from and not new.time_to:
            out.time_to = None
        return out


def _hours_text(hours: dict) -> str:
    names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    parts = []
    for key, name in zip(DAY_KEYS, names):
        entry = (hours or {}).get(key)
        if not entry:
            parts.append(f"{name}: выходной")
            continue
        ranges = [entry] if isinstance(entry[0], str) else entry
        parts.append(f"{name}: " + ", ".join(f"{a}–{b}" for a, b in ranges))
    return "; ".join(parts)


def _system_prompt(salon: Salon, services: list[Service], staff: list[Staff]) -> str:
    tz = ZoneInfo(salon.timezone)
    now = datetime.now(tz)
    days = []
    for i in range(14):
        d = now.date() + timedelta(days=i)
        label = " (сегодня)" if i == 0 else " (завтра)" if i == 1 else ""
        days.append(f"{d.isoformat()} — {WEEKDAYS_FULL[d.weekday()]}{label}")
    svc_lines = "\n".join(f"- id={s.id}: {s.name}, {int(s.price)} ₽, {s.duration_min} мин"
                          for s in services)
    staff_lines = "\n".join(f"- id={s.id}: {s.name}" for s in staff) or "- (не указаны)"
    faq = (salon.texts or {}).get("faq", "").strip() or "(не заполнено)"
    return f"""Ты — администратор в чат-боте записи. Салон: {salon.name}. Клиенты пишут как в мессенджере: коротко, с опечатками, уменьшительными именами.
Разбери последнее сообщение клиента и верни ТОЛЬКО JSON-объект:
{{"intent": "book|reschedule|cancel|question|other",
 "service_id": число|null, "service_mentioned": строка|null,
 "staff_id": число|null, "staff_mentioned": строка|null,
 "date": "YYYY-MM-DD"|null, "time_from": "HH:MM"|null, "time_to": "HH:MM"|null,
 "answer": строка|null}}

Правила:
- intent: book — хочет записаться; reschedule — перенести существующую запись; cancel — отменить запись; question — вопрос о салоне (цены, адрес, часы, услуги, правила); other — приветствие, благодарность и прочее.
- service_id — только id из списка услуг. Если клиент назвал услугу, которой нет в списке, service_id=null, а её название — в service_mentioned.
- staff_id — только id из списка мастеров; уменьшительные имена сопоставляй с полными (Лена → Елена, Маша → Мария, Вика → Виктория, Оля → Ольга). «Любой мастер», «всё равно к кому» → staff_id=0. Если назван мастер, которого нет в списке, staff_id=null, а имя — в staff_mentioned. Не назвал мастера — staff_id=null.
- date — дата из календаря ниже. «В четверг» — ближайший четверг начиная с сегодняшнего дня. Для reschedule — новая желаемая дата.
- Время — в часах работы салона: «после 6» / «после шести» при работе до 20:00 значит 18:00, «в 3» — 15:00. «После X» → time_from=X, time_to=null. «До X» → time_to=X. «Утром» → 10:00–12:00, «днём» → 12:00–17:00, «вечером» → 17:00–время закрытия. Точное время «в 15:30» → time_from=time_to="15:30". Не сказал про время — оба null.
- answer — только для intent=question: короткий дружелюбный ответ по данным салона ниже. Если ответа в данных нет — answer=null, не выдумывай.
- Поля, о которых клиент не говорил, — null. Метки [телефон], [имя], [email] — скрытые данные клиента, игнорируй их.

Услуги:
{svc_lines}

Мастера:
{staff_lines}

Часы работы: {_hours_text(salon.work_hours)}

О салоне:
{faq}

Календарь:
{chr(10).join(days)}"""


def _valid_time(v) -> str | None:
    if not isinstance(v, str) or not re.fullmatch(r"\d{1,2}:\d{2}", v.strip()):
        return None
    h, m = map(int, v.strip().split(":"))
    return f"{h:02d}:{m:02d}" if h < 24 and m < 60 else None


def _to_draft(data: dict, salon: Salon, services: list[Service],
              staff: list[Staff]) -> Draft:
    """Валидация ответа модели: всё, чего нет в данных салона, отбрасываем."""
    def _int(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _str(v):
        return v.strip()[:500] if isinstance(v, str) and v.strip() else None

    intent = data.get("intent") if data.get("intent") in INTENTS else "other"
    service_id = _int(data.get("service_id"))
    if service_id not in {s.id for s in services}:
        service_id = None
    staff_id = _int(data.get("staff_id"))
    if staff_id not in {s.id for s in staff} | {0}:
        staff_id = None
    day = None
    if isinstance(data.get("date"), str):
        try:
            d = date.fromisoformat(data["date"])
            today = datetime.now(ZoneInfo(salon.timezone)).date()
            if today <= d <= today + timedelta(days=HORIZON_DAYS):
                day = d.isoformat()
        except ValueError:
            pass
    return Draft(
        intent=intent, service_id=service_id, staff_id=staff_id, date=day,
        time_from=_valid_time(data.get("time_from")), time_to=_valid_time(data.get("time_to")),
        answer=_str(data.get("answer")) if intent == "question" else None,
        service_mentioned=_str(data.get("service_mentioned")) if service_id is None else None,
        staff_mentioned=_str(data.get("staff_mentioned")) if staff_id is None else None,
    )


def _catalog(db: Session, salon: Salon) -> tuple[list[Service], list[Staff]]:
    services = db.scalars(select(Service).where(
        Service.salon_id == salon.id, Service.is_active.is_(True)).order_by(Service.id)).all()
    staff = db.scalars(select(Staff).where(
        Staff.salon_id == salon.id, Staff.is_active.is_(True)).order_by(Staff.id)).all()
    return list(services), list(staff)


def parse(db: Session, salon: Salon, safe_text: str, context: str | None = None) -> Draft:
    """Фраза (уже без ПДн) → Draft. Бросает llm.LLMError."""
    services, staff = _catalog(db, salon)
    messages = [{"role": "system", "content": _system_prompt(salon, services, staff)}]
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": safe_text})
    return _to_draft(llm.parse_json(llm.complete(messages)), salon, services, staff)


# ── Вход из dialogs.handle_text ───────────────────────────────────────────
def handle(db: Session, salon: Salon, ext_id: int, name_hint: str | None,
           text: str, state_step: str | None, payload: dict | None) -> Reply:
    s = scrub(text)
    payload = payload or {}
    if state_step == "ai_cancel" and YES.match(s.text):
        dialogs._clear_state(db, salon, ext_id)
        return dialogs._reminder_action(db, salon, ext_id, "cancel", payload["booking_id"])

    prev = Draft(**payload["draft"]) if state_step == "ai_book" else None
    context = None
    if prev is not None:
        known = {k: v for k, v in asdict(prev).items() if v is not None and k != "answer"}
        context = (f"Клиент в процессе записи, бот задал уточняющий вопрос: "
                   f"«{payload.get('asked', '')}». Уже известно: {known}. "
                   "Короткий ответ клиента («в пятницу», «к Ольге», «давай в 4») — "
                   "это уточнение той же записи, intent=book.")
    try:
        draft = parse(db, salon, s.text, context)
    except llm.LLMError:
        dialogs._clear_state(db, salon, ext_id)
        return dialogs.main_menu(salon, greeting=False)

    if prev is not None and draft.intent in ("book", "other"):
        draft = prev.merged(draft)
        draft.intent = "book"
    dialogs._clear_state(db, salon, ext_id)

    if draft.intent == "book":
        return _book(db, salon, ext_id, name_hint, draft, s)
    if draft.intent in ("reschedule", "cancel"):
        return _change(db, salon, ext_id, draft)
    if draft.intent == "question":
        if draft.answer:
            return Reply(draft.answer, buttons=[[("📅 Записаться", "m|book")],
                                                [("← Меню", "m|menu")]])
        who = _who(db, salon, ext_id, name_hint)
        return Reply("Уточню у администратора — вам ответят в ближайшее время 🙌",
                     buttons=[[("← Меню", "m|menu")]],
                     admin_notify=f"❓ Вопрос от {who}:\n{text}")
    return dialogs.main_menu(salon, greeting=False)


def _who(db: Session, salon: Salon, ext_id: int, name_hint: str | None) -> str:
    customer = dialogs._customer(db, salon, ext_id)
    return customer.name if customer and customer.name else (name_hint or "клиент")


# ── Запись ────────────────────────────────────────────────────────────────
def _ask(db: Session, salon: Salon, ext_id: int, draft: Draft, question: str,
         buttons: list[list[tuple[str, str]]] | None = None) -> Reply:
    """Уточняющий вопрос: черновик ждёт ответа текстом, кнопки — запасной путь."""
    dialogs._set_state(db, salon, ext_id, "ai_book",
                       {"draft": asdict(draft), "asked": question})
    return Reply(question, buttons=(buttons or []) + [[("← Меню", "m|menu")]])


def _local(salon: Salon, dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo(salon.timezone))


def _day_label(salon: Salon, day: date) -> str:
    today = datetime.now(ZoneInfo(salon.timezone)).date()
    if day == today:
        return "сегодня"
    if day == today + timedelta(days=1):
        return "завтра"
    return f"{WEEKDAYS_FULL[day.weekday()]}, {day.day} {channels.RU_MONTHS[day.month - 1]}"


def _when(salon: Salon, dt: datetime) -> str:
    local = _local(salon, dt)
    return f"{_day_label(salon, local.date())} в {local.strftime('%H:%M')}"


def _in_window(salon: Salon, slot: datetime, draft: Draft) -> bool:
    t = _local(salon, slot).time()
    if draft.time_from and t < time.fromisoformat(draft.time_from):
        return False
    if draft.time_to:
        end = time.fromisoformat(draft.time_to)
        # точное время или «до X»: начало не позже X
        if t > end:
            return False
    return True


def _window_text(draft: Draft) -> str:
    if draft.time_from and draft.time_from == draft.time_to:
        return f"в {draft.time_from}"
    if draft.time_from and draft.time_to:
        return f"с {draft.time_from} до {draft.time_to}"
    if draft.time_from:
        return f"после {draft.time_from}"
    return f"до {draft.time_to}"


def _slot_buttons(salon: Salon, service_id: int, staff_id: int, slots: list[datetime],
                  near: str | None = None) -> list[list[tuple[str, str]]]:
    if near:  # окна рядом с тем, что просил клиент, а не первые с утра
        target = time.fromisoformat(near)
        minutes = lambda x: abs((_local(salon, x).hour * 60 + _local(salon, x).minute)
                                - (target.hour * 60 + target.minute))
        slots = sorted(sorted(slots, key=minutes)[:9])
    buttons, row = [], []
    for s in slots[:9]:
        row.append((_local(salon, s).strftime("%H:%M"),
                    f"t|{service_id}|{staff_id}|{s.strftime('%Y-%m-%dT%H:%M')}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def _book(db: Session, salon: Salon, ext_id: int, name_hint: str | None,
          draft: Draft, s: Scrubbed) -> Reply:
    services, staff = _catalog(db, salon)
    if draft.service_id is None and len(services) == 1:
        draft.service_id = services[0].id
    if draft.service_id is None:
        prefix = (f"Услуги «{draft.service_mentioned}» у нас нет 😔 "
                  if draft.service_mentioned else "")
        draft.service_mentioned = None
        return _ask(db, salon, ext_id, draft, prefix + "На какую услугу записать?",
                    [[(f"{x.name} — {int(x.price)} ₽", f"s|{x.id}")] for x in services])
    service = db.get(Service, draft.service_id)

    if draft.staff_id is None and draft.staff_mentioned:
        names = ", ".join(x.name for x in staff)
        draft.staff_mentioned = None
        return _ask(db, salon, ext_id, draft,
                    f"Такого мастера у нас не нашёл 😔 Работают: {names}. К кому записать?",
                    [[("🎲 Любой мастер", f"st|{service.id}|0")]]
                    + [[(x.name, f"st|{service.id}|{x.id}")] for x in staff])
    staff_id = draft.staff_id or 0
    master = db.get(Staff, staff_id) if staff_id else None
    who = f" к мастеру {master.name}" if master else ""

    if draft.date is None:
        return _ask(db, salon, ext_id, draft,
                    f"{service.name}{who} — на какой день? Напишите, например: "
                    "«завтра после 18» или «в субботу утром».",
                    dialogs._choose_day(db, salon, service.id, staff_id).buttons[:-1])
    day = date.fromisoformat(draft.date)
    slots = dialogs._slots_for(db, salon, service, staff_id, day)
    day_label = _day_label(salon, day)
    if not slots:
        # ищем ближайший день с окнами, чтобы не гонять клиента по кругу
        for i in range(1, 15):
            alt = dialogs._slots_for(db, salon, service, staff_id, day + timedelta(days=i))
            if alt:
                alt_day = _local(salon, alt[0]).date().isoformat()
                return _ask(db, salon, ext_id, Draft(**{**asdict(draft), "date": alt_day}),
                            f"На {day_label}{who} свободных окон нет 😔 "
                            f"Ближайшее — {_when(salon, alt[0])}. Подойдёт? Напишите время "
                            "или выберите:",
                            _slot_buttons(salon, service.id, staff_id, alt))
        return _ask(db, salon, ext_id, draft,
                    f"В ближайшие две недели{who} свободных окон нет 😔 Напишите другую дату.")
    if not (draft.time_from or draft.time_to):
        return _ask(db, salon, ext_id, draft,
                    f"{service.name}{who}, {day_label}. Во сколько удобно? Свободно:",
                    _slot_buttons(salon, service.id, staff_id, slots))
    matching = [x for x in slots if _in_window(salon, x, draft)]
    if not matching:
        return _ask(db, salon, ext_id, draft,
                    f"На {day_label} {_window_text(draft)}{who} свободного нет 😔 "
                    "Есть другое время — напишите или выберите:",
                    _slot_buttons(salon, service.id, staff_id, slots,
                                  near=draft.time_from or draft.time_to))
    starts_at = matching[0]
    dt_iso = starts_at.strftime("%Y-%m-%dT%H:%M")

    customer = dialogs._customer(db, salon, ext_id)
    if customer is not None and customer.name and customer.phone:
        return dialogs._create_booking(db, salon, customer, service.id, staff_id, dt_iso)
    name = s.name or (customer.name if customer else None) or name_hint
    if s.phone:
        customer = upsert_customer(db, salon.id, tg_id=ext_id, phone=s.phone, name=name)
        return dialogs._create_booking(db, salon, customer, service.id, staff_id, dt_iso)
    # новый клиент без телефона в фразе: дальше обычные шаги ask_name / ask_phone
    payload = {"service_id": service.id, "staff_id": staff_id,
               "starts_at": dt_iso, "name": name or ""}
    summary = f"{service.name}{who}, {_when(salon, starts_at)}"
    if not name:
        dialogs._set_state(db, salon, ext_id, "ask_name", payload)
        return Reply(f"Есть окно: {summary}. Как вас зовут?")
    dialogs._set_state(db, salon, ext_id, "ask_phone", payload)
    return Reply(f"Есть окно: {summary}. Чтобы закрепить его за вами, "
                 "напишите номер телефона или нажмите кнопку ниже.",
                 request_contact=True)


# ── Перенос и отмена ──────────────────────────────────────────────────────
def _change(db: Session, salon: Salon, ext_id: int, draft: Draft) -> Reply:
    customer = dialogs._customer(db, salon, ext_id)
    rows = []
    if customer is not None:
        rows = db.scalars(
            select(Booking)
            .options(joinedload(Booking.service), joinedload(Booking.staff))
            .where(Booking.customer_id == customer.id,
                   Booking.status.in_(svc.ACTIVE_STATUSES),
                   Booking.starts_at > datetime.now(timezone.utc))
            .order_by(Booking.starts_at)
        ).all()
    if not rows:
        return Reply("Не нашёл у вас предстоящих записей 🤔",
                     buttons=[[("📅 Записаться", "m|book")], [("← Меню", "m|menu")]])
    if draft.service_id is not None:
        rows = [b for b in rows if b.service_id == draft.service_id] or rows
    booking = rows[0]
    summary = (f"{booking.service.name}, {_when(salon, booking.starts_at)}"
               + (f", мастер {booking.staff.name}" if booking.staff else ""))

    if draft.intent == "cancel":
        dialogs._set_state(db, salon, ext_id, "ai_cancel", {"booking_id": booking.id})
        return Reply(f"Отменить запись: {summary}? Напишите «да» или нажмите кнопку.",
                     buttons=[[("❌ Да, отменить", f"bk|cancel|{booking.id}")],
                              [("Нет, оставить", "m|menu")]])

    if draft.date is None:
        return dialogs._reminder_action(db, salon, ext_id, "resched", booking.id)
    day = date.fromisoformat(draft.date)
    slots = dialogs._slots_for(db, salon, booking.service, booking.staff_id or 0, day)
    matching = [x for x in slots if _in_window(salon, x, draft)] if (
        draft.time_from or draft.time_to) else []
    if matching:
        return dialogs._resched_done(db, salon, booking.id,
                                     matching[0].strftime("%Y-%m-%dT%H:%M"))
    return dialogs._resched_time(db, salon, booking.id, day)
