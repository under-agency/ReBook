from sqlalchemy.orm import Session

from app.deps import Ctx
from app.models import AuditLog


def audit(
    db: Session,
    ctx: Ctx | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    salon_id: int | None = None,
    ip: str | None = None,
) -> None:
    db.add(AuditLog(
        salon_id=salon_id if salon_id is not None else (ctx.salon_id if ctx else None),
        user_id=ctx.user.id if ctx else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before,
        after=after,
        is_support=ctx.is_support if ctx else False,
        ip=ip if ip is not None else (ctx.session.ip if ctx else None),
    ))
