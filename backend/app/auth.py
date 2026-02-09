from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config import Settings, get_settings
from app.deps import get_auth_db, require_user
from app.models import AuthDB, LoginRequest, LoginResponse, User
from app.security import (
    build_session_cookie,
    extract_and_verify_session_cookie,
    new_session_token,
    sha256_hex,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    db: AuthDB = Depends(get_auth_db),
) -> LoginResponse:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username required")

    record = db.get_user_record_by_username(username)
    if record is None or not verify_password(payload.password, record.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = new_session_token()
    token_hash = sha256_hex(token)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
    db.create_session(token_hash=token_hash, user_id=record.id, expires_at=expires_at)

    cookie_value = build_session_cookie(token, settings.secret_key)
    response.set_cookie(
        key=settings.cookie_name,
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return LoginResponse(ok=True, username=record.username)


@router.post("/logout", response_model=dict)
def logout(
    request: Request,
    response: Response,
    _user: User = Depends(require_user),
    settings: Settings = Depends(get_settings),
    db: AuthDB = Depends(get_auth_db),
) -> dict:
    cookie_value = request.cookies.get(settings.cookie_name)
    if cookie_value:
        token = extract_and_verify_session_cookie(cookie_value, settings.secret_key)
        if token:
            db.delete_session(sha256_hex(token))

    response.delete_cookie(key=settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=dict)
def me(user: User = Depends(require_user)) -> dict:
    return {"ok": True, "username": user.username}

