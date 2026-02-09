from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, WebSocket

from app.config import Settings, get_settings
from app.deps import get_auth_db, require_user, require_user_ws
from app.logs import append_project_log_line
from app.models import AuthDB, User
from app.projects import resolve_project


router = APIRouter(prefix="/api", tags=["terminal"], dependencies=[Depends(require_user)])
ws_router = APIRouter(tags=["terminal"])


def _terminal_supported() -> bool:
    if os.name != "posix":
        return False
    try:
        import pty  # noqa: F401
        import termios  # noqa: F401
        import fcntl  # noqa: F401
        import struct  # noqa: F401
        import signal  # noqa: F401
    except Exception:
        return False
    return True


def _user_allowed(settings: Settings, user: User) -> bool:
    if not settings.enable_web_terminal:
        return False
    if not _terminal_supported():
        return False
    if not settings.terminal_allowed_users:
        return True
    return user.username.lower() in settings.terminal_allowed_users


def _split_host_port(value: str) -> tuple[str, int | None]:
    raw = (value or "").strip()
    if not raw:
        return "", None
    if raw.startswith("["):
        end = raw.find("]")
        if end == -1:
            return raw, None
        host = raw[1:end]
        rest = raw[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None

    if ":" in raw:
        host, _, port_str = raw.rpartition(":")
        if host and port_str.isdigit():
            return host, int(port_str)
    return raw, None


def _origin_allowed(*, websocket: WebSocket, settings: Settings) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    origin = origin.strip()

    if settings.terminal_allowed_origins:
        return origin in settings.terminal_allowed_origins

    host_header = websocket.headers.get("host") or ""
    parsed = urlparse(origin)
    if not parsed.hostname:
        return False

    origin_host = parsed.hostname
    origin_port = parsed.port
    if origin_port is None:
        origin_port = 443 if parsed.scheme == "https" else 80

    host_name, host_port = _split_host_port(host_header)
    if not host_name:
        return False
    if host_port is None:
        host_port = 443 if parsed.scheme == "https" else 80

    return origin_host.lower() == host_name.lower() and origin_port == host_port


def _shell_command(settings: Settings) -> list[str] | None:
    raw = settings.terminal_shell.strip()
    parts = shlex.split(raw, posix=True) if raw else []
    if not parts:
        parts = ["/bin/bash"]

    exe = parts[0]
    if "/" in exe:
        if Path(exe).exists():
            return parts
    else:
        resolved = shutil.which(exe)
        if resolved:
            parts[0] = resolved
            return parts

    for fallback in ("/bin/bash", "/bin/sh", "bash", "sh"):
        resolved = shutil.which(fallback) if "/" not in fallback else (fallback if Path(fallback).exists() else None)
        if resolved:
            return [resolved]
    return None


@dataclass(slots=True)
class _Limiter:
    lock: asyncio.Lock
    total: int
    per_user: dict[str, int]


_limiter = _Limiter(lock=asyncio.Lock(), total=0, per_user={})


async def _try_acquire(username: str, *, max_total: int, max_per_user: int) -> bool:
    async with _limiter.lock:
        if _limiter.total >= max_total:
            return False
        if _limiter.per_user.get(username, 0) >= max_per_user:
            return False
        _limiter.total += 1
        _limiter.per_user[username] = _limiter.per_user.get(username, 0) + 1
        return True


async def _release(username: str) -> None:
    async with _limiter.lock:
        _limiter.total = max(0, _limiter.total - 1)
        current = _limiter.per_user.get(username, 0)
        if current <= 1:
            _limiter.per_user.pop(username, None)
        else:
            _limiter.per_user[username] = current - 1


@router.get("/terminal", response_model=dict)
def terminal_capability(user: User = Depends(require_user), settings: Settings = Depends(get_settings)) -> dict:
    supported = _terminal_supported()
    enabled = supported and _user_allowed(settings, user)
    return {"supported": supported, "enabled": enabled}


def _set_winsize(fd: int, *, cols: int, rows: int) -> None:
    import fcntl  # posix-only
    import struct  # posix-only
    import termios  # posix-only

    safe_cols = max(10, min(int(cols), 400))
    safe_rows = max(5, min(int(rows), 200))
    winsz = struct.pack("HHHH", safe_rows, safe_cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsz)
    except OSError:
        return


def _spawn_pty(*, cmd: list[str], cwd: Path, initial_cols: int = 80, initial_rows: int = 24) -> tuple[subprocess.Popen[bytes], int]:
    import pty  # posix-only

    master_fd, slave_fd = pty.openpty()
    try:
        _set_winsize(slave_fd, cols=initial_cols, rows=initial_rows)
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(cwd),
                env=env,
                start_new_session=True,
            )
        except Exception:
            try:
                os.close(master_fd)
            except OSError:
                pass
            raise
        return proc, master_fd
    finally:
        try:
            os.close(slave_fd)
        except OSError:
            pass


async def _terminate_process(proc: subprocess.Popen[bytes], *, timeout_sec: float = 2.5) -> int:
    import signal  # posix-only

    if proc.poll() is not None:
        return int(proc.returncode or 0)

    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        pass

    try:
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=timeout_sec)
    except TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=timeout_sec)
        except TimeoutError:
            pass

    return int(proc.returncode or 0)


@ws_router.websocket("/ws/projects/{project_id}/terminal")
async def terminal_ws(websocket: WebSocket, project_id: str) -> None:
    settings = get_settings()

    if not settings.enable_web_terminal or not _terminal_supported():
        await websocket.close(code=4403)
        return

    if not _origin_allowed(websocket=websocket, settings=settings):
        await websocket.close(code=4403)
        return

    db: AuthDB = get_auth_db(settings)
    user = require_user_ws(websocket, settings, db)
    if user is None:
        await websocket.close(code=4401)
        return
    if not _user_allowed(settings, user):
        await websocket.close(code=4403)
        return

    project = resolve_project(settings, project_id)
    if project is None:
        await websocket.close(code=4404)
        return

    cmd = _shell_command(settings)
    if not cmd:
        await websocket.close(code=1011)
        return

    acquired = await _try_acquire(
        user.username,
        max_total=settings.terminal_max_sessions_total,
        max_per_user=settings.terminal_max_sessions_per_user,
    )
    if not acquired:
        await websocket.close(code=4429)
        return

    append_project_log_line(
        settings=settings,
        project_id=project_id,
        line=f"{datetime.now().astimezone().isoformat()} terminal start user={user.username}",
    )

    proc: subprocess.Popen[bytes] | None = None
    master_fd: int | None = None
    remove_reader: Any | None = None

    last_activity = time.monotonic()

    def bump_activity() -> None:
        nonlocal last_activity
        last_activity = time.monotonic()

    try:
        proc, master_fd = _spawn_pty(cmd=cmd, cwd=project.abs_path)
        os.set_blocking(master_fd, False)

        await websocket.accept()
        await websocket.send_json({"type": "ready", "project_id": project_id, "path": project.rel_path, "username": user.username})

        loop = asyncio.get_running_loop()
        q: asyncio.Queue[bytes | None] = asyncio.Queue()

        def _on_readable() -> None:
            if master_fd is None:
                return
            while True:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        q.put_nowait(None)
                        return
                    q.put_nowait(data)
                except BlockingIOError:
                    return
                except OSError:
                    q.put_nowait(None)
                    return

        loop.add_reader(master_fd, _on_readable)
        remove_reader = lambda: loop.remove_reader(master_fd)  # noqa: E731

        async def pty_to_ws() -> None:
            while True:
                data = await q.get()
                if data is None:
                    return
                bump_activity()
                await websocket.send_bytes(data)

        async def ws_to_pty() -> None:
            if master_fd is None:
                return
            while True:
                msg = await websocket.receive()
                msg_type = msg.get("type")
                if msg_type == "websocket.disconnect":
                    return

                if msg.get("bytes") is not None:
                    raw = msg["bytes"]
                    if raw:
                        bump_activity()
                        try:
                            os.write(master_fd, raw)
                        except OSError:
                            return
                    continue

                text = msg.get("text")
                if not text:
                    continue
                bump_activity()
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue

                if payload.get("type") == "resize":
                    try:
                        cols = int(payload.get("cols", 80))
                        rows = int(payload.get("rows", 24))
                    except (TypeError, ValueError):
                        continue
                    _set_winsize(master_fd, cols=cols, rows=rows)
                    continue

                if payload.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

        async def idle_watchdog() -> None:
            timeout = float(settings.terminal_idle_timeout_seconds)
            while True:
                await asyncio.sleep(1.0)
                if time.monotonic() - last_activity > timeout:
                    try:
                        await websocket.send_json({"type": "error", "message": "idle timeout"})
                    except Exception:
                        pass
                    try:
                        await websocket.close(code=4408)
                    except Exception:
                        pass
                    return

        tasks = [
            asyncio.create_task(pty_to_ws(), name="pty_to_ws"),
            asyncio.create_task(ws_to_pty(), name="ws_to_pty"),
            asyncio.create_task(idle_watchdog(), name="idle_watchdog"),
        ]
        _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        try:
            if remove_reader:
                remove_reader()
        except Exception:
            pass
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass
        exit_code = 0
        if proc is not None:
            try:
                exit_code = await _terminate_process(proc)
            except Exception:
                exit_code = int(proc.poll() or 0)

        append_project_log_line(
            settings=settings,
            project_id=project_id,
            line=f"{datetime.now().astimezone().isoformat()} terminal end user={user.username} exit={exit_code}",
        )
        await _release(user.username)
