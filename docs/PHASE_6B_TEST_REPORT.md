# Phase 6B — Test & Verification Report

All numbers come from commands executed during Phase 6B (Windows 10, Python 3.12, Chromium via Playwright).

## Results

| Run | Result |
| :--- | :--- |
| `pytest tests/` (project venv) after all 6B changes | **298 passed, 1 skipped, 0 failed** (156 s) |
| Collected | 299 = 85 (Phase 1–5) + 139 (Phase 6A) + **75 new (Phase 6B)** |
| `npm run build` after the frontend evidence/health changes | compiled; TypeScript clean; 13/13 static pages |

Skipped: the same Phase 6A symlink-escape test (this Windows account cannot create symlinks).

The first run of the new file had **2 failures**, both genuine defects fixed before the final run:
1. An oversized *chunked* body returned 400 instead of 413 (the framework converted the aborted read into a parse error). The middleware now forces 413.
2. A background job cancelled before its first step leaked its concurrency slot. Slots are now released from the task's done-callback.

Dependencies were not changed in 6B, so the fresh-virtualenv installation was not repeated; the suite ran in the project venv.

## Coverage of new tests (`tests/test_phase6b_security.py`, 75 tests)

| Item | Tests |
| :--- | :--- |
| Evidence auth | unauthenticated 401; old `/evidence/*` mount returns 404; operator can fetch; 10 traversal/out-of-scope paths (`../.env`, encoded, backslash, non-scans dirs, wrong extension, bad ids) all 404 |
| `/health` | public body is exactly `{"status":"healthy"}`; `/` leaks no config; details require auth |
| Bootstrap | 404 when no token configured; 403 for missing/wrong token with audit rows; success once then 400; weak password 422; **two concurrent attempts → exactly one 200**; short token rejected at production startup (isolated temp database for all of these) |
| Revocation | logout then same token → 401 "revoked"; logout-all kills every session and a new login works; admin revoke; deactivate blocks login and kills tokens; operators get 403; self-deactivation 400; unknown-user login performs a real bcrypt comparison |
| Client modes | sitekey extraction; official-test refused for production key / no key / mixed keys, accepted for the published Google test key; synthetic refused without image or with a real provider on the page; **API cannot hide a real reCAPTCHA behind `is_synthetic`**; real key + `is_official_test` still routes to human review |
| Size limits | oversize JSON by Content-Length → 413; oversize **chunked** → 413; HTML field limit 422 (two endpoints); invalid base64 400; non-image 400; 6000×6000 PNG bomb 413; oversized base64; token/enum field limits; valid image still accepted |
| Rate limits | verify-token and classify return 429 after the limit; admin operations limited |
| Job limits | concurrency limit, release after completion, per-user limit, foreground slot, shutdown cancellation; API returns 429 + `Retry-After` for crawls and batches when capacity is exhausted |
| Reviewer history | identity recorded for operator and admin decisions, ordered history with previous/new status and notes; `review_decisions` UPDATE/DELETE blocked by the database; notes not copied to audit |
| Audit chain | valid chain with correct genesis/links; DB blocks UPDATE/DELETE; **tamper detection** for modified entry (triggers dropped), deleted entry (sequence gap) and forged hash without the key; live-database verify endpoint reports valid; `limit` cap |
| Redaction | nested secret keys, JWT-shaped strings, URL userinfo/query, truncation, request-id sanitisation, fingerprint stability; failed login stores no attempted username; scan audit entry redacts URL query secrets |
| Headers | `nosniff`, `X-Frame-Options`, client request-id handling |

All 224 earlier tests pass unchanged (the only edit to existing test infrastructure is an autouse fixture in `conftest.py` that resets rate-limit buckets between tests).

## Not verified / known gaps

- **UI behavior was not exercised in a browser.** The blob-based screenshot loading and the health fallback compile and type-check, but I did not click through the dashboard. The reviewer identity/history is exposed by the API only.
- The audit chain lock is process-local; multi-process deployments are untested and unsupported until a DB-level lock is added.
- Audit-chain tests run on isolated temporary databases (tampering the live database would permanently break its chain); the live database is only checked for validity.
- The suite adds users (`t6b_*`) and review rows to the development database, as the Phase 5 tests already did.
- Rate limiting remains in-memory per process; background jobs are still lost on restart.
- Real-provider verification, brute-force timing measurements and load testing were not performed.
