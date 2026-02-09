from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.config import Settings, get_settings
from app.deps import get_auth_db, require_user, require_user_ws
from app.models import AuthDB, LogsResponse
from app.projects import resolve_project
from app.utils import project_log_path, tail_lines


router = APIRouter(prefix="/api/projects", tags=["logs"], dependencies=[Depends(require_user)])
ws_router = APIRouter(tags=["logs"])


def append_project_log_line(*, settings: Settings, project_id: str, line: str) -> None:
    log_path = project_log_path(settings.logs_dir, project_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line.replace("\n", "\\n") + "\n")


@router.get("/{project_id}/logs", response_model=LogsResponse)
def get_logs(project_id: str, lines: int = 200, settings: Settings = Depends(get_settings)) -> LogsResponse:
    if resolve_project(settings, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    safe_lines = max(1, min(int(lines), 2000))
    log_path = project_log_path(settings.logs_dir, project_id)
    return LogsResponse(lines=tail_lines(log_path, safe_lines))


@ws_router.websocket("/ws/projects/{project_id}/logs")
async def logs_ws(websocket: WebSocket, project_id: str) -> None:
    settings = get_settings()
    db: AuthDB = get_auth_db(settings)

    if resolve_project(settings, project_id) is None:
        await websocket.close(code=4404)
        return

    user = require_user_ws(websocket, settings, db)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()

    log_path = project_log_path(settings.logs_dir, project_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)

    init_lines = tail_lines(log_path, 200)
    await websocket.send_json({"type": "init", "lines": init_lines, "username": user.username})

    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    await websocket.send_json({"type": "line", "line": line.rstrip("\n")})
                else:
                    await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return

