# API Reference

Generated from the running FastAPI app (`app.routes`); interactive OpenAPI docs are served at `/docs`. Base URL `http://127.0.0.1:8000`.

**Authentication:** every `/api/*` route needs `Authorization: Bearer <JWT>` (from `POST /api/auth/login`) except `login`, `setup-initial-admin` (gated by a setup token) and `/api/health`. **Roles:** `operator` (default) and `admin` (user management, audit log, audit verification). **Errors:** `401` unauthenticated/expired/revoked, `403` role, `404`, `413` body too large, `422` validation, `429` rate or job limit (with `Retry-After`), `503` database unavailable, `500` generic message.

| Method | Path | Purpose |
| :-- | :-- | :-- |
| GET | `/` | Home |
| GET | `/api/auth/audit-logs` | Administrator-only endpoint to inspect security audit trail. |
| GET | `/api/auth/audit-logs/verify` | Administrator-only: recompute the audit hash chain and report tampering, if any. |
| POST | `/api/auth/login` | Authenticate user credentials and issue signed JWT access token. |
| POST | `/api/auth/logout` | Revoke the presented access token (server-side) and record the audit trail. |
| POST | `/api/auth/logout-all` | Invalidate every session (token) the current user has ever been issued. |
| GET | `/api/auth/me` | Return currently authenticated user profile and assigned role. |
| POST | `/api/auth/setup-initial-admin` | One-time bootstrap of the first administrator. |
| POST | `/api/auth/users` | Administrator-only endpoint to create new system users/operators. |
| POST | `/api/auth/users/{user_id}/deactivate` | Administrator-only: disable an account and invalidate its sessions immediately. |
| POST | `/api/auth/users/{user_id}/revoke-sessions` | Administrator-only: invalidate every outstanding token of a user (e.g. suspected leak). |
| POST | `/api/captcha/classify` | Classify page HTML/DOM markers into recognized CAPTCHA providers, |
| POST | `/api/captcha/evaluate-handling` | Classify discovered CAPTCHA and execute appropriate handling workflow: |
| POST | `/api/captcha/ocr-benchmark` | Evaluate an engine on the committed, hash-verified labelled dataset (`datasets/ocr_synthetic_v1`). |
| GET | `/api/captcha/ocr-benchmark/runs` | Persisted OCR evaluation runs (CLI held-out runs and API runs). |
| POST | `/api/captcha/ocr-demo` | Generate an OWNED synthetic CAPTCHA (true label known), recognise it with the selected engine, |
| GET | `/api/captcha/results` | Retrieve classified CAPTCHA records across scans. |
| GET | `/api/captcha/reviews` | Retrieve queue of human review records with status counters. |
| GET | `/api/captcha/reviews/{review_id}` | Retrieve details for a single human review record. |
| PATCH | `/api/captcha/reviews/{review_id}` | Update human review status as an operator decision. |
| GET | `/api/captcha/reviews/{review_id}/history` | Full, append-only decision history (who decided what, when, and why). |
| GET | `/api/captcha/verification/providers` | Supported providers, their official endpoints and the kinds of scenarios available. |
| GET | `/api/captcha/verification/records` | List Verification Records |
| POST | `/api/captcha/verify-token` | Server-side verification against the provider's official siteverify endpoint. |
| GET | `/api/evidence/{file_path}` | Get Evidence File |
| GET | `/api/health` | Public liveness probe: deliberately reveals nothing about configuration. |
| GET | `/api/health/details` | Authenticated diagnostics (configuration-dependent details live here, not on /health). |
| GET | `/api/stats/report` | Markdown evaluation report generated from the same persisted data as the dashboard. |
| GET | `/api/stats/summary` | Stats Summary |
| GET | `/api/websites/batches` | List batch jobs with optional status filter and pagination. |
| GET | `/api/websites/batches/{batch_id}` | Retrieve execution status and summary counters for a batch job. |
| GET | `/api/websites/batches/{batch_id}/report` | Generate and download a CSV compliance report for the specified batch. |
| GET | `/api/websites/batches/{batch_id}/results` | Retrieve itemized website inspection results for a batch job. |
| POST | `/api/websites/import` | Upload Csv |
| POST | `/api/websites/inspect-demo` | Inspect Demo |
| POST | `/api/websites/inspect-demo-batch` | Inspect Demo Batch |
| POST | `/api/websites/inspect-url` | Inspect an authorized website URL using Playwright. |
| GET | `/api/websites/overview-stats` | Summary metrics and provider distribution for the overview dashboard. |
| GET | `/api/websites/pages` | List discovered pages across scans with CAPTCHA and provider filters. |
| POST | `/api/websites/scan-batch` | Initiate an asynchronous batch scan for up to 300 website records. |
| GET | `/api/websites/scans` | List URL crawl scans with optional status filter and pagination. |
| GET | `/api/websites/scans/{scan_id}` | Retrieve status and summary information for a website crawl scan. |
| GET | `/api/websites/scans/{scan_id}/results` | Retrieve detailed discovered pages, classifications, evidence, and CAPTCHA results. |
| GET | `/api/websites/settings` | Diagnostic system settings and environment configuration. |
| GET | `/health` | Public liveness probe: deliberately reveals nothing about configuration. |

## Key request/response contracts

### `POST /api/captcha/verify-token`
```json
{"provider": "google_recaptcha|hcaptcha|cloudflare_turnstile", "token": "...", "secret_key": "(optional, operator's own)", "simulate_status": "invalid|expired|reused|provider_down|provider_malformed (optional, SIMULATION)", "expected_hostname": "(optional, real keys)"}
```
Response: `success`, `verification_mode` (`provider_live|provider_test_keys|simulated|local_validation`), `outcome`, `provider_called`, `provider_verified`, `token_source`, `http_status`, `error_codes`, `hostname`, `message`, `duration_ms`, `evidence_note`. `success` is true only if the provider confirmed. See `docs/PHASE_7_VERIFICATION_MATRIX.md`.

### `POST /api/captcha/ocr-benchmark`
`{"samples": 1-100, "engine": "hybrid|custom_mlp|tesseract_tuned|tesseract_legacy", "split": "dev|test"}` → evaluates the first N committed, hash-verified dataset samples (deterministic), persists a run, returns exact/char accuracy, latency, failures, per-sample results.

### `POST /api/captcha/ocr-demo`
`{"custom_text": "AB23C (optional)", "engine": "hybrid"}` → generates an owned synthetic CAPTCHA with a known label, recognises it, stores a real evaluation record.

### `GET /api/stats/summary?days=N`
Aggregates computed from persisted rows only; every block carries `denominator`; `time_range` states `since/until/all_time`. `GET /api/stats/report` returns the same data as a Markdown download.

### `GET /api/evidence/scans/<scan-id>/<file>.png`
Authenticated screenshot access; nothing else under `evidence/` is served.
