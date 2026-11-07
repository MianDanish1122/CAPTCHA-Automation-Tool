# Demo Environment Guide

A dedicated, disposable environment for the recording: **its own database, its own demo accounts, and an owned demo website — no real data, no real accounts, no arbitrary scanning.** Windows / PowerShell, run from the repository root (`captcha-automation-tool`).

## What the demo environment guarantees

| Property | How |
| :--- | :--- |
| Separate data | `demo_runtime/demo.db` (git-ignored); your real `data/captcha_tool.db` is never opened (the backend is started with `DATABASE_URL` pointing at the demo DB) |
| No real accounts | two accounts `demo_operator` / `demo_admin` (`@demo.invalid`) with **random passwords** generated on your machine into `demo_runtime/demo_credentials.txt` |
| Only synthetic / owned / official-test data | OCR on the project's own generated CAPTCHAs; scanning only `http://127.0.0.1:8090/` (served by `scripts.demo_env site`); verification only with the providers' published **test** keys |
| No arbitrary scanning | `ENABLE_LIVE_SCAN=false`, `ALLOWED_DOMAINS=localhost`; any other URL is refused before a request is made (rehearsed: `https://example.com` → "not in the authorized domains allowlist"; `http://169.254.169.254/…` → "cloud metadata IP … prohibited") |
| No bypass of third-party CAPTCHA | the demo page's reCAPTCHA widget uses a made-up site key; it is detected and queued for a human, never solved |
| Real measurements | the held-out OCR table is imported from `evidence/phase7/ocr/evaluation_test2.json` (produced by the benchmark script); everything else is created live during the demo |

## One-time setup

```powershell
# 1. dependencies (skip what you already have)
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
cd frontend; npm install; npm run build; cd ..

# 2. create the demo database + demo accounts + import the OCR benchmark results
.\venv\Scripts\python.exe -m scripts.demo_env setup --reset
```
`setup` prints the location of the credentials file. **Open it privately** (never on the recorded screen); passwords are not printed.

## Launch (three PowerShell windows, repository root)

**Window 1 — backend**
```powershell
$env:DATABASE_URL = 'sqlite:///C:/<your path>/captcha-automation-tool/demo_runtime/demo.db'   # exact line: run  .\venv\Scripts\python.exe -m scripts.demo_env env
$env:APP_ENV = 'development'
$env:ALLOW_DEV_LOOPBACK = 'true'
$env:ENABLE_LIVE_SCAN = 'false'
$env:ALLOWED_DOMAINS = 'localhost'
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
(`.\venv\Scripts\python.exe -m scripts.demo_env env` prints these five lines with the correct database path for your machine.)

**Window 2 — owned demo website**
```powershell
.\venv\Scripts\python.exe -m scripts.demo_env site        # http://127.0.0.1:8090/
```

**Window 3 — dashboard**
```powershell
cd frontend
npm run start -- -p 3000                                   # http://localhost:3000
```

Health check (no secrets in the output): `curl http://127.0.0.1:8000/health` → `{"status":"healthy"}`.

## Rehearse, then reset (important)

The rehearsal performs every scene in a real browser, times it, checks the expected output, and scans every page for leaked personal/internal details (Windows profile paths, e-mail addresses, JWTs, secret names, the demo passwords themselves):

```powershell
.\venv\Scripts\python.exe tests\demo_rehearsal.py
```
Last run on this machine: **19/19 steps passed, 0 leak findings, 0 console errors, 0 failed requests**, machine time ≈ 80 s (report + screenshots: `evidence/demo_rehearsal/`).

**The rehearsal writes demo data (a scan, a review decision, OCR and verification records). The recording needs the *empty* starting state, so afterwards:**
1. Stop the backend (Ctrl+C in Window 1).
2. `.\venv\Scripts\python.exe -m scripts.demo_env setup --reset`
3. Start the backend again (Window 1 commands). New passwords are generated — re-open the credentials file.

The rehearsal only works on a freshly reset database (it asserts "0 scans" at the start).

## Demo accounts
| Role | Username | Password |
| :--- | :--- | :--- |
| operator (used for the whole script) | `demo_operator` | in `demo_runtime/demo_credentials.txt` |
| admin (not needed; only for the audit-trail page) | `demo_admin` | same file |

Create extra accounts only with `python -m app.cli create-user` (prompted password). Nothing is hard-coded anywhere.

## Recording sequence (recommended)
1. Read `DEMO_RECORDING_CHECKLIST.md` (screen/privacy preparation).
2. Setup (once) → launch the three windows → run the rehearsal → fix anything it reports.
3. `setup --reset` + restart the backend (clean starting state).
4. Practise the script once without recording, using the demo site (this *dirties* the DB — reset again before the take).
5. Reset again (`setup --reset`, restart backend), open the credentials file privately, start recording, follow `DEMO_VIDEO_SCRIPT.md`.
6. After recording: stop the three windows, review the video frame by frame for leaks (checklist), then optionally `Remove-Item -Recurse demo_runtime`.

## Troubleshooting
| Symptom | Fix |
| :--- | :--- |
| Login rejected | wrong password (copy from the credentials file) or you reset the DB without restarting the backend |
| Inspector says target not allowed | you changed the environment: use `http://127.0.0.1:8090/` and keep `ALLOW_DEV_LOOPBACK=true` |
| Verification shows `provider_unavailable` | no internet to the providers' `siteverify` hosts; reconnect (the honest outage result is also a valid demo of the failure path) |
| First OCR run is slow | the model is loading on first use; run once before recording |
| Port busy | stop old windows; ports used: 8000, 3000, 8090 |

## Pre-recording audit — findings (reported separately; app behaviour not otherwise changed)

| # | Finding | Severity | Status |
| :-: | :--- | :-: | :--- |
| 1 | **Settings page/API printed local absolute paths** (`evidence_dir`, `reports_dir`, the Tesseract install path) — exposed the Windows profile name. | Medium (privacy) | **Fixed** (`app/routes/websites.py`): the API now returns `evidence/`, `reports/` and `tesseract`; the real configuration is used internally unchanged. 8 tests in `tests/test_settings_privacy.py`; rehearsal step S9b. The Settings page can now be shown. |
| 2 | OCR page showed the custom model's confidence as **"9998%"** (value ×100 on a value already in percent) | Medium (misleading number) | **Fixed** (display `99.98% (engine-reported)`) |
| 3 | OCR page labelled every engine's output **"TESSERACT OCR PREDICTION"** even when the custom model produced it | Medium (misleading attribution) | **Fixed** → "OCR Prediction"; page header now mentions the custom glyph model |
| 4 | The 99.3 % scope limit was only in documents, **not on screen** | High for requirement 7 | **Fixed:** scope note added to the OCR benchmark card and above the held-out table on the Evaluation page |
| 5 | Login badge said "Phase 5 Security-Hardened" (stale) | Low | **Fixed** → "Security-Hardened" |
| 6 | The sidebar "Docs" link opens Swagger (`/docs`) which lists every endpoint | Low | not changed; do not click it |
| 7 | Terminal prompts and file explorers show `C:\Users\<you>\OneDrive\…` | Medium (privacy) | recording hygiene — see the checklist |

Files changed for 2–5: `frontend/app/ocr/page.tsx`, `frontend/app/evaluation/page.tsx`, `frontend/app/login/page.tsx` (text only). New: `scripts/demo_env.py`, `tests/demo_rehearsal.py`, `.gitignore` (`demo_runtime/`).
