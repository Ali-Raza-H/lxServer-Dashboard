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


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


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
    enable_web_terminal: bool
    terminal_allowed_users: frozenset[str]
    terminal_shell: str
    terminal_max_sessions_per_user: int
    terminal_max_sessions_total: int
    terminal_idle_timeout_seconds: int
    terminal_allowed_origins: tuple[str, ...]


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

    enable_web_terminal = _parse_bool(os.environ.get("ENABLE_WEB_TERMINAL"), False)
    terminal_allowed_users = frozenset({u.lower() for u in _parse_csv(os.environ.get("TERMINAL_ALLOWED_USERS"))})
    if os.name == "nt":
        default_shell = os.environ.get("COMSPEC", "cmd.exe")
    else:
        default_shell = "/bin/bash"
    terminal_shell = os.environ.get("TERMINAL_SHELL", default_shell).strip() or default_shell
    terminal_max_sessions_per_user = _parse_int(os.environ.get("TERMINAL_MAX_SESSIONS_PER_USER"), 2)
    terminal_max_sessions_total = _parse_int(os.environ.get("TERMINAL_MAX_SESSIONS_TOTAL"), 10)
    terminal_idle_timeout_seconds = _parse_int(os.environ.get("TERMINAL_IDLE_TIMEOUT_SECONDS"), 1800)
    terminal_allowed_origins = tuple(_parse_csv(os.environ.get("TERMINAL_ALLOWED_ORIGINS")))

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
        enable_web_terminal=enable_web_terminal,
        terminal_allowed_users=terminal_allowed_users,
        terminal_shell=terminal_shell,
        terminal_max_sessions_per_user=max(1, terminal_max_sessions_per_user),
        terminal_max_sessions_total=max(1, terminal_max_sessions_total),
        terminal_idle_timeout_seconds=max(30, terminal_idle_timeout_seconds),
        terminal_allowed_origins=terminal_allowed_origins,
    )
