# Phase 7 — Cost Analysis

## Summary

| Item | Cost to run the application |
| :--- | :--- |
| Third-party CAPTCHA-solving API | **none — no solver is integrated** |
| Per-challenge cost of the custom OCR | **no per-challenge fee**; ≈ 4.5 ms mean CPU wall-clock per challenge (hybrid, measured) |
| Provider verification calls (reCAPTCHA / hCaptcha / Turnstile `siteverify`) | the application adds **no charge**; the demo uses the providers' free published test keys. Production use would be governed by each provider's own terms/pricing for the operator's real keys — **not researched or assumed here** |
| Software licences | all dependencies are open source (Tesseract: Apache-2.0; others per their licences) |
| Hosting | **not part of Phase 7** (no deployment performed); no hosting cost is claimed |

The assignment asks for a cost breakdown "for any third-party service". Since none is used, the breakdown is: external service cost = **0**, because there is no external solver; what remains is local compute and the (optional) provider verification calls.

## Local processing cost (measured, not estimated)

Measured on the held-out `test2` set (n = 300), Windows 10 desktop, single thread, sequential:

| Engine | Mean latency / challenge | p95 |
| :--- | :---: | :---: |
| `custom_mlp` | 4.5 ms | 5.7 ms |
| `hybrid` (default) | 5.7 ms | 8.3 ms |
| `tesseract_tuned` | 246.7 ms | 409.1 ms |
| `tesseract_legacy` (previous default) | 327.3 ms | 674.5 ms |

Cost per challenge = CPU-time × your machine's hourly price. With `c` = price of one CPU-core-hour:

```
cost_per_challenge = (latency_ms / 3 600 000) × c
hybrid:  5.7 / 3 600 000 × c  ≈ 1.6 × 10⁻⁶ × c     (the previous Tesseract default was ≈ 57× more expensive)
```

(No hourly price is assumed; plug in your own.) Memory: the model is 346 KB; Tesseract adds a separate process per call (only in the baseline/fallback path).

## Training cost

One-off: ≈ 55 s of CPU for 60 epochs on 14 910 glyphs (`model_training.json`), plus ≈ 10 min for the full dev experiment grid and ≈ 6 min for a full held-out evaluation. Repeatable with the commands in `PHASE_7_OCR_EVALUATION.md`.

## Provider verification calls

| Mode | Calls provider? | Cost basis |
| :--- | :---: | :--- |
| `provider_test_keys` | yes | free, published test keys |
| `provider_live` | yes | the operator's own provider account/terms |
| `simulated`, `local_validation` | no | none |

Each verification is a single HTTPS POST (8 s timeout, configurable `VERIFY_TIMEOUT_SECONDS`); failures are not retried automatically, so a provider outage cannot multiply calls.

## If a paid solver were ever added (not recommended, not done)

It would need: written authorization for the target challenges, a documented per-solve price and monthly cap, error handling for refunds/timeouts, and a cost field in every result. None of that exists, deliberately: for third-party production CAPTCHAs the design is detect → human review.
