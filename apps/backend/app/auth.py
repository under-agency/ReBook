import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SessionRow, User

_ph = PasswordHasher()

SESSION_COOKIE = "rebook_session"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(pass_hash: str, password: str) -> bool:
    try:
        return _ph.verify(pass_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: Session, user: User, ip: str | None = None, user_agent: str | None = None
) -> str:
    token = secrets.token_urlsafe(32)
    row = SessionRow(
        token_hash=_token_hash(token),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(row)
    return token


def get_session(db: Session, token: str) -> SessionRow | None:
    row = db.get(SessionRow, _token_hash(token))
    if row is None or row.expires_at < datetime.now(timezone.utc):
        return None
    return row


def delete_session(db: Session, token: str) -> None:
    row = db.get(SessionRow, _token_hash(token))
    if row is not None:
        db.delete(row)


def make_invite_token() -> tuple[str, str, datetime]:
    """() -> (token, token_hash, expires_at)"""
    token = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.invite_ttl_hours)
    return token, _token_hash(token), expires


def invite_hash(token: str) -> str:
    return _token_hash(token)


# ── Rate-limit логина (in-memory, на процесс) ─────────────────────────────
_attempts: dict[str, list[float]] = {}
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SEC = 300


def login_allowed(key: str) -> bool:
    now = time.monotonic()
    window = [t for t in _attempts.get(key, []) if now - t < LOGIN_WINDOW_SEC]
    _attempts[key] = window
    return len(window) < LOGIN_MAX_ATTEMPTS


def register_attempt(key: str) -> None:
    _attempts.setdefault(key, []).append(time.monotonic())
