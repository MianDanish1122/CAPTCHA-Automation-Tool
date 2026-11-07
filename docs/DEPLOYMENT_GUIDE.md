# Deployment Guide (documentation only — no deployment has been performed)

This guide describes how to run the application outside development. **Do not expose it publicly without approval and the controls below.** Containers/reverse-proxy examples from Phase 5 are in `docs/PHASE_5_DEPLOYMENT_GUIDE.md`; this page is the up-to-date checklist.

## 1. Preconditions
- Python 3.12, Node 20, Tesseract 5 on the host, `python -m playwright install chromium` (run Chromium in an isolated container/VM with a non-root user for anything beyond a pilot).
- One application process per database (audit lock, rate limiter and job registry are in-process).

## 2. Secrets and configuration (`APP_ENV=production`)
Startup **refuses to run** unless: `DEBUG=false`, no `ALLOW_DEV_LOOPBACK`, no `SCAN_ALLOW_INVALID_CERTS`, `JWT_SECRET_KEY` ≥ 32 chars (not `dev-…`), `AUDIT_HMAC_KEY` ≥ 32 chars **and different** from the JWT secret, no wildcard CORS, `INITIAL_ADMIN_SETUP_TOKEN` (if set) ≥ 24 chars. Fixtures are disabled in production regardless of `ALLOW_FIXTURES`.

| Secret | Generate | Store |
| :--- | :--- | :--- |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | secret manager → env var |
| `AUDIT_HMAC_KEY` | `python -m app.cli generate-audit-key` | separate secret, not in DB backups; rotate with `AUDIT_HMAC_KEYS_PREVIOUS` (see `PHASE_6B_FINAL_REVIEW.md`) |

Other settings: `ALLOWED_DOMAINS` (only authorised targets), `ENABLE_LIVE_SCAN` (leave `false` unless authorised), `CORS_ALLOWED_ORIGINS` (your exact frontend origin), `TRUSTED_PROXIES` (your reverse proxy's address; it must *append* to `X-Forwarded-For`), `NEXT_PUBLIC_API_BASE_URL` at frontend build time, `VERIFY_TIMEOUT_SECONDS`.

## 3. Database
```powershell
# backup first (also records the audit head)
python -m app.cli backup-db
python -m alembic upgrade head          # baseline → 6b01phase6security → 7a01phase7evaluation (idempotent)
python -m app.cli audit-verify          # chain valid?
```
Rollback: downgrades are destructive and refuse to run without `ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1`; restore from a verified backup instead (`restore-db --file … --expected-head-seq … --expected-head-hash … --yes`, application stopped). After upgrading from a pre-6B release every user must sign in again (`JWT_REQUIRE_VER_CLAIM=true`).

## 4. First administrator
`python -m app.cli create-admin --username … --email …` (hidden prompt, ≥ 12 chars) or `--generate-password`. Avoid `INITIAL_ADMIN_SETUP_TOKEN`.

## 5. OCR assets
`app/ocr/model/glyph_mlp_v1.npz` and `tesseract_tuned.json` ship with the repository. Verify the dataset with `python -m scripts.ocr_benchmark verify-dataset`. Retraining is optional (`train`, ~1 min).

## 6. Run
Backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000` behind a TLS-terminating reverse proxy (HSTS, CSP, request-size limits at the proxy as well). Frontend: `npm ci && npm run build && npm run start -p 3000` (or static export behind the proxy). Do not use `--reload` on Windows with Playwright.

## 7. Operations
- Daily: `backup-db`; copy the printed audit head (`head_seq`, `head_hash`) to **write-once storage**; periodically `audit-verify --expected-head-seq … --expected-head-hash …`.
- Emergency: `python -m app.cli invalidate-sessions --all`.
- Monitor `/health` (public liveness), `/api/health/details` (authenticated), audit log actions `auth.login_failed`, `scan.create`, `captcha.mode_assertion`.
- Provider verification needs outbound HTTPS to the three `siteverify` hosts; scanning needs outbound access only to allow-listed domains.

## 8. Not covered
Multi-instance scaling (needs Redis/DB locks/queue), PostgreSQL port of audit triggers, container hardening, CI/CD, monitoring stack.
