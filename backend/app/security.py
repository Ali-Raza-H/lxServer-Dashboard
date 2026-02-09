from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Final

import bcrypt


_SIGN_SEP: Final[str] = "."


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _signature(value: str, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def build_session_cookie(token: str, secret_key: str) -> str:
    sig = _signature(token, secret_key)
    return f"{token}{_SIGN_SEP}{sig}"


def extract_and_verify_session_cookie(cookie_value: str, secret_key: str) -> str | None:
    if not cookie_value:
        return None
    token, sep, sig = cookie_value.rpartition(_SIGN_SEP)
    if not sep or not token or not sig:
        return None
    expected = _signature(token, secret_key)
    if not hmac.compare_digest(expected, sig):
        return None
    return token

