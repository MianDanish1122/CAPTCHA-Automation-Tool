# Test Report (Phase 7 final run)

Environment: Windows 10, Python 3.12, pytest, Playwright Chromium, Next.js 16.4.5, Tesseract 5.5.0. Provider tests used the real internet on 2026-11-07.

## Backend suite — `pytest tests/`

**445 passed, 1 skipped, 0 failed** (357 s). 446 collected = 333 (Phases 1–6B, all still passing) + 105 Phase 7 tests + **8 settings-privacy tests** (added after the demo rehearsal; see `PHASE_7_FINAL_ACCEPTANCE.md` addendum).

| File | Tests | Scope |
| :--- | :---: | :--- |
| `test_api_endpoints`, `test_captcha_intelligence`, `test_csv_importer`, `test_detection_fixtures`, `test_ocr_and_token`, `test_security`, `test_smart_crawler` | 71 | Phases 1–4 functionality (unchanged assertions) |
| `test_phase5_security` | 14 | auth, RBAC, SSRF basics, rate limit, audit |
| `test_phase6a_security` | 139 | H1–H4 SSRF/IP/rate-limit/fixture fixes, credentials, dependencies |
| `test_phase6b_security` | 75 | evidence auth, bootstrap, revocation, size/rate/job limits, review history, audit chain, redaction |
| `test_phase6b_final` | 34 | audit key rotation, Alembic migrations (incl. Phase 7 head), JWT migration, backup/restore |
| **`test_phase7_ocr`** | **33** | deterministic generator, split disjointness, dataset hash integrity, metrics, engine failure behaviour, hybrid fallback, accuracy floor on dev, API honesty (true labels, no fake records, persisted deterministic benchmark) |
| **`test_phase7_verification`** | **46** | mocked provider behaviour, outages, malformed responses, local validation, simulations never succeed, **live** official test keys (reCAPTCHA, hCaptcha, Turnstile ×3), persistence, auth |
| **`test_phase7_reliability`** | **26** | browser launch failure, timeouts, unreachable hosts, policy violations, unsupported CAPTCHAs, cancellation, DB/unhandled errors, auth failures, stats correctness and empty-state honesty |

Skipped (1): the symlink-escape fixture test (this Windows account cannot create symlinks).

Defects found by the Phase 7 tests (all fixed): browser-launch failure escaped as an exception and left a crawl `crawling`; a cancelled crawl stayed `crawling`; DB/unhandled errors had no safe handler; split ranges `test`/`test2` overlapped in *declaration* (no sample overlapped; ranges corrected); the dev database contained 21 pre-existing fake OCR rows (`ground_truth="SYNTHETIC"`) — now excluded from statistics and reported separately.

## Frontend production build — `npm run build`
Compiled successfully, TypeScript clean, **15/15 pages** prerendered (adds `/evaluation`, `/verification`). Lint not run.

## Browser E2E (Playwright, real Chromium, real backend, production frontend, isolated migrated DB)

| Script | Result | Evidence |
| :--- | :---: | :--- |
| `tests/e2e_phase7_browser.py` (evaluator workflow) | **30/30** | `evidence/phase7/e2e/e2e_report.json` + 10 screenshots + downloaded report |
| `tests/e2e_phase6b_browser.py` (security regression) | **32/32** | `evidence/phase7/regression_phase6b_browser_verification.json` |

The Phase 7 E2E drove: sign-in; empty-state dashboard with the 8 workflow steps; inspecting an owned local site with a production-keyed reCAPTCHA (queued for human review, not solved); discovered pages and authenticated screenshot evidence; OCR demo ×2 and a 20-sample persisted benchmark; four verification scenarios (official test keys → confirmed by provider; simulated expiry → labelled simulated; missing token → local validation; Turnstile "already spent" → genuine provider response); dashboard numbers compared with the API (pages, verification attempts, simulated vs provider-confirmed, held-out OCR table equal to the stored measurements, denominators on every block, time-range filter); report download; no page errors, failed requests, HTTP ≥ 400 or console errors. During development the script exposed three test-script/UI issues (stale result panel race, an ambiguous selector matching a step card instead of the download button, case of CSS-uppercased labels) — corrected; the product behaved correctly.

## Standalone evidence runs
- `python -m scripts.ocr_benchmark …` — held-out results in `evidence/phase7/ocr/` (see `PHASE_7_OCR_EVALUATION.md`).
- `python -m scripts.token_acquisition_demo` — reCAPTCHA and Turnstile test-widget tokens acquired and verified by the providers; hCaptcha widget not automated (`evidence/phase7/verification/token_acquisition.json`).

## Not run / not covered
Lint; fresh-virtualenv reinstall after Phase 7 (no new third-party dependency was added: the custom model uses NumPy/OpenCV/Pillow already declared); the older `run_acceptance_tests.py` / `verify_frontend_e2e.py`; load/performance testing; multi-process behaviour; Firefox/WebKit; real production CAPTCHA keys.

## Addendum — settings privacy fix (after the demo rehearsal)
`/api/websites/settings` no longer returns local absolute paths: `evidence_dir` → `evidence/`, `reports_dir` → `reports/`, `tesseract_cmd` → `tesseract` (the real configured values are used internally and unchanged). `tests/test_settings_privacy.py` (8 tests) asserts the safe values, the absence of drive/UNC/POSIX paths, profile-name segments, secrets and database location, frontend field compatibility, unchanged internal configuration with Tesseract still running through it, and unchanged 401/200 access control; 3 of them fail against the previous code. Re-run after the fix: backend **445 passed, 1 skipped**; frontend build 15/15; Phase 7 browser E2E **30/30**; Phase 6B browser regression **32/32**; demo rehearsal on a freshly reset isolated database **19/19** (new step S9b visits Settings), 0 leak findings, 0 console errors, 0 failed requests.
