# Assignment Requirements Mapping

Source: *Assignment 01 — CAPTCHA Solving & Verification Tool* (technical assessment). Status words: **Met** (implemented and evidenced), **Met with limits** (see limit), **Not met**.

## Core requirements

| Req | Assignment text (short) | Status | Implementation | Evidence |
| :-- | :--- | :---: | :--- | :--- |
| A1 | Identify the challenge type (synthetic text / image) | Met | `classify_captcha`; synthetic path requires a valid image and no provider markers | `tests/test_captcha_intelligence.py`, `test_phase6b_security.py` |
| A2 | Distinguish recognised from unsupported types | Met | unknown/interstitial → `unknown_challenge` → human review; unknown markup → `no_captcha` | `test_unsupported_challenges_*` |
| A3 | Identify reCAPTCHA / hCaptcha / Turnstile in a controlled test integration | Met | DOM/script detection incl. active vs passive vs invisible; fixtures + local site | `tests/fixtures/*.html`, E2E "results page shows the detected reCAPTCHA" |
| B | Solving engine (custom **or** approved API) | Met with limits | **Custom** OCR: segmentation + HOG/MLP + Tesseract fallback; confidence + latency reported | `docs/PHASE_7_OCR_EVALUATION.md` — 99.3 % exact on held-out synthetic set (**in-distribution only**) |
| C1 | Official token acquisition and server-side validation with test keys / owned site | Met with limits | tokens acquired from official **test** widgets on an owned page (reCAPTCHA, Turnstile) and verified via `siteverify`; hCaptcha via documented test token | `scripts/token_acquisition_demo.py`, matrix V1–V8; hCaptcha widget click not automated |
| C2 | Handle invalid, expired, reused, missing tokens gracefully | Met | invalid/expired/reused: **simulated** (labelled) and, for Turnstile, genuine provider `timeout-or-duplicate`; missing/malformed: local; outages/garbage: handled | `docs/PHASE_7_VERIFICATION_MATRIX.md` |
| C3 | Structured response without exposing secrets/tokens in logs | Met | fixed result schema; secrets never returned; tokens never stored; audit redaction | `test_secret_never_appears_in_result`, 6B redaction tests |
| D1 | Interface to upload/select a challenge, trigger processing, see results | Met | OCR Laboratory, Verification, Inspector pages | E2E screenshots 06–09 |
| D2 | Show total attempts, successes/failures, processing time, challenge type, provider/method | Met | Evaluation dashboard + report (attempts, outcomes by mode, OCR exact/char/latency, CAPTCHA types) | E2E `10_evaluation_dashboard.png`, report download |
| D3 | Estimated per-challenge cost where third-party services are used | Met (n/a) | no third-party solver; cost analysis shows $0 external cost and measured compute | `docs/PHASE_7_COST_ANALYSIS.md` |

## Technical expectations
Modular architecture (`app/ocr`, `services`, `routes`), secure configuration (`.env`, production validation, secrets never printed), sensible timeouts (navigation, provider 8 s, job limits), readable documentation (this set). **Met.**

## Required deliverables

| Deliverable | Status | Where |
| :--- | :---: | :--- |
| Repository with setup instructions and environment variables | Met | `README.md`, `.env.example` |
| Working application demonstrated on synthetic/owned challenges | Met | E2E 30/30 + 32/32, screenshots in `evidence/phase7/e2e/` |
| ≥ 1 solving workflow and ≥ 1 official token-verification workflow | Met | OCR engines; verification matrix |
| 3–5 minute demonstration video (success and failure cases) | **Not met (human step)** | script + checklist ready: `docs/USER_GUIDE.md`; recording must be done by a person |
| Short architecture explanation + cost breakdown | Met | `docs/SYSTEM_ARCHITECTURE.md`, `docs/PHASE_7_COST_ANALYSIS.md` |

## Bonus features
| Bonus | Status |
| :--- | :---: |
| Multiple challenge types / providers | Met (3 providers + synthetic text + interstitials) |
| Fallback handling if the primary method fails | Met (hybrid: custom → Tesseract; provider outage → `provider_unavailable`) |
| Batch processing + accuracy statistics on a supplied synthetic dataset | Met (dataset benchmark with CI, CSV batch scanning) |
| Reusable API endpoint for authorised integrations | Met (`/api/captcha/*`, JWT-protected; `docs/API_REFERENCE.md`) |

## Scope & acceptance conditions
Only synthetic, locally hosted, owned, or official-test environments are used for solving/verification. No bypass of anti-bot protection, token harvesting or unsolicited submission exists. A reviewer can run the tool, see a working supported solver, verify an official token flow, inspect failure handling, and read the source — see README and `docs/PHASE_7_FINAL_ACCEPTANCE.md`.
