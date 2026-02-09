from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.actions import router as actions_router
from app.auth import router as auth_router
from app.config import get_settings
from app.logs import router as logs_router
from app.logs import ws_router as logs_ws_router
from app.models import AuthDB, HealthResponse
from app.projects import router as projects_router
from app.system_stats import router as system_router
from app.terminal import router as terminal_router
from app.terminal import ws_router as terminal_ws_router


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        db = AuthDB(settings.auth_db_path)
        db.init()
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="Homelab Control Dashboard", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(ok=True)

    frontend_dir: Path = settings.frontend_dir

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    @app.get("/login.html", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(frontend_dir / "login.html")

    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(actions_router)
    app.include_router(logs_router)
    app.include_router(system_router)
    app.include_router(logs_ws_router)
    app.include_router(terminal_router)
    app.include_router(terminal_ws_router)

    app.mount("/", StaticFiles(directory=str(frontend_dir), html=False), name="frontend")
    return app


app = create_app()
