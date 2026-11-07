# Implementation Plan & Execution Roadmap

This roadmap governs the incremental enhancement of the CAPTCHA Automation Tool without disrupting previously verified features.

## Milestone Status Overview

| Phase | Milestone Description | Target Modules | Status |
| :--- | :--- | :--- | :--- |
| **01** | Architecture Inspection & Docs | `.env`, `requirements.txt`, `docs/*` | COMPLETED |
| **02** | Local Test Fixtures | `tests/fixtures/*.html` | IN PROGRESS |
| **03** | Configuration & SQLite Persistence | `app/config.py`, `app/database.py`, `app/models.py` | PENDING |
| **04** | Security Guard & SSRF Protection | `app/services/security_guard.py` | PENDING |
| **05** | Enhanced Scanner & Detection Engine | `app/services/browser_scanner.py` | PENDING |
| **06** | Batch Processing & Reporting Pipeline | `app/services/batch_processor.py`, `app/services/report_generator.py` | PENDING |
| **07** | Synthetic OCR & Token Verifier | `app/services/ocr_service.py`, `app/services/token_verifier.py` | PENDING |
| **08** | API Routes & FastAPI Integration | `app/routes/websites.py`, `app/routes/captcha.py`, `app/main.py` | PENDING |
| **09** | Automated Pytest Suite & Coverage | `tests/test_*.py` | PENDING |
| **10** | Genuine Screenshots & Evidence Package | `evidence/screenshots/*.png`, `evidence/TEST_EVIDENCE.md` | PENDING |

---

## Detailed Phase Breakdown

### Phase 2: Local Test Fixtures
- Create synthetic and locally controlled HTML fixtures under `tests/fixtures/`:
  - `normal_contact_form.html`: Standard contact form with name, email, message inputs and no CAPTCHA.
  - `google_recaptcha.html`: Form containing active `.g-recaptcha` checkbox container and official test sitekey.
  - `invisible_recaptcha.html`: Form containing invisible reCAPTCHA button and script triggers.
  - `hcaptcha.html`: Form containing active `.h-captcha` container and script tags.
  - `cloudflare_turnstile.html`: Form with `.cf-turnstile` container and Cloudflare challenges script.
  - `unknown_challenge.html`: Simulates an anti-bot challenge interstitial (e.g. Cloudflare "Just a moment...", Datadome/PerimeterX challenge block).

### Phase 3: Configuration & Database Persistence
- `app/config.py`: Implement type-safe configuration using `python-dotenv` and Pydantic with fallback defaults.
- `app/database.py`: SQLAlchemy engine, session maker, and database auto-initialization (`init_db`).
- `app/models.py`: Declarative ORM models for `BatchJob` and `WebsiteInspection`.

### Phase 4: Security Guard & SSRF Protection
- Validate URL scheme (`http` / `https` only).
- Disallow credentials or anomalous ports in URLs.
- DNS resolution check: Disallow private IP addresses (RFC 1918, 127.0.0.1, localhost, link-local 169.254.x.x, IPv6 loopback).
- Check against domain allowlist if configured.
- Reject live scanning if `ENABLE_LIVE_SCAN=false`.

### Phase 5: Browser Scanner Enhancement
- Distinguish active challenge presentation from passive script markers.
- Implement contact page discovery heuristics (scanning internal links for `/contact`, `/contact-us`, etc.).
- Maintain backwards compatibility with `inspect_local_demo`.
- Add context-level browser pooling to eliminate full Chromium restarts per page.

### Phase 6: Batch Processor & Report Generator
- Implement batch queue runner with concurrency semaphore.
- Support batch execution of up to 200 URLs with per-item fault tolerance.
- Persist real-time progress and summary to SQLite.
- Generate structured CSV report matching interviewer criteria.

### Phase 7: Synthetic OCR & Token Verifier
- Synthetic CAPTCHA generation using Pillow (distorted fonts, background noise lines, salt & pepper dots).
- OpenCV image preprocessing (Gaussian blur, grayscale, Otsu thresholding, morphological closing).
- Tesseract OCR inference with timing, confidence metrics, and limitation notes.
- Server-side verification for Google reCAPTCHA test keys against `https://www.google.com/recaptcha/api/siteverify`.

### Phase 8: API Integration
- Wire all new endpoints into FastAPI.
- Ensure all previously verified endpoints remain unmodified and fully functional.

### Phase 9 & 10: Pytest Suite & Evidence Verification
- Execute automated tests with zero failures.
- Automate genuine screenshot capture via Playwright headless browser.
- Deliver `TEST_EVIDENCE.md` and submission artifact bundle.
