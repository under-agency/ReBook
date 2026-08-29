from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ── Статусы ────────────────────────────────────────────────────────────────
SALON_STATUSES = ("onboarding", "active", "grace", "paused", "archived")
# рассылки идут только в этих статусах салона
SALON_SENDING_STATUSES = ("active", "grace")

BOOKING_STATUSES = (
    "new", "reminded_24h", "reminded_sms",
    "confirmed", "done", "rescheduled", "cancelled", "no_show",
)
BOOKING_FINAL_STATUSES = ("done", "rescheduled", "cancelled", "no_show")

ROLES = ("owner", "staff", "superadmin")
CHANNELS = ("tg", "max", "sms")


class Base(DeclarativeBase):
    pass


class Salon(Base):
    __tablename__ = "salons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="onboarding", server_default="onboarding")
    niche: Mapped[str | None] = mapped_column(Text)
    tg_bot_token: Mapped[str | None] = mapped_column(Text)
    max_bot_token: Mapped[str | None] = mapped_column(Text)
    channel_priority: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["tg", "max", "sms"], server_default="{tg,max,sms}"
    )
    avg_check: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    work_hours: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"mon":["10:00","20:00"],...}
    remind_offsets_h: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=lambda: [24, 3], server_default="{24,3}"
    )
    sms_limit_month: Mapped[int] = mapped_column(Integer, default=300, server_default="300")
    texts: Mapped[dict] = mapped_column(JSONB, default=dict)  # шаблоны сообщений
    timezone: Mapped[str] = mapped_column(Text, default="Europe/Moscow", server_default="Europe/Moscow")
    feature_flags: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    monthly_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    next_payment_at: Mapped[date | None] = mapped_column(Date)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    admin_tg_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"status IN {SALON_STATUSES}", name="salons_status_check"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int | None] = mapped_column(ForeignKey("salons.id"))  # NULL для superadmin
    email: Mapped[str] = mapped_column(Text, unique=True)
    pass_hash: Mapped[str | None] = mapped_column(Text)  # NULL до принятия приглашения
    role: Mapped[str] = mapped_column(Text)
    invite_token_hash: Mapped[str | None] = mapped_column(Text)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    salon: Mapped[Salon | None] = relationship()

    __table_args__ = (
        CheckConstraint(f"role IN {ROLES}", name="users_role_check"),
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    name: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    duration_min: Mapped[int] = mapped_column(Integer)
    repeat_cycle_days: Mapped[int | None] = mapped_column(Integer)  # NULL = без реактивации
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    name: Mapped[str] = mapped_column(Text)
    work_hours: Mapped[dict | None] = mapped_column(JSONB)  # NULL = часы салона
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)  # E.164
    tg_id: Mapped[int | None] = mapped_column(BigInteger)
    max_id: Mapped[int | None] = mapped_column(BigInteger)
    last_visit_at: Mapped[date | None] = mapped_column(Date)
    last_service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"))
    do_not_disturb: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_outreach_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    last_service: Mapped[Service | None] = relationship()

    __table_args__ = (
        UniqueConstraint("salon_id", "phone", name="customers_salon_phone_key"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[int] = mapped_column(Integer)  # снапшот из услуги на момент записи
    status: Mapped[str] = mapped_column(Text, default="new", server_default="new")
    source: Mapped[str] = mapped_column(Text, default="bot", server_default="bot")  # bot|manual|yclients
    note: Mapped[str | None] = mapped_column(Text)
    rescheduled_to_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped[Customer] = relationship()
    service: Mapped[Service] = relationship()
    staff: Mapped[Staff | None] = relationship()

    __table_args__ = (
        CheckConstraint(f"status IN {BOOKING_STATUSES}", name="bookings_status_check"),
        Index("ix_bookings_salon_starts_status", "salon_id", "starts_at", "status"),
    )


class Waitlist(Base):
    __tablename__ = "waitlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    wanted_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    wanted_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageLog(Base):
    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    channel: Mapped[str] = mapped_column(Text)
    # reminder_24h|reminder_3h|sms_chase|reactivation|confirm|waitlist_offer|report|faq|test
    kind: Mapped[str] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), server_default="0")
    delivery_status: Mapped[str | None] = mapped_column(Text)  # sent|stub|failed
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped[Customer | None] = relationship()

    __table_args__ = (
        CheckConstraint(f"channel IN {CHANNELS}", name="message_log_channel_check"),
        Index("ix_message_log_salon_sent", "salon_id", "sent_at"),
    )


class DialogState(Base):
    __tablename__ = "dialog_state"

    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"), primary_key=True)
    channel: Mapped[str] = mapped_column(Text, primary_key=True)
    ext_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # tg_id или max_id
    step: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # режим поддержки: superadmin работает в контексте этого салона
    acting_salon_id: Mapped[int | None] = mapped_column(ForeignKey("salons.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    salon_id: Mapped[int | None] = mapped_column(ForeignKey("salons.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text)  # login|create|update|status_change|...
    entity: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    is_support: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ip: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()

    __table_args__ = (
        Index("ix_audit_log_salon_created", "salon_id", "created_at"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salons.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    paid_at: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
