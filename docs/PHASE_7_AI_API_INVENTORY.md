# Phase 7 — Custom AI / API Inventory

## 1. Direct answers

| Question | Answer |
| :--- | :--- |
| Is a **paid external solver API** integrated? | **No.** None is integrated, configured, or called. No solver account, key or endpoint exists anywhere in the code or `.env.example`. |
| What is the "custom AI"? | A **locally trained character classifier** for the project's *own synthetic text CAPTCHAs*: segmentation + HOG features + a small neural network written in NumPy, trained here from seeds (no pretrained weights, no external model). A **Tesseract** (third-party OCR) pipeline is kept as the baseline and as the hybrid fallback. |
| Which external services are called at runtime? | Only the providers' official **siteverify** endpoints, and only when a verification is requested (reCAPTCHA, hCaptcha, Turnstile). Nothing else leaves the machine; no telemetry. |
| Does anything solve production CAPTCHAs? | **No.** reCAPTCHA / hCaptcha / Turnstile / interstitials are detected, classified and routed to human review. Official *test* modes are used for verification demos only. |

## 2. What is implemented locally

| Component | Location | Technique | Trained / tuned on |
| :--- | :--- | :--- | :--- |
| Synthetic CAPTCHA generator | `app/ocr/dataset.py` | Pillow: rotated glyphs, noise lines/dots, seeded | n/a |
| Ink mask + noise filter | `app/ocr/preprocess.py` | dark-pixel threshold + connected-component size filter (domain prior of the generator) | tuned on dev |
| Segmentation | `app/ocr/segment.py` | connected components, overlap merging, width-based splitting | rule fixed using dev errors |
| Features | `app/ocr/segment.py` | own NumPy HOG (9 bins, 4×4 cells, 2×2 blocks, L2-Hys) + width/height ratio, relative height, relative centre | — |
| **Glyph classifier** | `app/ocr/model.py`, weights `app/ocr/model/glyph_mlp_v1.npz` (346 KB) | 327→256 (ReLU)→32 (softmax), Adam, L2, mini-batch, written in NumPy | train split: 14 910 glyphs from 2 982 generated images (seeds 0–2 999) |
| Tesseract pipelines | `app/ocr/engines.py` | OpenCV preprocessing variants + `pytesseract` | configuration chosen on dev |
| Hybrid router | `app/ocr/engines.py` | custom first, Tesseract fallback on implausible segmentation / low glyph probability (<0.55) | threshold fixed a priori, not tuned on held-out data |
| CAPTCHA classification | `app/services/captcha_intelligence.py`, `browser_scanner.py` | **rule-based** DOM/script-marker detection (reCAPTCHA v2/invisible, hCaptcha, Turnstile, interstitials) — *not* machine learning | hand-written rules, tested on fixtures |
| Server validation of client-claimed modes | `captcha_intelligence.validate_client_assertions` | published test-key matching, image validation | — |
| Evaluation metrics | `app/ocr/metrics.py` | exact match, Levenshtein character accuracy, position accuracy, Wilson 95 % CI, latency percentiles | — |

## 3. Libraries and models

| Package (version in this environment) | Purpose | Local / external |
| :--- | :--- | :--- |
| numpy 2.5.4 | classifier, HOG, metrics | local |
| opencv-python 5.0.0.93 | image decoding, thresholds, components, Sobel | local |
| Pillow 13.0.0 | synthetic image generation, image validation | local |
| pytesseract 0.3.13 + **Tesseract 5.5.0** (`eng.traineddata`, third-party pretrained LSTM) | baseline/fallback OCR | local binary (not a cloud API) |
| playwright 1.64.1 (Chromium) | website inspection (always through the SSRF/egress guard) | local |
| httpx 0.28.1 | server-side provider verification calls | calls provider endpoints |
| FastAPI 0.162.0, SQLAlchemy 2.1.8, Alembic, PyJWT, bcrypt, pydantic | API, persistence, security | local |
| Next.js 16.4.5, React 19.3.0, Tailwind 4 | dashboard | local |

Pretrained models in the system: **only** Tesseract's bundled English LSTM. The custom glyph model has no pretrained component.

## 4. Provider / external API inventory

| Endpoint | Used by | When | Credentials | Cost to this project |
| :--- | :--- | :--- | :--- | :--- |
| `https://www.google.com/recaptcha/api/siteverify` | `token_verifier` | only when a verification is requested | published **test** secret by default; an operator may supply their own secret per request (never stored/returned) | none charged by the application (see `PHASE_7_COST_ANALYSIS.md`) |
| `https://api.hcaptcha.com/siteverify` | same | same | published test secret | same |
| `https://challenges.cloudflare.com/turnstile/v0/siteverify` | same | same | published dummy secrets (`1x…`, `2x…`, `3x…`) | same |
| Provider widget scripts (google.com/recaptcha, hcaptcha.com, challenges.cloudflare.com) | **only** `scripts/token_acquisition_demo.py`, on a page we serve locally with official TEST site keys | manual demo | test site keys | none |
| No other external API | — | — | — | — |

Scanned third-party pages are fetched through the guarded egress layer (SSRF policy, allow-list, DNS pinning); scanning external sites additionally requires `ENABLE_LIVE_SCAN=true` and an allow-listed domain — default off.

## 4a. Test-only functions (must not be mistaken for production behaviour)

| Function | Why it is test-only |
| :--- | :--- |
| Simulated verification scenarios (`simulate_status`, legacy `MOCK_*` tokens) | no provider call; can never succeed; labelled `simulated` |
| Official **test** mode (`is_official_test`) and the documented dummy tokens (`token_source: dummy_test_token`) | only honoured when every site key on the page is a published test key; proves the integration, not a solved challenge |
| `scripts/token_acquisition_demo.py` | obtains tokens from provider TEST widgets on an owned page |
| `fixture://` demo pages | only in development/test environments; path-validated |
| Synthetic CAPTCHA generator, `/api/captcha/ocr-demo`, `/ocr-benchmark` | operate on owned synthetic data |
| `mark_completed`/`ocr_inference` handling for uploaded images | an uploaded image has no known label → accuracy is never recorded for it |

## 4b. Functions that require human verification

| Situation | Handling |
| :--- | :--- |
| Production reCAPTCHA / hCaptcha / Turnstile detected (interactive, invisible or passive) | `HumanReviewRecord` created; operator decision stored with identity and history |
| Anti-bot interstitials (Cloudflare "Just a moment", Datadome, PerimeterX, AWS WAF) | `manual_investigation` review case |
| `is_official_test` requested for a page with a non-test key | flag refused → human review |
| Any result the operator doubts | review decisions are append-only and audited |

## 5. Honest capability statement

The custom model reaches 99.3 % exact match on 300 never-inspected held-out images **from the same synthetic generator** (docs/PHASE_7_OCR_EVALUATION.md). It has not been evaluated on any other CAPTCHA family, and it is not applied to third-party challenges.
