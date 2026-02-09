from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CmdResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


def run_subprocess(
    cmd: Sequence[str],
    *,
    cwd: Path,
    timeout_sec: float,
    env: Mapping[str, str] | None = None,
) -> CmdResult:
    start = time.monotonic()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    try:
        completed = subprocess.run(
            list(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            env=merged_env,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return CmdResult(
            exit_code=int(completed.returncode),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        stderr = ""
        if e.stderr:
            if isinstance(e.stderr, (bytes, bytearray)):
                stderr = e.stderr.decode("utf-8", errors="replace")
            else:
                stderr = str(e.stderr)
        return CmdResult(
            exit_code=124,
            stdout="",
            stderr=f"Command timed out after {timeout_sec}s. {stderr}".strip(),
            duration_ms=duration_ms,
        )
    except FileNotFoundError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        return CmdResult(exit_code=127, stdout="", stderr=str(e), duration_ms=duration_ms)


def tail_lines(path: Path, line_count: int) -> list[str]:
    if line_count <= 0:
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    lines = content.splitlines()
    return lines[-line_count:]


_PROJECT_ID_RE = re.compile(r"^[a-f0-9]{40}$")


def project_log_path(logs_dir: Path, project_id: str) -> Path:
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise ValueError("Invalid project id")
    return logs_dir / f"{project_id}.log"


def list_top_level_entries(project_dir: Path) -> list[dict]:
    entries: list[dict] = []
    try:
        for child in project_dir.iterdir():
            name = child.name
            if name.startswith("."):
                continue
            try:
                stat = child.stat()
            except OSError:
                continue
            entries.append(
                {
                    "name": name,
                    "is_dir": child.is_dir(),
                    "size": int(stat.st_size),
                }
            )
    except FileNotFoundError:
        return []

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries

