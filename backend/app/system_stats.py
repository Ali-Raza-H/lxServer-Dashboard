from __future__ import annotations

import os
import platform
import time
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.deps import require_user
from app.models import SystemStatsResponse


router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(require_user)])


@router.get("/system", response_model=SystemStatsResponse)
def system_stats(settings: Settings = Depends(get_settings)) -> SystemStatsResponse:
    cpu_percent = float(psutil.cpu_percent(interval=0.15))

    if hasattr(os, "getloadavg"):
        load_avg = [float(x) for x in os.getloadavg()]  # type: ignore[attr-defined]
    else:
        load_avg = [0.0, 0.0, 0.0]

    mem = psutil.virtual_memory()
    mem_total = int(mem.total)
    mem_used = int(mem.used)

    disk_path = str(settings.dev_root) if settings.dev_root.exists() else str(Path(settings.dev_root.anchor or "/"))
    disk = psutil.disk_usage(disk_path)
    disk_total = int(disk.total)
    disk_used = int(disk.used)

    uptime_seconds = int(time.time() - psutil.boot_time())
    hostname = platform.node()
    local_time_iso = datetime.now().astimezone().isoformat()

    return SystemStatsResponse(
        cpu_percent=cpu_percent,
        load_avg=load_avg,
        mem_total=mem_total,
        mem_used=mem_used,
        disk_total=disk_total,
        disk_used=disk_used,
        uptime_seconds=uptime_seconds,
        hostname=hostname,
        local_time_iso=local_time_iso,
    )

