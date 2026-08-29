"""Изоляция тенантов: salon_id берётся ТОЛЬКО из сессии, никогда из запроса.

Чужой объект отдаём как 404, не 403 — не подтверждаем существование
(docs/10-crm-logic.md).
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, get_session
from app.db import get_db
from app.models import SessionRow, User


@dataclass
class Ctx:
    user: User
    session: SessionRow
    role: str            # роль пользователя как есть
    salon_id: int | None  # эффективный салон (у superadmin — из режима поддержки)
    is_support: bool     # superadmin работает в чужом салоне


def get_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Не авторизован")
    session = get_session(db, token)
    if session is None:
        raise HTTPException(401, "Сессия истекла")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Пользователь не активен")
    is_support = user.role == "superadmin" and session.acting_salon_id is not None
    salon_id = user.salon_id if user.role != "superadmin" else session.acting_salon_id
    return Ctx(user=user, session=session, role=user.role, salon_id=salon_id, is_support=is_support)


def require_salon(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    """Доступ к данным салона: owner, staff или superadmin в режиме поддержки."""
    if ctx.salon_id is None:
        raise HTTPException(403, "Нет доступа к данным салона")
    return ctx


def require_owner(ctx: Ctx = Depends(require_salon)) -> Ctx:
    """Настройки/отчёты: только owner (staff их не видит) или поддержка."""
    if ctx.role == "staff":
        raise HTTPException(403, "Недостаточно прав")
    return ctx


def require_superadmin(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    if ctx.role != "superadmin":
        raise HTTPException(403, "Недостаточно прав")
    return ctx


def get_owned_or_404(db: Session, model, obj_id: int, salon_id: int):
    obj = db.get(model, obj_id)
    if obj is None or obj.salon_id != salon_id:
        raise HTTPException(404, "Не найдено")
    return obj
