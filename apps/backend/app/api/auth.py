from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    hash_password,
    invite_hash,
    login_allowed,
    register_attempt,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.deps import Ctx, get_ctx
from app.models import Salon, User

router = APIRouter()


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=settings.session_ttl_days * 86400, path="/",
    )


def _me_payload(db: Session, user: User, acting_salon_id: int | None) -> dict:
    salon_id = user.salon_id if user.role != "superadmin" else acting_salon_id
    salon = db.get(Salon, salon_id) if salon_id else None
    return {
        "user": {"id": user.id, "email": user.email, "role": user.role},
        "salon": {
            "id": salon.id, "name": salon.name, "status": salon.status,
            "onboarding_step": salon.onboarding_step, "timezone": salon.timezone,
        } if salon else None,
        "is_support": user.role == "superadmin" and acting_salon_id is not None,
    }


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    key = f"{ip}:{body.email.lower()}"
    if not login_allowed(key):
        raise HTTPException(429, "Слишком много попыток, попробуйте позже")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active or not user.pass_hash \
            or not verify_password(user.pass_hash, body.password):
        register_attempt(key)
        raise HTTPException(401, "Неверный email или пароль")
    token = create_session(db, user, ip, request.headers.get("user-agent"))
    # входы в кабинет логируются: единственный источник правды при спорах
    audit(db, None, "login", "user", user.id, salon_id=user.salon_id, ip=ip)
    db.commit()
    _set_cookie(response, token)
    return _me_payload(db, user, None)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        delete_session(db, token)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return _me_payload(db, ctx.user, ctx.session.acting_salon_id)


class AcceptInviteIn(BaseModel):
    token: str
    password: str


@router.post("/accept-invite")
def accept_invite(body: AcceptInviteIn, request: Request, response: Response,
                  db: Session = Depends(get_db)):
    if len(body.password) < 8:
        raise HTTPException(422, "Пароль должен быть не короче 8 символов")
    user = db.scalar(select(User).where(User.invite_token_hash == invite_hash(body.token)))
    if user is None:
        raise HTTPException(404, "Приглашение не найдено")
    if user.invite_expires_at is None or user.invite_expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Срок действия приглашения истёк — запросите новое")
    user.pass_hash = hash_password(body.password)
    user.invite_token_hash = None
    user.invite_expires_at = None
    ip = request.client.host if request.client else None
    token = create_session(db, user, ip, request.headers.get("user-agent"))
    audit(db, None, "accept_invite", "user", user.id, salon_id=user.salon_id, ip=ip)
    db.commit()
    _set_cookie(response, token)
    return _me_payload(db, user, None)
