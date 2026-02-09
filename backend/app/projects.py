from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.deps import require_user
from app.models import ProjectInfo, ProjectType
from app.utils import run_subprocess


_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}


@dataclass(frozen=True, slots=True)
class ResolvedProject:
    id: str
    name: str
    rel_path: str
    abs_path: Path
    is_git: bool


router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_user)])


def project_id_from_relpath(rel_path: str) -> str:
    return hashlib.sha1(rel_path.encode("utf-8")).hexdigest()


def _detect_type(project_dir: Path) -> ProjectType:
    if (project_dir / "pyproject.toml").exists() or (project_dir / "requirements.txt").exists() or (project_dir / "setup.py").exists():
        return "python"
    if (project_dir / "package.json").exists():
        return "node"
    return "other"


def _project_last_modified_iso(project_dir: Path) -> str:
    try:
        mtime = project_dir.stat().st_mtime
        for child in project_dir.iterdir():
            try:
                mtime = max(mtime, child.stat().st_mtime)
            except OSError:
                continue
        return datetime.fromtimestamp(mtime).astimezone().isoformat()
    except FileNotFoundError:
        return datetime.now().astimezone().isoformat()


def _git_branch(project_dir: Path) -> str | None:
    res = run_subprocess(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=project_dir, timeout_sec=2.0, env=_GIT_ENV)
    if res.exit_code != 0:
        return None
    branch = res.stdout.strip()
    return branch or None


def _git_dirty(project_dir: Path) -> bool:
    res = run_subprocess(["git", "status", "--porcelain"], cwd=project_dir, timeout_sec=2.0, env=_GIT_ENV)
    return bool(res.stdout.strip())


def iter_projects(settings: Settings) -> list[ResolvedProject]:
    dev_root = settings.dev_root
    dashboard_root = settings.dashboard_root.resolve()
    dev_root_resolved = dev_root.resolve(strict=False)
    logs_dir_resolved = settings.logs_dir.resolve(strict=False)

    if not dev_root.exists():
        return []

    resolved: list[ResolvedProject] = []
    for entry in dev_root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        try:
            entry_resolved = entry.resolve()
        except OSError:
            continue

        if not entry_resolved.is_relative_to(dev_root_resolved):
            continue
        if entry_resolved == dashboard_root:
            continue
        if entry_resolved == logs_dir_resolved:
            continue

        rel_path = entry.relative_to(dev_root).as_posix()
        proj_id = project_id_from_relpath(rel_path)
        is_git = (entry / ".git").exists()
        resolved.append(
            ResolvedProject(
                id=proj_id,
                name=entry.name,
                rel_path=rel_path,
                abs_path=entry,
                is_git=is_git,
            )
        )

    resolved.sort(key=lambda p: p.name.lower())
    return resolved


def scan_projects(settings: Settings) -> list[ProjectInfo]:
    projects: list[ProjectInfo] = []
    for proj in iter_projects(settings):
        branch = _git_branch(proj.abs_path) if proj.is_git else None
        dirty = _git_dirty(proj.abs_path) if proj.is_git else False
        projects.append(
            ProjectInfo(
                id=proj.id,
                name=proj.name,
                path=proj.rel_path,
                is_git=proj.is_git,
                git_branch=branch,
                git_dirty=dirty,
                detected_type=_detect_type(proj.abs_path),
                last_modified=_project_last_modified_iso(proj.abs_path),
            )
        )
    return projects


def resolve_project(settings: Settings, project_id: str) -> ResolvedProject | None:
    for proj in iter_projects(settings):
        if proj.id == project_id:
            return proj
    return None


@router.get("", response_model=list[ProjectInfo])
def list_projects(settings: Settings = Depends(get_settings)) -> list[ProjectInfo]:
    return scan_projects(settings)
