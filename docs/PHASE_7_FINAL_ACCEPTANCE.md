# Phase 7 — Final Acceptance

Branch `phase-7-assignment-readiness` (from Phase 6B HEAD `6abbe79`). Phase 8 and deployment: **not started**.

## 1. Weighted acceptance matrix

Weights are from the original assignment. "Readiness" is my assessment of the evidence, **not a numeric mark**; the evidence column lists what can be opened and re-run.

| Criterion | Weight | Before Phase 7 (measured) | After Phase 7 (measured) | Readiness | Evidence | Main remaining gap |
| :--- | :---: | :--- | :--- | :---: | :--- | :--- |
| Recognition / solving accuracy | 30 % | 20 % exact / 64.8 % char on 20 random samples (positional metric) | **held-out n = 300 never-inspected: legacy 32.3 % → custom/hybrid 99.3 % exact, 78.9 % → 99.7–99.8 % char, 327 ms → ≈ 5 ms**; reproducible dataset, splits, CI, error analysis | **Strong** for the project's own synthetic CAPTCHAs | `PHASE_7_OCR_EVALUATION.md`, `evidence/phase7/ocr/` | result is in-distribution; no other CAPTCHA family measured |
| Verification-token handling | 20 % | reCAPTCHA only; simulations and offline fake success mixed with live calls; nothing persisted | 3 providers via official `siteverify`; explicit modes; no fake success; real provider responses for success/failure/"already spent"; token acquired from official test widgets (2 of 3); 21-scenario matrix; persisted | **Strong** (test-key level) | `PHASE_7_VERIFICATION_MATRIX.md`, `token_acquisition.json`, 46 tests | no real production keys exercised; hCaptcha widget acquisition not automated |
| Custom AI or authorized API | 20 % | Tesseract + OpenCV only; undocumented | custom trained model (segmentation + HOG + NumPy MLP, weights 346 KB, trained from seeds) + tuned Tesseract + hybrid fallback; inventory; **no paid solver, stated explicitly** | **Strong** | `PHASE_7_AI_API_INVENTORY.md`, `app/ocr/`, `model_training*.json` | classification is rule-based (not ML) |
| Reliability and error handling | 15 % | protections existed; failure modes untested; fake success on outage; stuck scans | 26 targeted tests + fixes (browser launch, cancel, DB, unhandled, outage); matrix | **Good** | `PHASE_7_RELIABILITY_REPORT.md` | no crash-recovery/queue, SQLite, single process |
| Interface and reporting | 10 % | no OCR/verification aggregates, no verification page | Evaluation dashboard (8-step workflow, denominators, time range, held-out table, report download), Verification page, OCR engine/split selection | **Good** | E2E 30/30, screenshots in `evidence/phase7/e2e/` | no charts over time; reviewer history not in UI |
| Code quality and documentation | 5 % | phase-by-phase docs, stale README | README, mapping, architecture, API (generated), user guide + demo checklist, security summary, limitations, deployment, cost, test report | **Good** | `docs/` | demo **video** not recorded (human) |

## 2. Measured improvements (same held-out set, same code)

| Metric (test2, n = 300) | Baseline `tesseract_legacy` | Final `hybrid` |
| :--- | :---: | :---: |
| Exact match | 32.3 % (95 % CI 27.3–37.8) | **99.3 %** (97.6–99.8) |
| Character accuracy | 78.9 % | **99.8 %** |
| Mean latency | 327 ms | **5.7 ms** |
| Failures (error/empty) | 4 | **0** |

Other measured changes: verification outage → previously `success:true` (fake), now `provider_unavailable`; scan stuck states → terminal; unhandled DB error → 503 without internals; fake OCR rows → excluded and no longer written.

## 3. Verification run (this session)

| Check | Result |
| :--- | :---: |
| Backend `pytest tests/` | **437 passed, 1 skipped, 0 failed** (438 collected: 333 earlier + 105 new) |
| Frontend `npm run build` | **passed** (15/15 pages) |
| Browser E2E — Phase 7 evaluator workflow | **30/30** |
| Browser E2E — Phase 6B security regression | **32/32** |
| Regressions from Phase 6B | **none found** (all 6A/6B tests, migrations, and the 6B browser suite pass) |

## 4. Phase 7 deliverables

`docs/PHASE_7_IMPLEMENTATION_PLAN.md`, `…_OCR_EVALUATION.md`, `…_VERIFICATION_MATRIX.md`, `…_AI_API_INVENTORY.md`, `…_RELIABILITY_REPORT.md`, `…_FINAL_ACCEPTANCE.md`, `…_COST_ANALYSIS.md`; plus `README.md`, `REQUIREMENTS_MAPPING.md`, `SYSTEM_ARCHITECTURE.md`, `API_REFERENCE.md`, `USER_GUIDE.md`, `SECURITY_SUMMARY.md`, `TEST_REPORT.md`, `DEPLOYMENT_GUIDE.md`, `KNOWN_LIMITATIONS.md`. Evidence: `evidence/phase7/{ocr,e2e,verification}/` and the 6B regression report.

## 5. Security architecture changes (documented reasons)

No change to the Phase 5–6B architecture except: provider verification can no longer return success without the provider (integrity fix), generic error handlers (information-leak fix), crawl state handling on failure/cancel (availability fix), additive tables via a guarded migration (`7a01phase7evaluation`).

## 6. Remaining limitations (also in `KNOWN_LIMITATIONS.md`)

1. OCR accuracy is for the **project's own generator** only.
2. `test` was inspected after first use; `test2` is the clean set.
3. Provider-live success path untested with real keys; test keys ≠ production proof; hCaptcha widget acquisition not automated.
4. Demonstration video not recorded.
5. Single-process state, SQLite, background jobs lost on restart, `localStorage` JWT without CSP, audit head must be anchored externally.
6. Deployment not performed; Phase 8 not started.

## 7. Completion statement

Implementation and measured evidence exist for all six weighted criteria. Phase 7 is **ready for your review** — it should not be called complete until you have accepted the limitations above and the demonstration video (a human deliverable) has been recorded.

## Addendum — settings privacy fix
Found during the demo rehearsal and fixed in a minimal change to `app/routes/websites.py` (+ tests, docs). Verification after the fix: backend 445 passed / 1 skipped; frontend build 15/15; Phase 7 E2E 30/30; Phase 6B E2E 32/32; demo rehearsal 19/19 with no leaks. No other behaviour changed.
