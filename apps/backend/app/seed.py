"""Демо-данные: python -m app.seed [--reset]

Создаёт superadmin, демо-салон с клиентами, записями и логом сообщений за
прошлый и текущий месяц — дашборд и отчёт сразу показывают живые цифры.
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text as sa_text

from app.auth import hash_password, make_invite_token
from app.config import settings
from app.db import SessionLocal
from app.models import (
    Base, Booking, Customer, MessageLog, Payment, Salon, Service, Staff, User,
)
from app.services.salons import DEFAULT_TEXTS, DEFAULT_WORK_HOURS, NICHE_PRESETS
from app import channels

rng = random.Random(42)

# база знаний ИИ-ассистента демо-салона (цены и часы он берёт из услуг и графика)
DEMO_FAQ = (
    "Адрес: Москва, ул. Садовая, 12, вход со двора, 2 этаж. От метро «Маяковская» 5 минут пешком.\n"
    "Оплата: наличные, карта, СБП.\n"
    "Парковка: бесплатная во дворе.\n"
    "Опоздание больше 15 минут — запись может сдвинуться или отмениться.\n"
    "Отменить или перенести запись можно в этом боте без звонка."
)

FIRST_NAMES = ["Анна", "Мария", "Ольга", "Елена", "Наталья", "Ирина", "Татьяна",
               "Светлана", "Юлия", "Екатерина", "Дарья", "Алина", "Вера", "Полина",
               "Ксения", "Людмила", "Галина", "Оксана", "Марина", "Алла", "Никита",
               "Сергей", "Андрей", "Дмитрий", "Павел", "Иван", "Олег", "Виктор",
               "Григорий", "Пётр"]


def reset(db) -> None:
    tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
    db.execute(sa_text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    db.commit()
    print("Базы очищены.")


def seed() -> None:
    db = SessionLocal()
    if db.scalar(select(User).where(User.email == "admin@rebook.ru")):
        print("Данные уже есть — запустите с --reset для пересоздания.")
        return

    # ── Superadmin ────────────────────────────────────────────────────────
    db.add(User(email="admin@rebook.ru", pass_hash=hash_password("admin12345"),
                role="superadmin"))

    # ── Демо-салон ────────────────────────────────────────────────────────
    tz = ZoneInfo("Europe/Moscow")
    salon = Salon(
        name="Салон «Анна»", status="active", niche="салон",
        tg_bot_token=settings.telegram_bot_token or None,
        avg_check=Decimal("2200"), work_hours=DEFAULT_WORK_HOURS,
        texts={**DEFAULT_TEXTS, "faq": DEMO_FAQ}, sms_limit_month=300,
        monthly_fee=Decimal("10000"),
        next_payment_at=(datetime.now(tz) + timedelta(days=12)).date(),
        onboarding_step=4,
        feature_flags={"reactivation": True, "max_channel": False, "waitlist": True,
                       "llm_assistant": True},
    )
    db.add(salon)
    db.flush()

    db.add(User(salon_id=salon.id, email="owner@demo.ru",
                pass_hash=hash_password("owner12345"), role="owner"))
    db.add(User(salon_id=salon.id, email="staff@demo.ru",
                pass_hash=hash_password("staff12345"), role="staff"))

    services = []
    for name, price, dur, cycle in NICHE_PRESETS["салон"]:
        s = Service(salon_id=salon.id, name=name, price=price,
                    duration_min=dur, repeat_cycle_days=cycle)
        db.add(s)
        services.append(s)
    staff = [Staff(salon_id=salon.id, name=n) for n in ("Мария", "Елена", "Виктория")]
    db.add_all(staff)
    db.flush()

    # ── Клиенты: активные, спящие, потерянные, исключённые ────────────────
    today = datetime.now(tz).date()
    customers: list[Customer] = []
    for i, name in enumerate(FIRST_NAMES):
        svc = rng.choice(services)
        # разброс давности визита относительно цикла услуги → все статусы
        factor = rng.choice([0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 4.0])
        days_ago = int(svc.repeat_cycle_days * factor)
        c = Customer(
            salon_id=salon.id, name=name,
            phone=f"+79{rng.randint(100000000, 999999999)}",
            tg_id=rng.randint(10**8, 10**9) if rng.random() < 0.6 else None,
            last_visit_at=today - timedelta(days=days_ago),
            last_service_id=svc.id,
            do_not_disturb=(i % 14 == 13),
        )
        db.add(c)
        customers.append(c)
    db.flush()

    # ── Записи и сообщения ────────────────────────────────────────────────
    def log(booking, customer, kind, channel, sent_at, status="sent"):
        template = salon.texts.get(kind if kind in salon.texts else "reminder_24h", "")
        db.add(MessageLog(
            salon_id=salon.id, customer_id=customer.id,
            booking_id=booking.id if booking else None,
            channel=channel, kind=kind,
            text=channels.render(template, salon=salon, customer=customer, booking=booking),
            cost=Decimal(str(settings.sms_cost)) if channel == "sms" else Decimal("0"),
            delivery_status="stub" if channel == "sms" else status,
            sent_at=sent_at,
        ))

    def make_booking(day_local, hour, minute, svc, cust, st, status, source="bot"):
        starts = datetime(day_local.year, day_local.month, day_local.day,
                          hour, minute, tzinfo=tz).astimezone(timezone.utc)
        b = Booking(salon_id=salon.id, customer_id=cust.id, service_id=svc.id,
                    staff_id=st.id, starts_at=starts, duration_min=svc.duration_min,
                    status=status, source=source,
                    created_at=starts - timedelta(days=rng.randint(2, 10)))
        db.add(b)
        db.flush()
        b.customer, b.service, b.staff = cust, svc, st
        return b

    # Прошлый месяц: ~60 записей с полным каскадом
    prev_month_last_day = today.replace(day=1) - timedelta(days=1)
    for _ in range(60):
        day = prev_month_last_day.replace(day=rng.randint(1, prev_month_last_day.day))
        cust, svc, st = rng.choice(customers), rng.choice(services), rng.choice(staff)
        roll = rng.random()
        if roll < 0.62:
            status = "done"
        elif roll < 0.72:
            status = "no_show"
        elif roll < 0.82:
            status = "cancelled"
        elif roll < 0.88:
            status = "rescheduled"
        else:
            status = "done"
        b = make_booking(day, rng.randint(10, 18), rng.choice([0, 30]), svc, cust, st, status)
        reminder_at = b.starts_at - timedelta(hours=24)
        if cust.tg_id:
            log(b, cust, "reminder_24h", "tg", reminder_at)
            if rng.random() < 0.35:  # не ответил кнопкой → SMS-догон
                log(b, cust, "sms_chase", "sms", b.starts_at - timedelta(hours=3))
        else:
            log(b, cust, "sms_chase", "sms", reminder_at)
        if status == "done" and rng.random() < 0.15:
            # визит пришёл из реактивации
            log(None, cust, "reactivation", "tg" if cust.tg_id else "sms",
                b.created_at - timedelta(days=rng.randint(1, 5)))
        if status == "done" and rng.random() < 0.08:
            log(b, cust, "waitlist_offer", "tg" if cust.tg_id else "sms",
                b.created_at - timedelta(hours=2))

    # Текущий месяц до сегодня
    for _ in range(25):
        if today.day == 1:
            break
        day = today.replace(day=rng.randint(1, max(1, today.day - 1)))
        cust, svc, st = rng.choice(customers), rng.choice(services), rng.choice(staff)
        status = rng.choices(["done", "no_show", "cancelled"], weights=[8, 1, 1])[0]
        b = make_booking(day, rng.randint(10, 18), rng.choice([0, 30]), svc, cust, st, status)
        if cust.tg_id:
            log(b, cust, "reminder_24h", "tg", b.starts_at - timedelta(hours=24))
        else:
            log(b, cust, "sms_chase", "sms", b.starts_at - timedelta(hours=24))

    # Сегодня и завтра: живые статусы для дашборда
    for offset, count in ((0, 4), (1, 5)):
        day = today + timedelta(days=offset)
        hours = rng.sample(range(10, 19), count)
        for h in hours:
            cust, svc, st = rng.choice(customers), rng.choice(services), rng.choice(staff)
            status = rng.choice(["confirmed", "reminded_24h", "new"]) if offset == 0 \
                else rng.choice(["new", "new", "reminded_24h"])
            b = make_booking(day, h, rng.choice([0, 30]), svc, cust, st, status)
            if status in ("confirmed", "reminded_24h"):
                log(b, cust, "reminder_24h", "tg" if cust.tg_id else "sms",
                    b.starts_at - timedelta(hours=24))

    # Оплата за прошлый период
    db.add(Payment(
        salon_id=salon.id, amount=Decimal("10000"),
        period_start=prev_month_last_day.replace(day=1),
        period_end=prev_month_last_day,
        paid_at=prev_month_last_day.replace(day=3),
        note="Абонентка, чек через «Мой налог»",
    ))

    # ── Второй салон в онбординге (для админки и изоляции) ────────────────
    salon_b = Salon(
        name="Барбершоп «Бритва»", status="onboarding", niche="салон",
        avg_check=Decimal("1500"), work_hours=DEFAULT_WORK_HOURS,
        texts=dict(DEFAULT_TEXTS), monthly_fee=Decimal("8000"), onboarding_step=0,
    )
    db.add(salon_b)
    db.flush()
    for name, price, dur, cycle in NICHE_PRESETS["салон"][:2]:
        db.add(Service(salon_id=salon_b.id, name=name, price=price,
                       duration_min=dur, repeat_cycle_days=cycle))
    token, token_hash, expires = make_invite_token()
    db.add(User(salon_id=salon_b.id, email="owner2@demo.ru", pass_hash=None,
                role="owner", invite_token_hash=token_hash, invite_expires_at=expires))

    db.commit()
    print("Сиды готовы.")
    print("  superadmin: admin@rebook.ru / admin12345")
    print("  владелец:   owner@demo.ru / owner12345")
    print("  админ:      staff@demo.ru / staff12345")
    print(f"  приглашение владельца салона Б: /invite/{token}")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset(SessionLocal())
    seed()
