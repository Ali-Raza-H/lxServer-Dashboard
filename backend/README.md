# Homelab Control Dashboard (v1)

A lightweight, self-hosted web dashboard for browsing projects in your homelab “devs root” and running **safe, predefined actions** (no arbitrary command execution).

## Features

- FastAPI backend (Python 3.12) + vanilla HTML/JS frontend (served by the backend)
- Username/password login (bcrypt hashes) + server-side sessions in SQLite
- Project discovery: scans `DEV_ROOT` and shows git status + basic project type detection
- Safe actions per project:
  - `git_status`
  - `git_pull` (`--ff-only`)
  - `list_files` (top-level only)
- Per-project logs (tail + WebSocket streaming)
- System stats (psutil)

## Assumptions

- This dashboard is intended for **LAN / VPN use** (e.g. behind Tailscale). Do not expose it publicly.
- Your projects are direct subfolders of `DEV_ROOT` (default: `~/Desktop/Devs`).
- If `DASHBOARD_LOGS` lives inside `DEV_ROOT`, it is ignored from the projects list.
- For safety, symlinked entries that resolve outside `DEV_ROOT` are ignored.
- You will create the initial admin user using `scripts/init_db.py`.

## Quickstart (Linux Mint)

From the repo root:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env (set SECRET_KEY at minimum)

python ../scripts/init_db.py
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080/`.

## Windows development

From the repo root (PowerShell):

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

## Configuration

The backend reads environment variables (see `backend/.env.example`):

- `DEV_ROOT` (default: `~/Desktop/Devs`)
- `DASHBOARD_LOGS` (default: `~/Desktop/Devs/dashboard_logs`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8080`)
- `SECRET_KEY` (required for stable sessions; auto-generated in dev with a warning)
- Optional: `AUTH_DB`, `COOKIE_NAME`, `COOKIE_SECURE`, `SESSION_TTL_SECONDS`

## Security notes

- Keep this on your LAN (or behind a VPN). If you need internet access, use a reverse proxy + HTTPS + additional controls.
- Actions are hard-coded allowlists. The API does **not** run arbitrary shell commands from user input.
- `git pull` is `--ff-only` and disables terminal prompts (`GIT_TERMINAL_PROMPT=0`).

## Running tests

```bash
cd backend
python -m pytest
```

## Deployment (systemd)

Use the unit file in `systemd/homelab-dashboard.service` as a starting point:

1. Clone the repo onto your Linux Mint host
2. Create a venv in `backend/.venv` and install requirements
3. Copy `backend/.env.example` to a real `.env` and set `SECRET_KEY`
4. Edit the systemd service to point to your clone location and Linux user

Then:

```bash
sudo cp systemd/homelab-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-dashboard
```
