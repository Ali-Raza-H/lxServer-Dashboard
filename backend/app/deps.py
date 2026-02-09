from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, WebSocket, status

from app.config import Settings, get_settings
from app.models import AuthDB, User
from app.security import extract_and_verify_session_cookie, sha256_hex


def get_auth_db(settings: Settings = Depends(get_settings)) -> AuthDB:
    db = AuthDB(settings.auth_db_path)
    db.init()
    return db


def require_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: AuthDB = Depends(get_auth_db),
) -> User:
    cookie_value = request.cookies.get(settings.cookie_name)
    if not cookie_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = extract_and_verify_session_cookie(cookie_value, settings.secret_key)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    token_hash = sha256_hex(token)
    user = db.get_user_by_session_token_hash(token_hash, now=datetime.now(timezone.utc))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    return user


def require_user_ws(websocket: WebSocket, settings: Settings, db: AuthDB) -> User | None:
    cookie_value = websocket.cookies.get(settings.cookie_name)
    if not cookie_value:
        return None
    token = extract_and_verify_session_cookie(cookie_value, settings.secret_key)
    if not token:
        return None
    token_hash = sha256_hex(token)
    return db.get_user_by_session_token_hash(token_hash, now=datetime.now(timezone.utc))

