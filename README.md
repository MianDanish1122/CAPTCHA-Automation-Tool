# Technology Brainz — CAPTCHA Inspector

A CAPTCHA **recognition, solving (owned/synthetic only) and verification** tool with a web dashboard, built for
"Assignment 01 — CAPTCHA Solving & Verification Tool".

What it does, honestly:

| Capability | Status |
| :--- | :--- |
| Recognise & classify CAPTCHAs (reCAPTCHA v2/invisible, hCaptcha, Turnstile, anti-bot interstitials, synthetic text) | rule-based detection, tested on fixtures and a local site |
| **Solve** synthetic text CAPTCHAs the project generates itself | custom NumPy glyph classifier + Tesseract fallback: **99.3 % exact match on 300 never-inspected held-out images** (same generator; see limits) |
| Verify tokens server-side with the providers' **official** `siteverify` endpoints (reCAPTCHA, hCaptcha, Turnstile) | official **test keys** (live) + mocks + clearly labelled simulations; every result states how it was produced |
| Third-party / production CAPTCHAs | **never solved or bypassed** — detected and routed to a human review queue |
| Paid external solver API | **none integrated** |
| Dashboard | Next.js: overview, evaluation metrics (with denominators), inspector, scans, results, human review, OCR lab, verification, batch, reports |

Docs index: [requirements mapping](docs/REQUIREMENTS_MAPPING.md) · [architecture](docs/SYSTEM_ARCHITECTURE.md) ·
[OCR evaluation](docs/PHASE_7_OCR_EVALUATION.md) · [verification matrix](docs/PHASE_7_VERIFICATION_MATRIX.md) ·
[AI/API inventory](docs/PHASE_7_AI_API_INVENTORY.md) · [cost](docs/PHASE_7_COST_ANALYSIS.md) ·
[reliability](docs/PHASE_7_RELIABILITY_REPORT.md) · [security summary](docs/SECURITY_SUMMARY.md) ·
[API](docs/API_REFERENCE.md) · [user guide + demo checklist](docs/USER_GUIDE.md) · [deployment](docs/DEPLOYMENT_GUIDE.md) ·
[test report](docs/TEST_REPORT.md) · [known limitations](docs/KNOWN_LIMITATIONS.md) · [final acceptance](docs/PHASE_7_FINAL_ACCEPTANCE.md)

## Quick start (Windows, PowerShell)

Prerequisites: Python 3.12+, Node.js 20+, [Tesseract 5](https://github.com/UB-Mannheim/tesseract/wiki) (default path `C:\Program Files\Tesseract-OCR\tesseract.exe`).

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env            # then edit: set JWT_SECRET_KEY, AUDIT_HMAC_KEY (see below)

# database: development auto-creates tables; for a managed schema use Alembic
.\venv\Scripts\python.exe -m alembic upgrade head

# first administrator (prompts for a password; nothing is hard-coded)
.\venv\Scripts\python.exe -m app.cli create-admin --username admin --email admin@example.test

# backend (do not use --reload on Windows with Playwright)
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (second terminal)
cd frontend; npm install; npm run build; npm run start -- -p 3000
```

Open http://localhost:3000 and sign in. Swagger UI: http://127.0.0.1:8000/docs.

## Required / important environment variables (`.env`)

| Variable | Default | Notes |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | `production`/`staging` enforce strong secrets, no dev loopback, no fixtures |
| `JWT_SECRET_KEY` | dev placeholder | **required ≥ 32 chars in production** |
| `AUDIT_HMAC_KEY` | derived (dev only) | **independent of the JWT secret; required in production** (`python -m app.cli generate-audit-key`) |
| `DATABASE_URL` | SQLite `data/captcha_tool.db` | |
| `ENABLE_LIVE_SCAN` | `false` | scanning external sites needs `true` **and** `ALLOWED_DOMAINS` |
| `ALLOWED_DOMAINS` | `example.com,demo.com,localhost` | authorised scan targets only |
| `TESSERACT_CMD` | Windows default path | |
| `TRUSTED_PROXIES` | empty | forwarding headers ignored unless the peer is listed |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | |
| `RECAPTCHA_TEST_*`, `VERIFY_TIMEOUT_SECONDS` | Google public test keys, 8 | verification demo |
| `INITIAL_ADMIN_SETUP_TOKEN` | empty | leave empty; use the CLI |

Complete list with comments: `.env.example`.

## Try the features

```powershell
# 1) OCR: reproduce the benchmark (deterministic dataset in datasets/ocr_synthetic_v1)
.\venv\Scripts\python.exe -m scripts.ocr_benchmark verify-dataset
.\venv\Scripts\python.exe -m scripts.ocr_benchmark evaluate --split test2 --out my_run.json

# 2) Official test-key token acquisition + server-side verification (needs internet)
.\venv\Scripts\python.exe -m scripts.token_acquisition_demo

# 3) Tests
.\venv\Scripts\python.exe -m pytest tests/ -q
```

In the UI: **Evaluation** (metrics + report) → **URL Inspector** → **Scan History** → **CAPTCHA Results** → **OCR Laboratory** → **Verification** → **Human Review** → **Reports**. See [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Repository layout

```
app/                FastAPI backend
  routes/           auth, websites, captcha, evidence, stats
  services/         crawler, browser scanner, SSRF/egress guard, classification, token verifier, audit, jobs
  ocr/              dataset generator, preprocessing, segmentation, custom model, engines, metrics
scripts/            ocr_benchmark.py, token_acquisition_demo.py
datasets/           ocr_synthetic_v1 (hash-verified dev/test/test2 + manifest)
alembic/            migrations (Phase 1-5 baseline, Phase 6 security, Phase 7 evaluation)
frontend/           Next.js dashboard
tests/              pytest suite + Playwright E2E scripts
docs/               documentation and phase reports      evidence/  measured outputs and screenshots
```

## Safety & scope

Only synthetic/owned challenges are solved. Production reCAPTCHA/hCaptcha/Turnstile challenges are detected and sent to human review; official **test** modes are used for demonstrations; no tokens are harvested or forged; scans are limited to authorised domains behind an SSRF/egress guard. See [docs/SECURITY_SUMMARY.md](docs/SECURITY_SUMMARY.md) and [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).
