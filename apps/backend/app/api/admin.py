from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.audit import audit
from app.api.dto import audit_dto, iso, message_dto
from app.db import get_db
from app.deps import Ctx, require_superadmin
from app.models import AuditLog, MessageLog, Payment, Salon, User
from app.services.salons import NICHE_PRESETS, create_salon, invite_owner

router = APIRouter()


def _month_start_utc(salon: Salon, now: datetime) -> datetime:
    tz = ZoneInfo(salon.timezone)
    local_now = now.astimezone(tz)
    return datetime(local_now.year, local_now.month, 1, tzinfo=tz).astimezone(timezone.utc)


EMPTY_HEALTH = {"last_activity": None, "errors_24h": 0, "sms_used": 0}


def _health_map(db: Session, salons: list[Salon]) -> dict[int, dict]:
    """Здоровье всех салонов одним запросом.

    Салоны живут в разных часовых поясах, поэтому «начало месяца» для счётчика
    SMS у каждого своё — подставляем его через CASE по salon_id.
    """
    if not salons:
        return {}
    now = datetime.now(timezone.utc)
    month_starts = case(
        *[(MessageLog.salon_id == s.id, _month_start_utc(s, now)) for s in salons],
        else_=now,
    )
    rows = db.execute(select(
        MessageLog.salon_id,
        func.max(MessageLog.sent_at),
        func.count(MessageLog.id).filter(
            MessageLog.delivery_status == "failed",
            MessageLog.sent_at >= now - timedelta(hours=24)),
        func.count(MessageLog.id).filter(
            MessageLog.channel == "sms", MessageLog.sent_at >= month_starts),
    ).where(
        MessageLog.salon_id.in_([s.id for s in salons])
    ).group_by(MessageLog.salon_id)).all()
    health = {s.id: dict(EMPTY_HEALTH) for s in salons}
    for salon_id, last_activity, errors_24h, sms_used in rows:
        health[salon_id] = {
            "last_activity": iso(last_activity),
            "errors_24h": errors_24h or 0,
            "sms_used": sms_used or 0,
        }
    return health


def _salon_health(db: Session, salon: Salon) -> dict:
    return _health_map(db, [salon])[salon.id]


def _salon_dto(db: Session, salon: Salon, health: dict | None = None,
               with_health: bool = True) -> dict:
    dto = {
        "id": salon.id, "name": salon.name, "status": salon.status, "niche": salon.niche,
        "timezone": salon.timezone,
        "avg_check": float(salon.avg_check) if salon.avg_check else None,
        "sms_limit_month": salon.sms_limit_month,
        "monthly_fee": float(salon.monthly_fee) if salon.monthly_fee else None,
        "next_payment_at": iso(salon.next_payment_at),
        "feature_flags": salon.feature_flags,
        "onboarding_step": salon.onboarding_step,
        "has_tg_bot": bool(salon.tg_bot_token),
        "work_hours": salon.work_hours,
        "channel_priority": salon.channel_priority,
        "created_at": iso(salon.created_at),
    }
    if with_health:
        dto["health"] = health if health is not None else _salon_health(db, salon)
    return dto


def _problem_rank(dto: dict) -> tuple:
    """Сортировка: сначала проблемные (docs/10-crm-logic.md)."""
    has_errors = dto["health"]["errors_24h"] > 0
    status_rank = {"paused": 0, "grace": 1, "onboarding": 2,
                   "active": 3, "archived": 4}.get(dto["status"], 5)
    return (0 if has_errors else 1, status_rank, dto["name"])


@router.get("/salons")
def list_salons(ctx: Ctx = Depends(require_superadmin), db: Session = Depends(get_db)):
    salons = list(db.scalars(select(Salon)).all())
    health = _health_map(db, salons)
    items = [_salon_dto(db, s, health=health[s.id]) for s in salons]
    items.sort(key=_problem_rank)
    return {"items": items}


@router.get("/niches")
def niches(ctx: Ctx = Depends(require_superadmin)):
    return {"niches": [
        {"key": key, "services": [
            {"name": n, "price": p, "duration_min": d, "repeat_cycle_days": c}
            for n, p, d, c in preset
        ]} for key, preset in NICHE_PRESETS.items()
    ]}


class SalonCreateIn(BaseModel):
    name: str
    niche: str | None = None
    owner_email: EmailStr
    tg_bot_token: str | None = None
    avg_check: float | None = None
    work_hours: dict | None = None
    channel_priority: list[str] | None = None
    sms_limit_month: int = 300
    monthly_fee: float | None = None
    timezone: str = "Europe/Moscow"


@router.post("/salons")
def create_salon_endpoint(body: SalonCreateIn, ctx: Ctx = Depends(require_superadmin),
                          db: Session = Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.email) == body.owner_email.lower())):
        raise HTTPException(409, "Пользователь с этим email уже существует")
    salon = create_salon(
        db, name=body.name, niche=body.niche, tg_bot_token=body.tg_bot_token,
        avg_check=body.avg_check, work_hours=body.work_hours,
        channel_priority=body.channel_priority, sms_limit_month=body.sms_limit_month,
        monthly_fee=body.monthly_fee, timezone=body.timezone,
    )
    owner, invite_token = invite_owner(db, salon, body.owner_email)
    audit(db, ctx, "create", "salon", salon.id, salon_id=salon.id,
          after={"name": salon.name, "owner_email": body.owner_email})
    db.commit()
    # email-сервиса в dev нет — ссылку-приглашение отдаём в ответе
    return {
        "salon": _salon_dto(db, salon),
        "invite_link": f"/invite/{invite_token}",
        "owner_email": owner.email,
    }


@router.get("/salons/{salon_id}")
def get_salon(salon_id: int, ctx: Ctx = Depends(require_superadmin),
              db: Session = Depends(get_db)):
    salon = db.get(Salon, salon_id)
    if salon is None:
        raise HTTPException(404, "Салон не найден")
    dto = _salon_dto(db, salon)
    dto["users"] = [
        {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active,
         "invited": u.pass_hash is None}
        for u in db.scalars(select(User).where(User.salon_id == salon.id)).all()
    ]
    dto["payments"] = [
        {"id": p.id, "amount": float(p.amount), "period_start": iso(p.period_start),
         "period_end": iso(p.period_end), "paid_at": iso(p.paid_at), "note": p.note}
        for p in db.scalars(select(Payment).where(Payment.salon_id == salon.id)
                            .order_by(Payment.period_start.desc())).all()
    ]
    return dto


class SalonPatchIn(BaseModel):
    name: str | None = None
    status: str | None = None
    tg_bot_token: str | None = None
    avg_check: float | None = None
    sms_limit_month: int | None = None
    monthly_fee: float | None = None
    next_payment_at: date | None = None
    feature_flags: dict | None = None
    admin_tg_chat_id: int | None = None
    timezone: str | None = None


@router.patch("/salons/{salon_id}")
def patch_salon(salon_id: int, body: SalonPatchIn,
                ctx: Ctx = Depends(require_superadmin), db: Session = Depends(get_db)):
    salon = db.get(Salon, salon_id)
    if salon is None:
        raise HTTPException(404, "Салон не найден")
    data = body.model_dump(exclude_unset=True)
    before = {k: str(getattr(salon, k)) for k in data}
    for field, value in data.items():
        setattr(salon, field, value)
    audit(db, ctx, "update", "salon", salon.id, salon_id=salon.id,
          before=before, after={k: str(v) for k, v in data.items()})
    db.commit()
    return _salon_dto(db, salon)


class PaymentIn(BaseModel):
    amount: float
    period_start: date
    period_end: date
    paid_at: date | None = None
    note: str | None = None


@router.post("/salons/{salon_id}/payments")
def add_payment(salon_id: int, body: PaymentIn,
                ctx: Ctx = Depends(require_superadmin), db: Session = Depends(get_db)):
    salon = db.get(Salon, salon_id)
    if salon is None:
        raise HTTPException(404, "Салон не найден")
    payment = Payment(salon_id=salon.id, **body.model_dump())
    db.add(payment)
    if body.paid_at:
        salon.next_payment_at = body.period_end
        # оплата снимает grace/paused
        if salon.status in ("grace", "paused"):
            salon.status = "active"
    audit(db, ctx, "create", "payment", None, salon_id=salon.id,
          after={"amount": body.amount, "period": f"{body.period_start}..{body.period_end}"})
    db.commit()
    return {"ok": True, "salon_status": salon.status}


@router.post("/salons/{salon_id}/invite")
def reissue_invite(salon_id: int, ctx: Ctx = Depends(require_superadmin),
                   db: Session = Depends(get_db)):
    salon = db.get(Salon, salon_id)
    if salon is None:
        raise HTTPException(404, "Салон не найден")
    owner = db.scalar(select(User).where(User.salon_id == salon.id, User.role == "owner"))
    if owner is None:
        raise HTTPException(404, "У салона нет владельца")
    from app.auth import make_invite_token
    token, token_hash, expires = make_invite_token()
    owner.invite_token_hash = token_hash
    owner.invite_expires_at = expires
    audit(db, ctx, "reissue_invite", "user", owner.id, salon_id=salon.id)
    db.commit()
    return {"invite_link": f"/invite/{token}", "owner_email": owner.email}


# ── Режим поддержки ───────────────────────────────────────────────────────
@router.post("/salons/{salon_id}/impersonate")
def impersonate(salon_id: int, ctx: Ctx = Depends(require_superadmin),
                db: Session = Depends(get_db)):
    """Вход в кабинет салона: всё пишется в аудит с пометкой «действие поддержки»."""
    salon = db.get(Salon, salon_id)
    if salon is None:
        raise HTTPException(404, "Салон не найден")
    ctx.session.acting_salon_id = salon.id
    db.add(AuditLog(salon_id=salon.id, user_id=ctx.user.id, action="support_enter",
                    entity="salon", entity_id=salon.id, is_support=True, ip=ctx.session.ip))
    db.commit()
    return {"ok": True, "salon": {"id": salon.id, "name": salon.name}}


@router.post("/impersonate/stop")
def impersonate_stop(ctx: Ctx = Depends(require_superadmin), db: Session = Depends(get_db)):
    if ctx.session.acting_salon_id:
        db.add(AuditLog(salon_id=ctx.session.acting_salon_id, user_id=ctx.user.id,
                        action="support_exit", entity="salon",
                        entity_id=ctx.session.acting_salon_id, is_support=True,
                        ip=ctx.session.ip))
        ctx.session.acting_salon_id = None
        db.commit()
    return {"ok": True}


# ── Глобальные журналы ────────────────────────────────────────────────────
@router.get("/audit")
def global_audit(
    salon_id: int | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require_superadmin), db: Session = Depends(get_db),
):
    q = select(AuditLog)
    if salon_id is not None:
        q = q.where(AuditLog.salon_id == salon_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.options(joinedload(AuditLog.user))
                      .order_by(AuditLog.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for a in rows:
        dto = audit_dto(a)
        dto["salon_id"] = a.salon_id
        items.append(dto)
    return {"items": items, "total": total, "page": page}


@router.get("/messages")
def global_messages(
    salon_id: int | None = None, channel: str | None = None,
    delivery_status: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require_superadmin), db: Session = Depends(get_db),
):
    q = select(MessageLog)
    if salon_id is not None:
        q = q.where(MessageLog.salon_id == salon_id)
    if channel:
        q = q.where(MessageLog.channel == channel)
    if delivery_status:
        q = q.where(MessageLog.delivery_status == delivery_status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.options(joinedload(MessageLog.customer))
                      .order_by(MessageLog.sent_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for m in rows:
        dto = message_dto(m)
        dto["salon_id"] = m.salon_id
        items.append(dto)
    return {"items": items, "total": total, "page": page}
