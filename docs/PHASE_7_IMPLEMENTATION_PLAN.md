# Phase 7 — Implementation Plan

**Branch:** `phase-7-assignment-readiness` (from Phase 6B HEAD `6abbe79`). Security work from 6A/6B is not changed except where a gap is documented.

## 0. Source of truth: the original assignment

"Assignment 01 — CAPTCHA Solving & Verification Tool" (`CAPTCHA_Automation_Assignment_01_Updated (2).docx`). Marking weights: **Recognition/solving accuracy 30 %**, **Verification-token handling 20 %**, **Custom AI or authorized API integration 20 %**, **Reliability and error handling 15 %**, **Interface and reporting 10 %**, **Code quality and documentation 5 %**. Required deliverables: repository with setup instructions and env vars; working application on synthetic/owned challenges; at least one solving workflow and one official provider token-verification workflow; a 3–5 minute demo video (success *and* failure cases); short architecture explanation + cost breakdown for any third-party service. Bonus: multiple challenge types/providers, fallback handling, batch processing + accuracy statistics on a synthetic dataset, reusable API endpoint. Scope: synthetic / owned / official-test environments only; no bypass of anti-bot protection elsewhere.

Note: the demo video is a human deliverable. Phase 7 produces the script/checklist and a rehearsed, evidence-backed workflow but cannot record the video.

## 1. Baseline inspection (what exists, what is wrong)

| Area | Finding (from reading the code at `6abbe79`) | Gap vs. criteria |
| :--- | :--- | :--- |
| OCR (30 %) | `generate_synthetic_captcha` uses the *global* `random` (not reproducible); `benchmark_synthetic_ocr` generates fresh random samples on every call, so numbers are not comparable between runs; "character accuracy" is **position-wise** (`zip`), which collapses after one insertion/deletion; Tesseract is run with the generic page-segmentation mode and no glyph-level logic; no dataset files, no held-out split, no stored results. Phase 6A measured **20 % exact / 64.8 % char on 20 random samples** | accuracy, reproducibility, honesty of metrics |
| Evaluation records | `evaluate-handling` stored OCR records with `ground_truth="SYNTHETIC"`, `exact_match=False`, accuracy 0 regardless of reality | incorrect records |
| Verification (20 %) | `token_verifier` mixes four things in one response shape: live Google test-key calls, magic-string/flag **simulations**, local missing-token rejection, and an **offline fallback that returns `success: true` ("verified_offline_official_test_mode") when Google is unreachable**. Only Google reCAPTCHA is implemented; hCaptcha/Turnstile verification is absent. Results are not persisted, so no aggregate statistics | simulated vs provider conflated; fake success on outage |
| AI/API (20 %) | Custom pipeline = OpenCV preprocessing + Tesseract; no trained component; docs claim nothing about paid APIs but nothing documents it either | needs an actual custom model and an inventory |
| Reliability (15 %) | Many protections exist (SSRF, limits, revocation) but failure modes (browser launch, DB error, provider outage, OCR failure) are not systematically tested; unhandled exceptions would surface as raw 500s | error matrix + tests |
| Interface (10 %) | Pages exist; overview shows scan counts only; **no OCR/verification aggregates, no denominators, no verification page, no report that combines the evaluation** | genuine aggregate metrics |
| Docs (5 %) | Phase-by-phase docs; README still describes Phase 2-era features; no requirement mapping / user guide / API doc | consolidate |

## 2. Work packages (priority order, each: inspect → change → tests → evidence → commit)

1. **OCR (30 %)** — deterministic dataset generator (seeded; no global RNG), materialised dataset with SHA-256 manifest, **train / dev / held-out test** split by disjoint seed ranges; a benchmark script that reproduces the legacy baseline on the held-out set, runs preprocessing/OCR experiments **on the dev split only**, selects the configuration on dev, then evaluates **once** on the held-out test split; metrics = exact match, Levenshtein-based character accuracy, per-position accuracy, latency (mean/p50/p95), failure count, n; machine-readable JSON + report. A custom model (HOG features + small MLP in NumPy, trained on our own synthetic train split via the segmentation pipeline) is compared to improved Tesseract; the app uses the measured best, with a hybrid fallback. Correct the evaluation records.
2. **Verification (20 %)** — rewrite the verifier with an explicit `verification_mode` (`provider_live`, `provider_test_keys`, `simulated`, `local_validation`), providers reCAPTCHA / hCaptcha / Turnstile via their official `siteverify` endpoints and official test secrets (these give genuine provider-side outcomes, including Turnstile's "token already spent" = `timeout-or-duplicate`); remove the fake offline success; validate response shape; persist every attempt; verification matrix with real executed evidence.
3. **Custom AI / API inventory (20 %)** — architecture, dependency/API inventory, cost analysis (local vs external), explicit statement that no paid solver is integrated.
4. **Reliability (15 %)** — tests and fixes for browser launch failure, navigation timeout, unreachable host, redirect/policy violation, unsupported CAPTCHA, OCR failure, provider downtime/invalid response, job limits/cancellation, DB errors, auth failures; global safe error handler; error-handling matrix.
5. **Interface (10 %)** — `GET /api/stats/summary` computed only from persisted rows with explicit denominators and time ranges; Evaluation dashboard page (workflow steps 1–8), verification page, OCR benchmark view, evaluation report download. No mock numbers.
6. **Docs (5 %)** — README, requirement mapping, architecture, API doc, OCR evaluation, verification matrix, security summary, test report, deployment guide, user guide, known limitations, cost inventory.
7. **Acceptance** — full backend suite, frontend build, Playwright E2E (with screenshots into `evidence/phase7/`), weighted acceptance matrix.

## 3. Rules followed

- OCR is trained and evaluated only on images generated by this repository (owned/synthetic). No third-party CAPTCHA images are collected.
- Real reCAPTCHA / hCaptcha / Turnstile challenges are detected, classified and routed to human review; official **test** keys are used for verification demonstrations. No tokens are harvested or forged.
- No improvement is claimed unless measured on the **same held-out set** with the same metric code. Dev-set numbers are labelled as such.
- No deployment, no Phase 8.
