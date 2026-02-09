from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.deps import require_user
from app.logs import append_project_log_line
from app.models import ActionRequest, ActionResult, FileEntry
from app.projects import ResolvedProject, resolve_project
from app.utils import CmdResult, list_top_level_entries, run_subprocess


router = APIRouter(prefix="/api/projects", tags=["actions"], dependencies=[Depends(require_user)])

_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}


def _fmt_files(entries: list[dict]) -> str:
    if not entries:
        return "(no files)"
    lines: list[str] = []
    for e in entries:
        kind = "DIR " if e["is_dir"] else "FILE"
        lines.append(f"{kind} {e['name']} ({e['size']} bytes)")
    return "\n".join(lines)


def _run_git_cmd(project_dir: Path, cmd: list[str], timeout_sec: float) -> CmdResult:
    return run_subprocess(cmd, cwd=project_dir, timeout_sec=timeout_sec, env=_GIT_ENV)


def _run_action_sync(project: ResolvedProject, action: str) -> ActionResult:
    if action == "git_status":
        if not project.is_git:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a git repository")
        res = _run_git_cmd(project.abs_path, ["git", "status", "-sb"], timeout_sec=10.0)
        return ActionResult(exit_code=res.exit_code, stdout=res.stdout, stderr=res.stderr, duration_ms=res.duration_ms)

    if action == "git_pull":
        if not project.is_git:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a git repository")
        res = _run_git_cmd(project.abs_path, ["git", "pull", "--ff-only"], timeout_sec=60.0)
        return ActionResult(exit_code=res.exit_code, stdout=res.stdout, stderr=res.stderr, duration_ms=res.duration_ms)

    if action == "list_files":
        start = time.monotonic()
        entries = list_top_level_entries(project.abs_path)
        duration_ms = int((time.monotonic() - start) * 1000)
        files = [FileEntry(name=e["name"], is_dir=bool(e["is_dir"]), size=int(e["size"])) for e in entries]
        return ActionResult(exit_code=0, stdout=_fmt_files(entries), stderr="", duration_ms=duration_ms, files=files)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown action")


@router.post("/{project_id}/action", response_model=ActionResult)
async def run_action(project_id: str, payload: ActionRequest, settings: Settings = Depends(get_settings)) -> ActionResult:
    project = resolve_project(settings, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = await asyncio.to_thread(_run_action_sync, project, payload.action)

    append_project_log_line(
        settings=settings,
        project_id=project_id,
        line=f"{datetime.now().astimezone().isoformat()} action={payload.action} exit={result.exit_code} dur_ms={result.duration_ms}",
    )
    return result

