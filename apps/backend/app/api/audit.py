from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.dto import audit_dto
from app.db import get_db
from app.deps import Ctx, require_owner
from app.models import AuditLog

router = APIRouter()


@router.get("")
def list_audit(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require_owner), db: Session = Depends(get_db),
):
    """Журнал изменений салона; действия поддержки видны с пометкой."""
    q = select(AuditLog).where(AuditLog.salon_id == ctx.salon_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.options(joinedload(AuditLog.user)).order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [audit_dto(a) for a in rows], "total": total, "page": page}
