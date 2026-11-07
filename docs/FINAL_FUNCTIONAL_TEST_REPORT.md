# Final Functional Test Report

Date: 2026-11-07. Branch `phase-7-assignment-readiness`, working tree uncommitted. Baseline preserved: commit `f5c7df8`, tag `baseline-before-real-world-qa`, logs in `evidence/final_qa/baseline/`.

## Results

| Suite | Baseline | Final |
|---|---|---|
| Backend `pytest tests` | 445 passed, 1 skipped | **621 passed, 1 skipped, 0 failed** (+176 new tests) |
| Frontend `npm run build` | 15/15 | **15/15**, TypeScript clean |
| Browser: Phase 7 evaluator workflow | 30/30 | **30/30** |
| Browser: Phase 6B security regression | 32/32 | **32/32** |
| Demo rehearsal | 19/19 | **19/19**, 0 leaks, 0 console errors |
| Browser: batch workflow (new) | n/a | **16/16** (`tests/e2e_realworld_batch_ui.py`, screenshots in `evidence/final_qa/batch_ui/`) |

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
