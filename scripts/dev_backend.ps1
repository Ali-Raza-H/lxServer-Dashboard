$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RootDir "backend")

if (-not (Test-Path ".venv")) {
  if ($env:PYTHON) {
    & $env:PYTHON -m venv .venv
  } elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.12 -m venv .venv
  } else {
    python -m venv .venv
  }
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

$HostAddr = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$PortNum = if ($env:PORT) { $env:PORT } else { "8080" }

python -m uvicorn app.main:app --reload --host $HostAddr --port $PortNum

