# Reproducing the browser test environment

Prerequisites: project `venv` with requirements, `playwright install chromium`, Node.js and `npm install` in `frontend\`.
Ports 8000 and 3000 must be free (the script refuses to start otherwise and never kills processes it did not start).

## One command (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\e2e\run-browser-suites.ps1 -Suite all -Build
```

`-Suite` is `phase7`, `phase6b`, `batch`, `demo` or `all`. `-Build` runs `npm run build` first. `-OutDir <path>` chooses where evidence is written.

What it guarantees:
- **Isolated database** per suite in the system temp folder; `data\captcha_tool.db` is never used.
- **Random credentials** generated in memory for the run; nothing is hard-coded or written to disk. (The demo suite uses `scripts.demo_env`, which stores its own random demo passwords in the git-ignored `demo_runtime\`.)
- **Evidence goes to `.e2e_runs\<timestamp>\`** (`E2E_OUT_DIR`), not to the tracked `evidence\` folders. If `E2E_OUT_DIR` is unset the suites write to their historical `evidence\...` locations, as before.
- Only the processes the script started are stopped. Exit code 1 if any suite fails.

## Equivalent manual commands (one suite)

```powershell
$env:DATABASE_URL = "sqlite:///$((Join-Path $env:TEMP 'e2e.db') -replace '\\','/')"
$env:APP_ENV = "development"; $env:ALLOW_DEV_LOOPBACK = "true"
$env:E2E_OPERATOR_USER = "e2e_operator"; $env:E2E_OPERATOR_PASSWORD = "<choose a random value>"
$env:E2E_ADMIN_USER = "e2e_admin";       $env:E2E_ADMIN_PASSWORD    = "<choose a random value>"   # phase6b only
$env:E2E_OUT_DIR = "$PWD\.e2e_runs\manual"; New-Item -ItemType Directory -Force "$env:E2E_OUT_DIR\batch_ui" | Out-Null

venv\Scripts\python.exe tests\e2e_realworld_batch_ui.py seed        # or e2e_phase7_browser.py / e2e_phase6b_browser.py
Start-Process venv\Scripts\python.exe -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WindowStyle Hidden
Start-Process npm.cmd -ArgumentList "run start -- -p 3000" -WorkingDirectory frontend -WindowStyle Hidden
venv\Scripts\python.exe tests\e2e_realworld_batch_ui.py run         # phase6b also has: ... cleanup
```

Demo rehearsal: `python -m scripts.demo_env setup --reset`, then set `DATABASE_URL` to `demo_runtime\demo.db`, `ENABLE_LIVE_SCAN=false`, `ALLOWED_DOMAINS=localhost`, start the backend, the frontend and `python -m scripts.demo_env site`, then `python tests\demo_rehearsal.py`.

## Backend tests

`pytest tests` now uses a throw-away database automatically (see `tests\conftest.py`). Export `DATABASE_URL` yourself only if you deliberately want a specific database.
