# Homelab Dashboard - Agent Notes

## Layout

This repo is intentionally split into a minimal backend + static frontend:

- `backend/app/` - FastAPI app code
- `backend/tests/` - pytest tests
- `frontend/` - static HTML/CSS/JS (served by the backend)
- `scripts/` - dev + admin scripts
- `systemd/` - systemd unit template

## Dev commands

Backend (from `backend`):

- Run: `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080`
- Tests: `python -m pytest`

Convenience scripts (from the repo root):

- Linux/macOS: `bash scripts/dev_backend.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File scripts/dev_backend.ps1`

## Auth DB init

Create the first admin user:

- From the repo root: `python scripts/init_db.py`
- Uses `ADMIN_USER` / `ADMIN_PASS` env vars if set, otherwise prompts.

## Adding new actions (conventions)

- Add the action name to `backend/app/models.py` (`ActionName`) and `ActionRequest`.
- Implement the allowlisted behavior in `backend/app/actions.py`:
  - No user-provided command strings
  - Use `run_subprocess()` with explicit command arrays, `cwd`, and timeouts
  - Append a single-line summary via `append_project_log_line()`
- Update the UI buttons in `frontend/app.js`.

