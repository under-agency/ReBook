"""Онбординг салонов: заготовки по нишам, дефолтные тексты, приглашение владельца."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.auth import make_invite_token
from app.models import Salon, Service, User

DEFAULT_WORK_HOURS = {
    "mon": ["10:00", "20:00"], "tue": ["10:00", "20:00"], "wed": ["10:00", "20:00"],
    "thu": ["10:00", "20:00"], "fri": ["10:00", "20:00"], "sat": ["10:00", "18:00"],
}

# Подстановки: {имя} {дата} {время} {услуга} {мастер} {салон}
DEFAULT_TEXTS = {
    "reminder_24h": "{имя}, напоминаем: завтра, {дата} в {время} — {услуга} у мастера {мастер}. Придёте?",
    "reminder_3h": "{имя}, ждём вас сегодня в {время}: {услуга}. Всё в силе?",
    "sms_chase": "{имя}, подтвердите запись {дата} в {время} ({салон}). Ответьте боту или позвоните нам.",
    "confirm": "Запись подтверждена: {услуга}, {дата} в {время}. Ждём вас!",
    "reactivation": "{имя}, давно не виделись! Пора обновить {услуга} — есть удобные окна на этой неделе. Записать?",
    # не шаблон, а база знаний ИИ-ассистента: адрес, как добраться, оплата, правила
    "faq": "",
}

# Заготовки услуг по нишам: (название, цена, длительность мин, цикл повтора дней)
NICHE_PRESETS: dict[str, list[tuple[str, int, int, int | None]]] = {
    "салон": [
        ("Женская стрижка", 2500, 60, 30),
        ("Мужская стрижка", 1500, 45, 30),
        ("Маникюр с покрытием", 2200, 90, 21),
        ("Окрашивание", 5000, 120, 60),
    ],
    "автосервис": [
        ("Замена масла", 1200, 30, 180),
        ("Экспресс-ТО", 1500, 45, 180),
        ("Шиномонтаж", 2000, 60, 180),
        ("Диагностика", 800, 30, 365),
    ],
    "стоматология": [
        ("Профгигиена", 4500, 60, 180),
        ("Лечение кариеса", 6000, 60, 365),
        ("Консультация", 1000, 30, 180),
    ],
}


def create_salon(
    db: Session, *, name: str, niche: str | None = None,
    tg_bot_token: str | None = None, avg_check: float | None = None,
    work_hours: dict | None = None, channel_priority: list[str] | None = None,
    sms_limit_month: int = 300, monthly_fee: float | None = None,
    timezone: str = "Europe/Moscow",
) -> Salon:
    salon = Salon(
        name=name, niche=niche, status="onboarding",
        tg_bot_token=tg_bot_token or None, avg_check=avg_check,
        work_hours=work_hours or DEFAULT_WORK_HOURS,
        channel_priority=channel_priority or ["tg", "max", "sms"],
        sms_limit_month=sms_limit_month, texts=dict(DEFAULT_TEXTS),
        monthly_fee=monthly_fee, timezone=timezone,
        feature_flags={"reactivation": False, "max_channel": False, "waitlist": False,
                       "llm_assistant": False},
    )
    db.add(salon)
    db.flush()
    for svc_name, price, dur, cycle in NICHE_PRESETS.get(niche or "", []):
        db.add(Service(salon_id=salon.id, name=svc_name, price=price,
                       duration_min=dur, repeat_cycle_days=cycle))
    return salon


def invite_owner(db: Session, salon: Salon, email: str) -> tuple[User, str]:
    """Создаёт учётку владельца с одноразовым токеном (72 ч). Возвращает (user, token)."""
    token, token_hash, expires = make_invite_token()
    user = User(
        salon_id=salon.id, email=email, pass_hash=None, role="owner",
        invite_token_hash=token_hash, invite_expires_at=expires,
    )
    db.add(user)
    db.flush()
    return user, token
