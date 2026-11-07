# Known Limitations

Stated plainly so the results are not over-read.

## Recognition / solving
1. **The custom OCR is validated only on this project's own synthetic generator** (99.3 % exact on 300 never-inspected images). Other fonts, stronger distortion, overlapping glyphs, colour-based noise, or different lengths are untested; the dark-ink mask relies on the generator's property that glyphs are darker than noise.
2. **Two held-out sets were used.** `test` was inspected after its first evaluation; `test2` is the clean headline set (`PHASE_7_OCR_EVALUATION.md` §6).
3. Residual errors are segmentation merges of adjacent wide letters (2/300 on `test2`).
4. Tesseract tuning used 100 dev samples; differences of a few points between Tesseract settings are inside the noise.
5. Only Arial-rendered held-out images were measured.
6. Confidence of the custom model is a softmax statistic, not a calibrated probability.
7. Real third-party CAPTCHAs are intentionally **not** solved; image/audio/behavioural challenges are out of scope.

## Verification
8. The PROVIDER-LIVE success path (real token, real site key) was **not exercised** (no real keys); it is covered by mock and by live rejection of an invalid secret.
9. Official test keys prove integration, not human solving; their behaviour is defined by the providers and may change (live tests skip when offline).
10. hCaptcha widget-driven token acquisition was not automated (checkbox selector); hCaptcha verification itself is tested with the documented test token.
11. Simulated invalid/expired/reused are simulations; only Turnstile's "already spent" test secret gives a genuine provider-side reused/expired response.

## Operations
12. **Single-process design:** audit-chain lock, rate limiter, job registry are in memory; multiple workers or hosts are unsupported until shared stores/locks exist.
13. Background jobs are lost on restart; a hard kill can leave a scan in `crawling` (no startup reaper).
14. SQLite only; audit triggers are SQLite-specific.
15. **Audit head must be anchored externally** (write-once storage) to detect truncation/rollback; legacy pre-chain audit rows are not tamper-evident.
16. JWT stored in `localStorage` (XSS-exposed), 60-minute lifetime, no CSP yet.
17. Reviewer identity/decision history is API-only (not shown in the UI).
18. Deployment (reverse proxy, TLS, containers) is documented but **not performed**.

## Deliverables
19. The 3–5 minute demonstration video must be recorded by a person (script and checklist: `docs/USER_GUIDE.md`).
20. Older scripts (`tests/run_acceptance_tests.py`, `verify_frontend_e2e.py`, `capture_evidence.py`) pre-date the security changes and were not re-run; the Phase 6B and Phase 7 Playwright scripts supersede them.
