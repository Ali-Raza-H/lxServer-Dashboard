from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _expand_path(value: str) -> Path:
    expanded = os.path.expandvars(value)
    return Path(expanded).expanduser().resolve(strict=False)


@dataclass(frozen=True, slots=True)
class Settings:
    dev_root: Path
    logs_dir: Path
    auth_db_path: Path
    host: str
    port: int
    secret_key: str
    cookie_name: str
    cookie_secure: bool
    session_ttl_seconds: int
    dashboard_root: Path
    frontend_dir: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env", override=False)
    load_dotenv(override=False)

    dashboard_root = Path(__file__).resolve().parents[2]
    frontend_dir = dashboard_root / "frontend"

    dev_root = _expand_path(os.environ.get("DEV_ROOT", "~/Desktop/Devs"))
    logs_dir = _expand_path(os.environ.get("DASHBOARD_LOGS", "~/Desktop/Devs/dashboard_logs"))
    auth_db_path = _expand_path(os.environ.get("AUTH_DB", "~/.local/share/homelab-dashboard/auth.db"))

    host = os.environ.get("HOST", "0.0.0.0")
    port = _parse_int(os.environ.get("PORT"), 8080)

    cookie_name = os.environ.get("COOKIE_NAME", "homelab_dashboard_session")
    cookie_secure = _parse_bool(os.environ.get("COOKIE_SECURE"), False)
    session_ttl_seconds = _parse_int(os.environ.get("SESSION_TTL_SECONDS"), 60 * 60 * 24 * 7)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_urlsafe(48)
        print(
            "WARNING: SECRET_KEY is not set. Using an ephemeral key for this process "
            "(sessions will be invalidated on restart). Set SECRET_KEY in your .env.",
            file=sys.stderr,
        )

    auth_db_path.parent.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        dev_root=dev_root,
        logs_dir=logs_dir,
        auth_db_path=auth_db_path,
        host=host,
        port=port,
        secret_key=secret_key,
        cookie_name=cookie_name,
        cookie_secure=cookie_secure,
        session_ttl_seconds=session_ttl_seconds,
        dashboard_root=dashboard_root,
        frontend_dir=frontend_dir,
    )
