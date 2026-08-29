from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import Ctx, require_owner
from app.models import Salon, Service

router = APIRouter()


class StepIn(BaseModel):
    step: int  # 1..4 — пройденный шаг мастера


@router.post("/step")
def save_step(body: StepIn, ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    salon = db.get(Salon, ctx.salon_id)
    if not 1 <= body.step <= 4:
        raise HTTPException(422, "Шаг от 1 до 4")
    salon.onboarding_step = max(salon.onboarding_step, body.step)
    db.commit()
    return {"onboarding_step": salon.onboarding_step}


@router.post("/complete")
def complete(ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db)):
    """Мастер пройден → салон активен, рассылки включаются."""
    salon = db.get(Salon, ctx.salon_id)
    if salon.status != "onboarding":
        return {"status": salon.status}
    services_count = db.scalar(select(func.count(Service.id)).where(
        Service.salon_id == salon.id, Service.is_active.is_(True))) or 0
    if services_count == 0:
        raise HTTPException(422, "Добавьте хотя бы одну услугу, прежде чем завершить настройку")
    salon.status = "active"
    salon.onboarding_step = 4
    audit(db, ctx, "status_change", "salon", salon.id,
          before={"status": "onboarding"}, after={"status": "active"})
    db.commit()
    return {"status": salon.status}
