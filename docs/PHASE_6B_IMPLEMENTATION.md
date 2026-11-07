# Phase 6B — Additional Security Hardening

**Branch:** `phase-6-security-remediation` (continues from Phase 6A, `9ce10b1`).
No CAPTCHA-bypass capability was added; synthetic OCR, official test-mode verification, fixtures and human review are preserved.

| # | Item | Where |
| :-- | :--- | :--- |
| 1 | Authenticated evidence screenshots | `app/routes/evidence.py`, `main.py`, `frontend/lib/api.ts`, `EvidenceViewer.tsx` |
| 2 | Minimal `/health` | `main.py` |
| 3 | Secure one-time admin provisioning | `routes/auth.py`, `config.py`, `cli.py` (6A) |
| 4 | Token revocation / session invalidation | `models.py`, `services/auth_service.py`, `routes/auth.py` |
| 5 | Server-side validation of `is_synthetic` / `is_official_test` | `services/captcha_intelligence.py`, `routes/captcha.py` |
| 6 | Request size limits | `services/input_limits.py`, route models, `main.py` |
| 7 | Missing rate limits | `routes/*.py`, `config.py` |
| 8 | Concurrent crawl / background-job limits | `services/job_manager.py`, `routes/websites.py`, `batch_processor.py` |
| 9 | Reviewer identity + decision history | `models.py` (`ReviewDecision`), `routes/captcha.py` |
| 10 | Tamper-evident audit records | `services/audit.py`, `database.py` |
| 11 | Redaction of sensitive values | `services/audit.py`, `routes/auth.py`, `routes/websites.py` |

## 1. Evidence screenshots

The public `StaticFiles` mount (`/evidence/**`, which exposed the *entire* evidence directory including test artifacts) is removed. `GET /api/evidence/{path}` now requires an operator/admin session and serves only `scans/<uuid>/<name>.png|jpg|jpeg`. The path must match a strict pattern and resolve inside `evidence/scans/`; responses are `Cache-Control: private, no-store`, `nosniff`. Because `<img src>` cannot send a bearer token, the UI fetches the image with the session token and shows it via an object URL (revoked on unmount).

## 2. `/health`

`/health` and `/api/health` return only `{"status":"healthy"}`. `/` no longer reports environment or scan settings. Diagnostics (OCR engine, allow-listed domains, live-scan flag, active jobs) moved to `GET /api/health/details` (authenticated); the dashboard uses it and falls back to the public probe.

## 3. Admin provisioning

`POST /api/auth/setup-initial-admin` **does not exist (404)** unless `INITIAL_ADMIN_SETUP_TOKEN` (≥ 24 chars) is configured; the caller must send it in `X-Setup-Token` (constant-time compare). It works only while the users table is empty, the check-and-insert is serialised, passwords must be ≥ 12 chars, it is rate-limited (3/min) and both successes and denied attempts are audited. Production startup rejects a configured token shorter than 24 chars. The CLI (`python -m app.cli create-admin`, Phase 6A) remains the recommended path and needs no network endpoint.

## 4. Token revocation

- `POST /api/auth/logout` now adds the token's `jti` to a denylist (`revoked_tokens`, auto-pruned after natural expiry). The frontend already called this endpoint, so logout is now real.
- `users.token_version` + a `ver` claim: `POST /api/auth/logout-all` (self), `POST /api/auth/users/{id}/revoke-sessions` and `/deactivate` (admin) invalidate *every* outstanding token immediately. Deactivation also blocks login; admins cannot deactivate themselves.
- Login does equal bcrypt work for unknown usernames (timing-based enumeration).
- Cost: one extra indexed lookup per authenticated request.

## 5. Client-asserted modes

The client's flags are now *requests*, never authority (`validate_client_assertions`):

- `is_synthetic` is honored only with a valid, bounded image **and** a page without real provider/interstitial markers — so it cannot hide a genuine third-party CAPTCHA from the review queue.
- `is_official_test` is honored only when a provider is detected and **every** site key on the page is a published provider test key (Google, hCaptcha, Turnstile). Otherwise the page is handled as a real challenge and queued for human review.
- Responses include `client_assertions` explaining each decision; `evaluate-handling` writes a `captcha.mode_assertion` audit event.
- Note: a user can still upload *their own* image and claim it is synthetic; ownership cannot be proven by software, so the claim is attributed (audit log) rather than trusted for third-party provider pages.

## 6. Size limits

- ASGI middleware: JSON bodies ≤ `MAX_JSON_BODY_BYTES` (2 MB), multipart ≤ CSV limit + framing; enforced by `Content-Length` **and** while streaming (chunked uploads).
- Fields: HTML ≤ `MAX_HTML_CHARS` (200k) on every endpoint, base64 length bounded, title/URL/token/secret/notes bounded, enums via patterns.
- Images: strict base64, ≤ `MAX_IMAGE_BYTES` (1 MB), allowed formats only, header-level dimension check against `MAX_IMAGE_PIXELS` (4 MP) **before** any decode (decompression-bomb defence). Invalid base64 is now an error (previously silently ignored).
- `audit-logs` `limit` is capped at 200.

## 7. Rate limits

Router-wide default (120/min) on websites and captcha APIs; `compute` bucket (30/min) on inspect-demo, inspect-demo-batch, classify, evaluate-handling, ocr-demo, verify-token; admin operations 20/min; bootstrap 3/min; audit verification 10/min. Existing login/inspect/batch/benchmark/review limits unchanged. Still per-process memory keyed by trusted client IP (Redis is an infrastructure follow-up).

## 8. Job limits

`JobManager`: max concurrent crawls (`MAX_CONCURRENT_CRAWLS`=2), batch jobs (`MAX_CONCURRENT_BATCH_JOBS`=1), and active jobs per user (`MAX_ACTIVE_JOBS_PER_USER`=2). Over the limit → HTTP 429 with `Retry-After`, checked *before* any DB rows are created. Foreground crawls occupy a slot too. Background tasks are strongly referenced (previously fire-and-forget tasks could be garbage-collected) and cancelled on shutdown; slots are released even if a task is cancelled before it starts. Jobs are still lost on process restart (no queue) — unchanged.

## 9. Reviewer identity and history

Every `PATCH /api/captcha/reviews/{id}` writes an append-only `review_decisions` row (who, role, previous → new status, notes, IP, request id) and updates `reviewed_by` / `decision_count` on the review. `GET /reviews/{id}/history` and the detail endpoint return the history. DB triggers block UPDATE/DELETE on that table. Free-text notes are kept in the decision record but **not** copied into the audit trail. *The UI does not yet display reviewer/history (API only).*

## 10. Tamper-evident audit trail

Each entry has `seq`, `prev_hash` and `entry_hash = HMAC-SHA256(key, prev_hash | canonical entry)`. Changing, deleting, inserting or reordering entries breaks verification from that point (`GET /api/auth/audit-logs/verify`, admin). SQLite triggers also make `audit_logs` UPDATE/DELETE fail at the database layer. Existing (pre-6B) rows are reported as `legacy_unchained_entries`; the chain starts at the first new entry.

**Limitations (honest):** (a) someone with the DB file can drop the triggers, but cannot recompute valid hashes without the key; someone with *both* can re-forge, so export/anchor `head_hash` externally (e.g. periodic copy to write-once storage); (b) if `AUDIT_HMAC_KEY` is unset the key is derived from `JWT_SECRET_KEY` — **rotating that secret makes older entries fail verification**, so set `AUDIT_HMAC_KEY` explicitly; (c) writers are serialised by an in-process lock, so run a single app process or add a DB-level sequence/lock before scaling out; (d) triggers are SQLite-only (PostgreSQL needs equivalent rules/permissions).

## 11. Redaction

`redact()` recursively masks values under sensitive keys (password, secret, token, authorization, api key, cookie, session, jwt, signature…), JWT-shaped strings, and strips userinfo/query strings from URLs inside strings; long strings are truncated. Applied to all audit details. Failed logins no longer store the attempted username (people type passwords there): only a keyed fingerprint (and the account id when the user exists) is recorded. `scan.create` stores a URL with its query redacted. Client `X-Request-ID` values are accepted only if short and `[A-Za-z0-9._-]`, otherwise replaced (log-injection defence). Baseline security headers (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` for `/api/*`) were added.

## Schema changes (additive)

`users.token_version`; `audit_logs.seq/prev_hash/entry_hash`; `human_reviews.reviewed_by_id/reviewed_by_username/decision_count`; new tables `revoked_tokens`, `review_decisions`. `init_db()` applies these to existing databases automatically (`ALTER TABLE … ADD COLUMN`, idempotent) because `create_all` never alters tables and the Alembic migration is still an empty stub. Tokens issued before the upgrade stay valid until expiry, logout-all or revocation.

## New configuration (see `.env.example`)

`INITIAL_ADMIN_SETUP_TOKEN`, `AUDIT_HMAC_KEY`, `MAX_JSON_BODY_BYTES`, `MAX_HTML_CHARS`, `MAX_IMAGE_BYTES`, `MAX_IMAGE_PIXELS`, `RATE_LIMIT_COMPUTE_PER_MIN`, `RATE_LIMIT_ADMIN_PER_MIN`, `RATE_LIMIT_SETUP_PER_MIN`, `MAX_CONCURRENT_CRAWLS`, `MAX_CONCURRENT_BATCH_JOBS`, `MAX_ACTIVE_JOBS_PER_USER`.

## Behavior changes to be aware of

- `/evidence/**` and the config fields on `/` and `/health` are gone (intended).
- Invalid base64/images now return 400/413 instead of being ignored.
- `is_official_test` / `is_synthetic` can now be refused; the response says why.
- A reviewer's free-text notes no longer appear in the audit trail.
