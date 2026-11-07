# Phase 6B — Final Test Report

All results below were produced by commands executed in this review (Windows 10, Python 3.12, Chromium via Playwright, Next.js 16.4.5).

## 1. Backend test suite

`pytest tests/` (project venv), final run after the last code change:

**332 passed, 1 skipped, 0 failed** (167 s). Collected 333 = 85 (Phase 1–5) + 139 (6A) + 75 (6B) + **34 new** (`tests/test_phase6b_final.py`).

Skipped: the symlink-escape test from 6A (this Windows account cannot create symlinks).

An earlier full run in this review had **1 failure**: `test_no_hardcoded_credentials_in_sources` flagged the literal text "Quick Test Credentials" inside my new browser-verification script. The script now uses a regex instead; the test and the full suite pass.

The 34 new tests:

| Condition | Tests |
| :--- | :--- |
| A — audit key | explicit, independent key configured in `.env`; status output holds no secret; key == JWT secret refused; production demands strong independent key (4 cases); entries record `key_id` and the key never reaches logs; **rotation** keeps old entries verifiable and reports "unknown key" when the old key is dropped; wrong key fails; unkeyed entry after keyed entries rejected |
| B — migrations | upgrade of a Phase 5 DB **stamped at the old stub** and one **never stamped** (rows preserved value-for-value; new columns defaulted; new tables, index and 4 triggers present; triggers enforce append-only); migrated DB works with the app audit chain (3 legacy rows reported as unchained); idempotent on an app-built DB and on re-run; **migrated schema == ORM schema**; guarded downgrades; downgrade 6B→baseline preserves original values and removes only 6B objects, re-upgrade works; baseline→base guarded |
| C — JWT | new accepted; pre-6B (no `ver`) rejected by default / accepted only in explicit grace mode; expired; no `exp`; no `jti`; `alg: none` and wrong signature; revoked `jti` (others unaffected); wrong `ver`; CLI invalidate-sessions kills tokens, login works again |
| E — audit/backup | consistent backup + head sidecar; restore needs confirmation and keeps the previous DB; tampered backup refused (live DB untouched); corrupt file refused; **rollback and truncation detected only with the external head**; head-hash mismatch; modified/deleted/forged records; `audit-verify` exit semantics |

## 2. Migration on real Phase 5 data

A copy of a genuine Phase 5 database (from the removed nested duplicate) was upgraded with `alembic upgrade head`:

| Table | Rows before → after | Values preserved |
| :--- | :---: | :---: |
| users | 6 → 6 | yes |
| audit_logs | 41 → 41 | yes |
| human_reviews | 97 → 97 | yes |
| url_scans | 58 → 58 | yes |
| discovered_pages | 170 → 170 | yes |
| batch_jobs | 26 → 26 | yes |
| website_inspections | 59 → 59 | yes |
| captcha_intelligence | 86 → 86 | yes |
| ocr_evaluations | 45 → 45 | yes |

`alembic_version` → `6b01phase6security`; four append-only triggers installed. (This real-data run was a one-off script on a private copy; the snapshot contains password hashes and is **not** in the repository. Its schema is in `tests/fixtures/phase5_schema.sql`.)

The development database was also checked: `python -m app.cli audit-verify` reported a valid chain (88 chained entries + 118 legacy) under the new independent key.

## 3. Browser verification (Playwright)

`tests/e2e_phase6b_browser.py` against the production frontend + real backend + isolated migrated database:

- Run 1: **31/32** — one genuine defect: double navigation after login (`net::ERR_ABORTED`). Fixed in `frontend/app/login/page.tsx`.
- Run 2 and Run 3 (after rebuilding / after the script wording fix): **32/32 passed**.

Checks (all passing): no credential panel on login; operator login → dashboard; protected screenshot renders through an authenticated blob; request carried bearer token; evidence → 401 without token / with garbage token, 404 for the legacy `/evidence` path and 3 traversal/out-of-scope paths, 200 `image/png` for the operator; `/health` is exactly `{"status":"healthy"}` with none of 7 sensitive markers; `/api/health/details` needs auth; operator 403 on audit logs, cannot create users, sees no audit section; logout clears storage and redirects, **old token → 401 "revoked"**, cannot fetch evidence; signed-out navigation redirects; admin sees the audit trail, 200 audit logs, **chain verification valid**, health details; neither test password appears in the audit log; no page errors, no failed requests, no HTTP ≥ 400 for application requests, no console errors. Evidence: `evidence/phase6b/browser_verification.json` + 5 screenshots (the report contains no credentials; verified by search).

## 4. Frontend production build

`npm run build` after the login-page change: compiled, TypeScript clean, 13/13 static pages. (Lint not run.)

## 5. What was not run / not covered

- `tests/run_acceptance_tests.py`, `tests/verify_frontend_e2e.py`, `capture_evidence.py`, `tests/capture_phase5_evidence.py` — older scripts that start their own stack; not re-run. The new browser script covers the security-relevant flows.
- Fresh-virtualenv installation was not repeated (no dependency changes since 6A; Alembic was already declared).
- Browser verification ran on Chromium only, at 1440×900, against a **development-mode** backend on an isolated SQLite database; no real third-party sites were scanned.
- Load/concurrency behavior of the audit chain with multiple processes is untested (documented as unsupported).
- The suite still adds test users/reviews to the development database.
