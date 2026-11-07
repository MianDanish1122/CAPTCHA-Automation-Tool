# Final Functional Test Report

Date: 2026-11-07. Branch `phase-7-assignment-readiness`. Baseline preserved: commit `f5c7df8`, tag `baseline-before-real-world-qa`, logs in `evidence/final_qa/baseline/`. The implementation is in commit `023739c`; the compliance and reproducibility fixes that followed are in the next commit (`9bb8808`).

## Final results (after all fixes)

| Suite | Baseline | Final |
|---|---|---|
| Backend `pytest tests` | 445 passed, 1 skipped | **625 passed, 1 skipped, 0 failed** (+180 new tests) |
| Frontend `npm run build` | 15/15 | **15/15**, TypeScript clean |
| Browser: Phase 7 evaluator workflow | 30/30 | **30/30** |
| Browser: Phase 6B security regression | 32/32 | **32/32** |
| Demo rehearsal | 19/19 | **19/19**, 0 leaks, 0 console errors |
| Browser: batch workflow (new) | n/a | **16/16** (`tests/e2e_realworld_batch_ui.py`) |

**The skipped test** is `tests/test_phase6a_security.py:110` (`test_fixture_symlink_escape_rejected`). It creates a symbolic link that points outside the fixtures folder to prove that the fixture loader refuses to follow it. Windows only allows symlink creation for elevated users or with Developer Mode, so on this machine the test skips itself ("Symlink creation not permitted on this system"). The baseline run also had exactly one skip (its log does not name the test; this is the only symlink-dependent skip in the suite). It is not a failure, but the symlink-escape check itself was **not exercised on this machine**; the other fixture-path checks (name allow-list, traversal and absolute-path rejection) are covered by passing tests.

## Earlier attempts that did NOT pass (kept for honesty)

The final numbers above are from the last complete runs. Along the way:

| Attempt | What happened | Cause and resolution |
|---|---|---|
| Backend suite, after the migration was added | 4 failed, 615 passed | The four Phase 6B migration tests asserted the old head revision. Constant updated to `8a01realworldqa`; no assertion weakened. |
| Backend suite, first run with the isolated test database | 1 failed, 624 passed | `test_realworld_stage4_form_probe`: a name field came back empty. Not reproduced afterwards (the file then passed 3 times alone). I raised the form probe's per-field fill timeout from 2 s to 5 s on the assumption of a timing issue under load; **the cause was not proven**. The next full run passed. |
| PowerShell runner, first use | All four suites reported FAIL | Bug in my runner script (it returned console output together with the exit code). Fixed before any suite result was counted. |
| Phase 6B browser, second use | 31/32 (`admin sees audit trail section in Settings`) | A page was loaded immediately after login. A wait for the page to settle was added to the script; rerun 32/32. |
| Batch UI browser, second use | Timed out on the file input | Same post-login timing problem; same fix; rerun 16/16. |
| Batch UI browser, very first run | Crashed the page | A genuine pre-existing defect (batch screen read `batchJob.id`, which the API did not return). Fixed in the API; see "Defects found" below. |

The post-login timing failures might point to a small race in the application's login guard; this was not investigated.

## Test environment and reproducibility

- **Isolated test database.** `tests/conftest.py` now creates a throw-away SQLite file in the system temp folder before the application is imported and deletes it at exit. An explicitly exported `DATABASE_URL` is respected. Verified: `data/captcha_tool.db` had an identical size and timestamp before and after full runs, so the development database is not read or written by `pytest tests`.
- **Browser suites.** `scripts/e2e/run-browser-suites.ps1` (Windows PowerShell 5.1+) runs `phase7`, `phase6b`, `batch`, `demo` or `all` (`-Build` runs the frontend build first). Each suite gets its own temporary database and random credentials generated in memory (none are hard-coded or written to disk). It refuses to start if ports 8000/3000 are in use and stops only the processes it started. Exact manual commands are in `scripts/e2e/README.md`.
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\e2e\run-browser-suites.ps1 -Suite all -Build
un-browser-suites.ps1 -Suite all -Build
  ```
- **Output directory.** The runner sets `E2E_OUT_DIR` to `.e2e_runs\<timestamp>` (git-ignored). Screenshots, JSON reports and server logs from a regression run go there, so the committed evidence under `evidence/` is not rewritten. If `E2E_OUT_DIR` is not set, the suites write to their historical `evidence/...` locations as before.
- The **final browser results above were produced through this runner** (Phase 7, demo: full run; Phase 6B and batch UI: after the post-login fix).

No existing test was removed or weakened. One constant changed: `HEAD` in `tests/test_phase6b_final.py` now names the new migration head `8a01realworldqa` (the four migration tests assert the head revision; the new additive migration legitimately moves it).

## New tests by stage
| Stage | File | Covers |
|---|---|---|
| 1 | `test_realworld_stage1_network_policy.py` | apex/www, allow-list matching, provider policy (lookalikes, http, credentials, wrong paths, POST), guard integration, read-only and lockdown in real Chromium |
| 2 | `..._stage2_detection.py` | classifier tables; delayed JS, script-only v3, iframe, no-CAPTCHA, text-mention regression |
| 3 | `..._stage3_batch.py` | employer CSV (200 rows), columns, invalid rows, labels, categories, robots matrix, pacing, migration, end-to-end pipeline with human-review records, screenshots, robots stop, continue-after-failure |
| 4 | `..._stage4_form_probe.py` | structure capture, synthetic fill, zero requests reaching a hostile page's server, honeypot/consent/hidden/CAPTCHA fields untouched |
| 5 | `..._stage5_evaluation.py` | formula injection, report columns, eligible-only metrics, API + downloads, manual launch keeps CSV context |
| 6 | `..._stage6_token_pages.py` | provider isolation on the test-key pages |

## Defects found by this QA and fixed
1. hCaptcha test-key acquisition always failed: three providers on one page; hCaptcha's reCAPTCHA-compat layer rendered a Google widget. Fixed (one page per provider, `recaptchacompat=off`); now 3/3 verified by the providers.
2. Batch scan results table read fields the API never returned (`status`, `forms_found_count`).
3. **CSV Batch Manager crashed when a scan started** (`batchJob.id` undefined; API returned only `batch_id`). Reports-page export links had the same undefined id. API now returns `id` and `completed_at`.
4. Batch/Reports CSV downloads were plain links that could not send the bearer token; replaced by authenticated downloads (verified by real downloads).
5. Audit CSV had no formula-injection protection.
6. apex → www redirects were rejected as cross-domain (49 of 200 CSV rows differ only by `www.`).
7. Provider widgets could never load under the domain-only guard.
8. Static detector reported a provider from a bare text mention (Breadtopia).

## Not covered in this stage
Live regression of Settings/Audit/Users/OCR was by the existing suites only. Live inspection of the 197 CSV sites that were not approved was not performed. The Breadtopia live evidence file was not regenerated after fix 8.
