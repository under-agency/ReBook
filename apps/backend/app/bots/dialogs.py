"""Канал-агностичный конечный автомат записи (docs/08, 09).

Выбор из списков едет в callback_data кнопок, свободный ввод (имя, телефон) —
через таблицу dialog_state. Произвольный текст вне этих шагов разбирает
ИИ-ассистент (assistant.py), если он включён у салона. Адаптеры каналов (telegram.py) только переводят
апдейты в вызовы этих функций и рендерят Reply.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import channels
from app.models import Booking, Customer, DialogState, Salon, Service, Staff
from app.services import bookings as svc
from app.services.customers import normalize_phone, upsert_customer
from app.services.slots import free_slots

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@dataclass
class Reply:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)  # [[(label, callback)]]
    request_contact: bool = False
    admin_notify: str | None = None  # уведомление в чат админа салона


# ── Служебное ─────────────────────────────────────────────────────────────
def _customer(db: Session, salon: Salon, ext_id: int) -> Customer | None:
    return db.scalar(select(Customer).where(
        Customer.salon_id == salon.id, Customer.tg_id == ext_id))


def _state(db: Session, salon: Salon, ext_id: int) -> DialogState | None:
    return db.get(DialogState, (salon.id, "tg", ext_id))


def _set_state(db: Session, salon: Salon, ext_id: int, step: str, payload: dict) -> None:
    state = _state(db, salon, ext_id)
    if state is None:
        db.add(DialogState(salon_id=salon.id, channel="tg", ext_id=ext_id,
                           step=step, payload=payload))
    else:
        state.step = step
        state.payload = payload


def _clear_state(db: Session, salon: Salon, ext_id: int) -> None:
    state = _state(db, salon, ext_id)
    if state is not None:
        db.delete(state)
        db.flush()  # иначе db.get в том же апдейте вернёт удалённую строку и _set_state её потеряет


def _gate(salon: Salon) -> Reply | None:
    if salon.status in ("onboarding", "archived"):
        return Reply("Запись скоро откроется — салон настраивает систему. Загляните позже 🙌")
    return None  # в paused бот отвечает и записывает — рассылки остановлены отдельно


def main_menu(salon: Salon, greeting: bool = True, name: str | None = None) -> Reply:
    from app.bots import assistant
    hello = f"👋 Здравствуйте{', ' + name if name else ''}!\n{salon.name} на связи.\n\n" if greeting else ""
    hint = ("\n\nМожно просто написать, что нужно, — например: "
            "«на маникюр в пятницу после 18»." if assistant.active(salon) else "")
    return Reply(
        hello + "Чем помочь?" + hint,
        buttons=[
            [("📅 Записаться", "m|book")],
            [("🗓 Мои записи", "m|my")],
            [("💬 Вопрос администратору", "m|ask")],
            [("🔕 Отписаться от напоминаний", "m|unsub")],
        ],
    )


# ── Входные точки ─────────────────────────────────────────────────────────
def handle_start(db: Session, salon: Salon, ext_id: int,
                 name_hint: str | None, param: str | None) -> Reply:
    if (gate := _gate(salon)):
        return gate
    _clear_state(db, salon, ext_id)
    # deep link из SMS: /start c_<customer_id> — связываем phone → tg_id
    if param and param.startswith("c_"):
        try:
            cust = db.get(Customer, int(param[2:]))
        except ValueError:
            cust = None
        if cust is not None and cust.salon_id == salon.id and cust.tg_id is None:
            cust.tg_id = ext_id
    customer = _customer(db, salon, ext_id)
    return main_menu(salon, name=(customer.name if customer else name_hint))


def handle_callback(db: Session, salon: Salon, ext_id: int,
                    name_hint: str | None, data: str) -> Reply:
    if (gate := _gate(salon)):
        return gate
    parts = data.split("|")
    state = _state(db, salon, ext_id)
    if state is not None and state.step == "ai_book":
        from app.bots import assistant
        # кнопка-ответ на уточнение ассистента: день и время из фразы не теряем
        if (reply := assistant.handle_button(db, salon, ext_id, name_hint,
                                             dict(state.payload), parts)) is not None:
            return reply
    if state is not None and state.step.startswith("ai_"):
        _clear_state(db, salon, ext_id)  # клиент ушёл на кнопки — черновик ассистента не нужен
    try:
        match parts:
            case ["m", "menu"]:
                _clear_state(db, salon, ext_id)
                return main_menu(salon, greeting=False)
            case ["m", "book"]:
                return _choose_service(db, salon)
            case ["m", "my"]:
                return _my_bookings(db, salon, ext_id)
            case ["m", "ask"]:
                _set_state(db, salon, ext_id, "ask_question", {})
                return Reply("Напишите ваш вопрос — передадим администратору.")
            case ["m", "unsub"]:
                return _unsubscribe(db, salon, ext_id)
            case ["s", sid]:
                return _choose_staff(db, salon, int(sid))
            case ["st", sid, stid]:
                return _choose_day(db, salon, int(sid), int(stid))
            case ["d", sid, stid, day_iso]:
                return _choose_time(db, salon, int(sid), int(stid), date.fromisoformat(day_iso))
            case ["t", sid, stid, dt_iso]:
                return _slot_chosen(db, salon, ext_id, name_hint, int(sid), int(stid), dt_iso)
            case ["bk", action, bid]:
                return _reminder_action(db, salon, ext_id, action, int(bid))
            case ["rd", bid, day_iso]:
                return _resched_time(db, salon, int(bid), date.fromisoformat(day_iso))
            case ["rt", bid, dt_iso]:
                return _resched_done(db, salon, int(bid), dt_iso)
            case _:
                return main_menu(salon, greeting=False)
    except (ValueError, KeyError):
        return main_menu(salon, greeting=False)


def handle_text(db: Session, salon: Salon, ext_id: int, name_hint: str | None,
                text: str, contact_phone: str | None = None) -> Reply:
    if (gate := _gate(salon)):
        return gate
    from app.bots import assistant
    state = _state(db, salon, ext_id)
    if state is None or state.step.startswith("ai_"):
        if assistant.active(salon):
            return assistant.handle(db, salon, ext_id, name_hint, text,
                                    state.step if state else None,
                                    dict(state.payload) if state else None)
        _clear_state(db, salon, ext_id)
        return main_menu(salon, greeting=False)
    if state.step == "ask_question":
        _clear_state(db, salon, ext_id)
        customer = _customer(db, salon, ext_id)
        who = customer.name if customer and customer.name else (name_hint or "клиент")
        return Reply("Передал администратору — вам ответят в ближайшее время 🙌",
                     buttons=[[("← Меню", "m|menu")]],
                     admin_notify=f"❓ Вопрос от {who}:\n{text}")
    if state.step == "ask_name":
        payload = dict(state.payload)
        payload["name"] = text.strip()[:100]
        _set_state(db, salon, ext_id, "ask_phone", payload)
        return Reply("Отлично! Теперь поделитесь номером телефона — по кнопке "
                     "или напишите его текстом.", request_contact=True)
    if state.step == "ask_phone":
        phone = normalize_phone(contact_phone or text)
        if phone is None:
            return Reply("Не разобрал номер 😕 Формат: +7 900 000-00-00. "
                         "Попробуйте ещё раз или нажмите кнопку ниже.",
                         request_contact=True)
        payload = dict(state.payload)
        _clear_state(db, salon, ext_id)
        customer = upsert_customer(db, salon.id, tg_id=ext_id,
                                   phone=phone, name=payload.get("name"))
        return _create_booking(db, salon, customer,
                               payload["service_id"], payload["staff_id"],
                               payload["starts_at"])
    _clear_state(db, salon, ext_id)
    if assistant.active(salon):
        return assistant.handle(db, salon, ext_id, name_hint, text, None, None)
    return main_menu(salon, greeting=False)


# ── Шаги записи ───────────────────────────────────────────────────────────
def _choose_service(db: Session, salon: Salon) -> Reply:
    services = db.scalars(select(Service).where(
        Service.salon_id == salon.id, Service.is_active.is_(True)).order_by(Service.id)).all()
    if not services:
        return Reply("Пока нет доступных услуг — загляните позже.")
    return Reply("Выберите услугу:", buttons=[
        [(f"{s.name} — {int(s.price)} ₽ · {s.duration_min} мин", f"s|{s.id}")]
        for s in services
    ] + [[("← Меню", "m|menu")]])


def _choose_staff(db: Session, salon: Salon, service_id: int) -> Reply:
    staff = db.scalars(select(Staff).where(
        Staff.salon_id == salon.id, Staff.is_active.is_(True)).order_by(Staff.id)).all()
    buttons = [[("🎲 Любой мастер", f"st|{service_id}|0")]]
    buttons += [[(s.name, f"st|{service_id}|{s.id}")] for s in staff]
    buttons.append([("← Назад", "m|book")])
    return Reply("К какому мастеру?", buttons=buttons)


def _choose_day(db: Session, salon: Salon, service_id: int, staff_id: int) -> Reply:
    tz = ZoneInfo(salon.timezone)
    today = datetime.now(tz).date()
    buttons = []
    for i in range(7):
        d = today + timedelta(days=i)
        label = "Сегодня" if i == 0 else "Завтра" if i == 1 else WEEKDAYS[d.weekday()]
        buttons.append([(f"{label}, {d.strftime('%d.%m')}",
                         f"d|{service_id}|{staff_id}|{d.isoformat()}")])
    buttons.append([("← Назад", f"s|{service_id}")])
    return Reply("Выберите день:", buttons=buttons)


def _slots_for(db: Session, salon: Salon, service: Service,
               staff_id: int, day: date) -> list[datetime]:
    tz = ZoneInfo(salon.timezone)
    staff = db.get(Staff, staff_id) if staff_id else None
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    busy = svc._busy_for(db, salon.id, staff.id if staff else None,
                         day_start, day_start + timedelta(days=1))
    return free_slots(
        work_hours=salon.work_hours, staff_hours=staff.work_hours if staff else None,
        duration_min=service.duration_min, day=day, tz=tz, busy=busy,
        now=datetime.now(timezone.utc),
    )


def _choose_time(db: Session, salon: Salon, service_id: int,
                 staff_id: int, day: date) -> Reply:
    service = db.get(Service, service_id)
    slots = _slots_for(db, salon, service, staff_id, day)
    if not slots:
        return Reply("На этот день свободных окон нет 😔 Выберите другой:",
                     buttons=[[("← К выбору дня", f"st|{service_id}|{staff_id}")]])
    tz = ZoneInfo(salon.timezone)
    buttons, row = [], []
    for s in slots[:24]:
        row.append((s.astimezone(tz).strftime("%H:%M"),
                    f"t|{service_id}|{staff_id}|{s.strftime('%Y-%m-%dT%H:%M')}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([("← К выбору дня", f"st|{service_id}|{staff_id}")])
    return Reply("Свободное время:", buttons=buttons)


def _slot_chosen(db: Session, salon: Salon, ext_id: int, name_hint: str | None,
                 service_id: int, staff_id: int, dt_iso: str) -> Reply:
    customer = _customer(db, salon, ext_id)
    if customer is not None and customer.name and customer.phone:
        return _create_booking(db, salon, customer, service_id, staff_id, dt_iso)
    # новый клиент: имя и телефон свободным вводом через dialog_state
    _set_state(db, salon, ext_id, "ask_name", {
        "service_id": service_id, "staff_id": staff_id, "starts_at": dt_iso,
        "name": name_hint or "",
    })
    return Reply("Как вас зовут?")


def _create_booking(db: Session, salon: Salon, customer: Customer,
                    service_id: int, staff_id: int, dt_iso: str) -> Reply:
    service = db.get(Service, service_id)
    staff = db.get(Staff, staff_id) if staff_id else None
    starts_at = datetime.fromisoformat(dt_iso).replace(tzinfo=timezone.utc)
    try:
        booking = svc.create_booking(db, salon, customer=customer, service=service,
                                     staff=staff, starts_at=starts_at, source="bot")
    except svc.BookingConflict:
        return Reply("Увы, это время только что заняли 😔 Выберите другое:",
                     buttons=[[("← К выбору дня", f"st|{service_id}|{staff_id}")]])
    booking.customer, booking.service, booking.staff = customer, service, staff
    text = channels.render(salon.texts.get("confirm", ""), salon=salon,
                           customer=customer, booking=booking)
    channels.send(db, salon, customer, "confirm", text, booking=booking,
                  transport=lambda *a, **kw: True)  # клиент получает ответ в этом же чате
    tz = ZoneInfo(salon.timezone)
    local = starts_at.astimezone(tz)
    when = f"{local.day} {channels.RU_MONTHS[local.month - 1]} в {local.strftime('%H:%M')}"
    return Reply(
        f"🎉 Записал!\n\n"
        f"💇 {service.name}\n"
        f"👤 {staff.name if staff else 'Любой мастер'}\n"
        f"📅 {when}\n"
        f"💰 {int(service.price)} ₽\n\n"
        f"Напомним накануне. До встречи!",
        buttons=[[("← Меню", "m|menu")]],
        admin_notify=f"🆕 Новая запись: {customer.name or 'клиент'}, {service.name}, {when}"
                     + (f", мастер {staff.name}" if staff else ""),
    )


# ── Мои записи / отмена / перенос ─────────────────────────────────────────
def _my_bookings(db: Session, salon: Salon, ext_id: int) -> Reply:
    customer = _customer(db, salon, ext_id)
    if customer is None:
        return Reply("У вас пока нет записей.", buttons=[
            [("📅 Записаться", "m|book")], [("← Меню", "m|menu")]])
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(Booking)
        .options(joinedload(Booking.service), joinedload(Booking.staff))
        .where(Booking.customer_id == customer.id,
               Booking.status.in_(svc.ACTIVE_STATUSES),
               Booking.starts_at > now)
        .order_by(Booking.starts_at).limit(5)
    ).all()
    if not rows:
        return Reply("Предстоящих записей нет.", buttons=[
            [("📅 Записаться", "m|book")], [("← Меню", "m|menu")]])
    tz = ZoneInfo(salon.timezone)
    lines, buttons = [], []
    for b in rows:
        local = b.starts_at.astimezone(tz)
        when = f"{local.day} {channels.RU_MONTHS[local.month - 1]} {local.strftime('%H:%M')}"
        lines.append(f"• {b.service.name} — {when}"
                     + (f" ({b.staff.name})" if b.staff else ""))
        buttons.append([(f"🔄 {when}", f"bk|resched|{b.id}"),
                        (f"❌ {when}", f"bk|cancel|{b.id}")])
    buttons.append([("← Меню", "m|menu")])
    return Reply("Ваши записи:\n" + "\n".join(lines) +
                 "\n\nПеренести 🔄 или отменить ❌:", buttons=buttons)


def _reminder_action(db: Session, salon: Salon, ext_id: int,
                     action: str, booking_id: int) -> Reply:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.salon_id != salon.id:
        return Reply("Запись не найдена — возможно, её уже отменили.")
    if action == "confirm":
        if booking.status in svc.ACTIVE_STATUSES:
            svc.set_status(db, booking, "confirmed")
        return Reply("Отлично, ждём вас! ✅", buttons=[[("← Меню", "m|menu")]])
    if action == "cancel":
        if booking.status in svc.ACTIVE_STATUSES:
            svc.set_status(db, booking, "cancelled")
            cust = db.get(Customer, booking.customer_id)
            return Reply("Запись отменена. Будем рады видеть вас в другой раз 🙌",
                         buttons=[[("📅 Записаться снова", "m|book")], [("← Меню", "m|menu")]],
                         admin_notify=f"❌ Отмена: {cust.name or 'клиент'}, запись #{booking.id}"
                                      " — слот освободился")
        return Reply("Эту запись уже нельзя отменить.", buttons=[[("← Меню", "m|menu")]])
    if action == "resched":
        if booking.status not in svc.ACTIVE_STATUSES:
            return Reply("Эту запись уже нельзя перенести.", buttons=[[("← Меню", "m|menu")]])
        # выбор нового дня для той же услуги/мастера
        tz = ZoneInfo(salon.timezone)
        today = datetime.now(tz).date()
        buttons = []
        for i in range(7):
            d = today + timedelta(days=i)
            label = "Сегодня" if i == 0 else "Завтра" if i == 1 else WEEKDAYS[d.weekday()]
            buttons.append([(f"{label}, {d.strftime('%d.%m')}", f"rd|{booking_id}|{d.isoformat()}")])
        buttons.append([("← Меню", "m|menu")])
        return Reply("На какой день перенести?", buttons=buttons)
    return main_menu(salon, greeting=False)


def _resched_time(db: Session, salon: Salon, booking_id: int, day: date) -> Reply:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.salon_id != salon.id:
        return Reply("Запись не найдена.")
    service = db.get(Service, booking.service_id)
    slots = _slots_for(db, salon, service, booking.staff_id or 0, day)
    if not slots:
        return Reply("В этот день свободных окон нет 😔",
                     buttons=[[("← К выбору дня", f"bk|resched|{booking_id}")]])
    tz = ZoneInfo(salon.timezone)
    buttons, row = [], []
    for s in slots[:24]:
        row.append((s.astimezone(tz).strftime("%H:%M"),
                    f"rt|{booking_id}|{s.strftime('%Y-%m-%dT%H:%M')}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([("← К выбору дня", f"bk|resched|{booking_id}")])
    return Reply("Свободное время:", buttons=buttons)


def _resched_done(db: Session, salon: Salon, booking_id: int, dt_iso: str) -> Reply:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.salon_id != salon.id:
        return Reply("Запись не найдена.")
    staff = db.get(Staff, booking.staff_id) if booking.staff_id else None
    starts_at = datetime.fromisoformat(dt_iso).replace(tzinfo=timezone.utc)
    try:
        new_booking = svc.reschedule(db, salon, booking,
                                     new_starts_at=starts_at, staff=staff)
    except (svc.BookingConflict, svc.InvalidTransition):
        return Reply("Это время уже занято, выберите другое:",
                     buttons=[[("← К выбору дня", f"bk|resched|{booking_id}")]])
    service = db.get(Service, new_booking.service_id)
    cust = db.get(Customer, new_booking.customer_id)
    tz = ZoneInfo(salon.timezone)
    local = starts_at.astimezone(tz)
    when = f"{local.day} {channels.RU_MONTHS[local.month - 1]} в {local.strftime('%H:%M')}"
    return Reply(f"🔄 Перенёс! Ждём вас {when}.",
                 buttons=[[("← Меню", "m|menu")]],
                 admin_notify=f"🔄 Перенос: {cust.name or 'клиент'}, {service.name} → {when}")


def _unsubscribe(db: Session, salon: Salon, ext_id: int) -> Reply:
    customer = _customer(db, salon, ext_id)
    if customer is None:
        return Reply("Вы и не были подписаны 🙂", buttons=[[("← Меню", "m|menu")]])
    customer.do_not_disturb = True
    return Reply("Готово — маркетинговых сообщений больше не будет.\n"
                 "Напоминания о ваших записях продолжат приходить.",
                 buttons=[[("← Меню", "m|menu")]])
