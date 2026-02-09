# Homelab Control Dashboard

A lightweight, self-hosted web dashboard for browsing projects in your homelab **devs root** and running **safe, predefined actions** (no arbitrary command execution from user input).

- Backend: Python 3.12 + FastAPI + Uvicorn
- Frontend: plain HTML/CSS/vanilla JS (served by the backend)
- Auth: username/password (bcrypt) + server-side sessions in SQLite
- Extras: system stats (psutil), per-project logs (tail + WebSocket streaming)

## Repo layout

- `backend/app/` - FastAPI app code
- `backend/tests/` - pytest tests
- `frontend/` - static UI (served by the backend)
- `scripts/` - dev + admin scripts
- `systemd/` - systemd unit template

## Quickstart (Linux Mint)

From the repo root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set SECRET_KEY to a long random value

python ../scripts/init_db.py
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Open:

- Dashboard: `http://localhost:8080/`
- Login page: `http://localhost:8080/login.html`

## Windows development (PowerShell)

From the repo root:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env

python ..\scripts\init_db.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Or use the convenience script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1
```

## Configuration

Configuration is via environment variables (use `backend/.env.example` as a template). Important ones:

- `DEV_ROOT` (default: `~/Desktop/Devs`) - folder containing your project folders (direct children only)
- `DASHBOARD_LOGS` (default: `~/Desktop/Devs/dashboard_logs`) - per-project log files written here
- `AUTH_DB` (default: `~/.local/share/homelab-dashboard/auth.db`) - SQLite auth DB (outside the repo by default)
- `SECRET_KEY` - required for stable sessions (if missing, the backend generates an ephemeral key with a warning)
- `HOST` / `PORT` - server bind
- `COOKIE_SECURE` - set `true` when behind HTTPS

## Auth / first admin user

Create the first user:

```bash
python scripts/init_db.py
```

You can set:

- `ADMIN_USER`
- `ADMIN_PASS`

...or the script will prompt interactively.

## What the dashboard does

### Projects list

`GET /api/projects` scans `DEV_ROOT` and returns:

- `name`, `path` (relative), `id` (sha1 of relative path)
- git info (`is_git`, `git_branch`, `git_dirty`)
- `detected_type` (`python` / `node` / `other`)
- `last_modified`

Rules:

- Hidden folders are ignored
- The dashboard repo itself is ignored (if it lives inside `DEV_ROOT`)
- If `DASHBOARD_LOGS` is inside `DEV_ROOT`, it is ignored from the projects list
- Symlinked entries that resolve outside `DEV_ROOT` are ignored

### Safe actions (allowlist)

`POST /api/projects/{project_id}/action` supports:

- `git_status` (runs `git status -sb`)
- `git_pull` (runs `git pull --ff-only`)
- `list_files` (top-level only; excludes hidden; includes size + dir flag)

Implementation notes:

- No user-provided command strings
- Subprocess is invoked with explicit argument arrays, `cwd` pinned to the project, and timeouts
- `GIT_TERMINAL_PROMPT=0` disables interactive git prompts

### Logs

- Each action appends a line to a per-project log file in `DASHBOARD_LOGS`
- Tail: `GET /api/projects/{project_id}/logs?lines=200`
- Live: `WS /ws/projects/{project_id}/logs`

### Web terminal (experimental)

This feature opens an **interactive shell** on the server via WebSocket + PTY. It is **disabled by default**.

- Capability: `GET /api/terminal`
- WebSocket: `WS /ws/projects/{project_id}/terminal` (starts in the project directory)
- UI: vendored xterm.js (`frontend/vendor/xterm/`, currently v5.3.0)

To enable (in `backend/.env`):

- `ENABLE_WEB_TERMINAL=true`
- `TERMINAL_ALLOWED_USERS=admin` (recommended, comma-separated)

### System stats

`GET /api/system` returns: CPU, load average, RAM, disk usage, uptime, hostname, and local time.

## Tests

```bash
cd backend
python -m pytest
```

## Deployment (systemd)

Use `systemd/homelab-dashboard.service` as a template:

1. Clone this repo onto the homelab machine
2. Create `backend/.venv` and install `backend/requirements.txt`
3. Copy `backend/.env.example` to `backend/.env` and set `SECRET_KEY`
4. Edit the service file placeholders (`User`, `WorkingDirectory`, `EnvironmentFile`, `ExecStart`)

Then:

```bash
sudo cp systemd/homelab-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-dashboard
```

## Security notes (read this)

- Treat this as a **LAN/VPN-only** app (e.g. behind Tailscale). Do not expose it publicly as-is.
- For HTTPS deployments, put it behind a reverse proxy and set `COOKIE_SECURE=true`.
- The API is intentionally allowlisted: it does **not** execute arbitrary commands from user input.
- The experimental web terminal is **equivalent to remote shell access** as the service user. Enable it only if you fully understand the risk.

## Troubleshooting

- **401 redirects to login**: make sure you ran `python scripts/init_db.py` and are logging in with that user.
- **Windows + OneDrive warnings during tests**: OneDrive/permissions can block pytest's cache writes; the test run should still pass.
