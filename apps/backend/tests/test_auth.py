import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.auth import make_invite_token
from app.models import AuditLog, User
from tests.conftest import PASSWORD, login, make_user


def test_login_logout_me(db, client, salon_a):
    owner = make_user(db, salon_a)
    login(client, owner)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["salon"]["name"] == salon_a.name
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password(db, client, salon_a):
    owner = make_user(db, salon_a)
    r = client.post("/api/auth/login",
                    json={"email": owner.email, "password": "wrong_password"})
    assert r.status_code == 401


def test_login_rate_limit(db, client, salon_a):
    owner = make_user(db, salon_a)
    for _ in range(10):
        client.post("/api/auth/login",
                    json={"email": owner.email, "password": "wrong_password"})
    r = client.post("/api/auth/login",
                    json={"email": owner.email, "password": PASSWORD})
    assert r.status_code == 429


def test_login_is_audited(db, client, salon_a):
    owner = make_user(db, salon_a)
    login(client, owner)
    rows = db.scalars(select(AuditLog).where(
        AuditLog.action == "login", AuditLog.salon_id == salon_a.id)).all()
    assert rows


def test_accept_invite(db, client, salon_a):
    token, token_hash, expires = make_invite_token()
    user = User(salon_id=salon_a.id, email=f"inv-{uuid.uuid4().hex[:8]}@test.ru",
                pass_hash=None, role="owner",
                invite_token_hash=token_hash, invite_expires_at=expires)
    db.add(user)
    db.flush()
    r = client.post("/api/auth/accept-invite",
                    json={"token": token, "password": "new_password_1"})
    assert r.status_code == 200
    assert r.json()["salon"]["id"] == salon_a.id
    # токен одноразовый
    r = client.post("/api/auth/accept-invite",
                    json={"token": token, "password": "new_password_1"})
    assert r.status_code == 404


def test_expired_invite(db, client, salon_a):
    token, token_hash, _ = make_invite_token()
    user = User(salon_id=salon_a.id, email=f"inv-{uuid.uuid4().hex[:8]}@test.ru",
                pass_hash=None, role="owner", invite_token_hash=token_hash,
                invite_expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    db.add(user)
    db.flush()
    r = client.post("/api/auth/accept-invite",
                    json={"token": token, "password": "new_password_1"})
    assert r.status_code == 410
