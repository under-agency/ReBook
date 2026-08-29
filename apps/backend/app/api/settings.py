from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import Ctx, get_owned_or_404, require_owner, require_salon
from app.models import Salon, Service, Staff

router = APIRouter()


def _salon_settings_dto(salon: Salon) -> dict:
    # токены ботов, лимит SMS и тариф владелец не меняет — это наша зона
    return {
        "name": salon.name, "status": salon.status, "niche": salon.niche,
        "timezone": salon.timezone, "work_hours": salon.work_hours,
        "texts": salon.texts, "remind_offsets_h": salon.remind_offsets_h,
        "channel_priority": salon.channel_priority,
        "avg_check": float(salon.avg_check) if salon.avg_check else None,
        "sms_limit_month": salon.sms_limit_month,  # read-only для владельца
        "has_tg_bot": bool(salon.tg_bot_token),
    }


@router.get("")
def get_settings(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    return _salon_settings_dto(db.get(Salon, ctx.salon_id))


class SettingsPatchIn(BaseModel):
    name: str | None = None
    timezone: str | None = None
    work_hours: dict | None = None
    texts: dict | None = None
    remind_offsets_h: list[int] | None = None
    channel_priority: list[str] | None = None
    avg_check: float | None = None


@router.patch("")
def patch_settings(body: SettingsPatchIn, ctx: Ctx = Depends(require_owner),
                   db: Session = Depends(get_db)):
    salon = db.get(Salon, ctx.salon_id)
    before = _salon_settings_dto(salon)
    for field in ("name", "timezone", "work_hours", "texts",
                  "remind_offsets_h", "channel_priority", "avg_check"):
        value = getattr(body, field)
        if value is not None:
            setattr(salon, field, value)
    audit(db, ctx, "update", "salon_settings", salon.id,
          before=before, after=_salon_settings_dto(salon))
    db.commit()
    return _salon_settings_dto(salon)


# ── Услуги ────────────────────────────────────────────────────────────────
def _service_dto(s: Service) -> dict:
    return {"id": s.id, "name": s.name, "price": float(s.price),
            "duration_min": s.duration_min, "repeat_cycle_days": s.repeat_cycle_days,
            "is_active": s.is_active}


@router.get("/services")
def list_services(ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    rows = db.scalars(select(Service).where(Service.salon_id == ctx.salon_id)
                      .order_by(Service.id)).all()
    return {"items": [_service_dto(s) for s in rows]}


class ServiceIn(BaseModel):
    name: str
    price: float
    duration_min: int
    repeat_cycle_days: int | None = None
    is_active: bool = True


@router.post("/services")
def create_service(body: ServiceIn, ctx: Ctx = Depends(require_owner),
                   db: Session = Depends(get_db)):
    service = Service(salon_id=ctx.salon_id, **body.model_dump())
    db.add(service)
    db.flush()
    audit(db, ctx, "create", "service", service.id, after=_service_dto(service))
    db.commit()
    return _service_dto(service)


class ServicePatchIn(BaseModel):
    name: str | None = None
    price: float | None = None
    duration_min: int | None = None
    repeat_cycle_days: int | None = None
    is_active: bool | None = None


@router.patch("/services/{service_id}")
def patch_service(service_id: int, body: ServicePatchIn,
                  ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    service = get_owned_or_404(db, Service, service_id, ctx.salon_id)
    before = _service_dto(service)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    audit(db, ctx, "update", "service", service.id, before=before, after=_service_dto(service))
    db.commit()
    return _service_dto(service)


@router.delete("/services/{service_id}")
def delete_service(service_id: int, ctx: Ctx = Depends(require_owner),
                   db: Session = Depends(get_db)):
    service = get_owned_or_404(db, Service, service_id, ctx.salon_id)
    service.is_active = False  # записи ссылаются на услугу — только деактивация
    audit(db, ctx, "deactivate", "service", service.id)
    db.commit()
    return {"ok": True}


# ── Мастера ───────────────────────────────────────────────────────────────
def _staff_dto(s: Staff) -> dict:
    return {"id": s.id, "name": s.name, "work_hours": s.work_hours, "is_active": s.is_active}


@router.get("/staff")
def list_staff(ctx: Ctx = Depends(require_salon), db: Session = Depends(get_db)):
    rows = db.scalars(select(Staff).where(Staff.salon_id == ctx.salon_id)
                      .order_by(Staff.id)).all()
    return {"items": [_staff_dto(s) for s in rows]}


class StaffIn(BaseModel):
    name: str
    work_hours: dict | None = None
    is_active: bool = True


@router.post("/staff")
def create_staff(body: StaffIn, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    staff = Staff(salon_id=ctx.salon_id, **body.model_dump())
    db.add(staff)
    db.flush()
    audit(db, ctx, "create", "staff", staff.id, after=_staff_dto(staff))
    db.commit()
    return _staff_dto(staff)


class StaffPatchIn(BaseModel):
    name: str | None = None
    work_hours: dict | None = None
    is_active: bool | None = None


@router.patch("/staff/{staff_id}")
def patch_staff(staff_id: int, body: StaffPatchIn,
                ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    staff = get_owned_or_404(db, Staff, staff_id, ctx.salon_id)
    before = _staff_dto(staff)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(staff, field, value)
    audit(db, ctx, "update", "staff", staff.id, before=before, after=_staff_dto(staff))
    db.commit()
    return _staff_dto(staff)


@router.delete("/staff/{staff_id}")
def delete_staff(staff_id: int, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    staff = get_owned_or_404(db, Staff, staff_id, ctx.salon_id)
    staff.is_active = False
    audit(db, ctx, "deactivate", "staff", staff.id)
    db.commit()
    return {"ok": True}


# ── Тестовое напоминание себе (шаг 4 онбординг-мастера) ───────────────────
@router.post("/test-reminder")
def test_reminder(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    salon = db.get(Salon, ctx.salon_id)
    if not salon.tg_bot_token:
        raise HTTPException(400, "У салона не настроен Telegram-бот — обратитесь в поддержку")
    if not salon.admin_tg_chat_id:
        raise HTTPException(400, "Сначала напишите вашему боту команду /admin — "
                                 "так он узнает, куда слать служебные сообщения")
    template = salon.texts.get("reminder_24h", "")
    text = (template
            .replace("{имя}", "Анна")
            .replace("{дата}", "12 сентября")
            .replace("{время}", "14:00")
            .replace("{услуга}", "Маникюр с покрытием")
            .replace("{мастер}", "Мария")
            .replace("{салон}", salon.name))
    import telebot
    try:
        bot = telebot.TeleBot(salon.tg_bot_token, threaded=False)
        bot.send_message(salon.admin_tg_chat_id,
                         "🔔 Так увидит напоминание ваш клиент:\n\n" + text)
    except Exception as e:
        raise HTTPException(502, f"Не удалось отправить: {e}")
    audit(db, ctx, "test_reminder", "salon", salon.id)
    db.commit()
    return {"ok": True, "preview": text}
