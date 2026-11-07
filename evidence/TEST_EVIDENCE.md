# Automated Test Evidence & Verification Audit

This document records the empirical verification and test results for the **CAPTCHA Inspection & Verification Tool**, corresponding directly to the automated test suite, live API tests, and visual screenshot evidence.

**Execution Environment**:
- Operating System: Windows 11 Pro (x64)
- Python Version: 3.12.3
- Browser Automation Engine: Playwright (Chromium Headless)
- OCR Engine: Tesseract OCR v5.5.0 (`C:\Program Files\Tesseract-OCR\tesseract.exe`)
- Image Processing: OpenCV v5.0.0 & Pillow v13.0.0
- Web Framework: FastAPI v0.162.0 with Uvicorn
- Persistence: SQLAlchemy 2.1.8 with SQLite
- Total Pytest Suite Status: **35 / 35 Tests PASSED (100%)**

---

## 1. Test Verification Matrix

| Test ID | Feature | Test Description | Input / Fixture | Expected Result | Actual Result | Status | Screenshot Filename | Notes & Limitations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-01** | Architecture | Project file and module organization | Repository layout | Modular folder hierarchy (`app/`, `tests/`, `docs/`, `evidence/`) | Clean separation of concerns with layered services | **PASS** | `01-project-structure.png` | Follows 12-factor application architecture. |
| **TC-02** | Documentation | OpenAPI / Swagger interactive UI | `GET /docs` | 200 OK, interactive endpoints rendered | All 10 routes categorized under Website & CAPTCHA tags | **PASS** | `02-swagger-ui.png` | Interactive schema validation with Pydantic. |
| **TC-03** | CSV Ingestion | Standard valid CSV upload & parsing | `valid_sample.csv` (2 rows) | `total_websites: 2`, `invalid_rows: 0`, HTTP 200 | 2 valid records parsed, normalized keys returned | **PASS** | `03-csv-import.png` | Supports UTF-8 and UTF-8-BOM encoding. |
| **TC-04** | Error Isolation | Malformed CSV row and URL validation | `invalid_sample.csv` (4 invalid rows) | Flags missing URLs, non-HTTP schemes, creds | Successfully isolates 4 invalid rows with line numbers | **PASS** | `04-invalid-csv-validation.png` | Batch continues gracefully despite individual row errors. |
| **TC-05** | Detection | Google reCAPTCHA v2 checkbox widget | `google_recaptcha.html` | `captcha_detected`, `is_active_challenge: true` | Detected `google_recaptcha` via DOM widget signature | **PASS** | `05-google-recaptcha-detection.png` | Distinguishes active widget from passive scripts. |
| **TC-06** | Detection | hCaptcha interactive challenge | `hcaptcha.html` | `captcha_detected`, provider: `hcaptcha` | Detected `hcaptcha` widget container | **PASS** | `06-hcaptcha-detection.png` | Verifies presence of interactive container `.h-captcha`. |
| **TC-07** | Detection | Cloudflare Turnstile challenge | `cloudflare_turnstile.html` | `captcha_detected`, provider: `cloudflare_turnstile` | Detected `cloudflare_turnstile` via `.cf-turnstile` | **PASS** | `07-cloudflare-turnstile-detection.png` | Identifies Cloudflare challenges API container. |
| **TC-08** | Detection | Clean contact form without CAPTCHA | `normal_contact_form.html` | `no_known_captcha_detected`, `contact_form_found: true` | Clean contact form verified, zero CAPTCHA indicators | **PASS** | `08-normal-contact-form.png` | Correctly prevents false positives on standard forms. |
| **TC-09** | Batch Engine | Asynchronous multi-site queue runner | 6 synthetic fixture records | Non-blocking execution, concurrency bounded | All 6 records processed, batch marked `completed` | **PASS** | `09-batch-processing.png` | Controlled concurrency via `asyncio.Semaphore`. |
| **TC-10** | Persistence | SQLite audit trail via SQLAlchemy | Batch ID foreign key query | Persistent records in `website_inspections` table | All itemized statuses, durations, and flags stored | **PASS** | `10-database-results.png` | Full audit trail survives application restarts. |
| **TC-11** | Vision & OCR | Synthetic CAPTCHA synthesis & Tesseract | Distorted 5-character string | Noise filtering + Otsu thresholding + OCR text | Ground truth matched, character accuracy computed | **PASS** | `11-ocr-demo.png` | Strictly for legacy distortion benchmarking. Modern CAPTCHAs use biometric telemetry. |
| **TC-12** | Token Verifier | Google reCAPTCHA test key verification | Official test key & simulated states | Valid passes, missing/invalid/reused rejected | Full 4-state matrix verified against Google specs | **PASS** | `12-token-verification.png` | Tested against official test keys and test simulation modes. |
| **TC-13** | Reporting | CSV compliance audit report generation | Completed batch results | Downloadable CSV with standard audit columns | Generated RFC 4180 CSV with UTF-8 BOM encoding | **PASS** | `13-final-csv-report.png` | Output saved in `reports/` and `evidence/reports/`. |

---

## 2. Test Execution Logs

Pytest complete test run output is permanently recorded at:
`evidence/test-results/pytest-output.txt`

### Summary Statistics:
- Total Test Cases: 35
- Passed: 35
- Failed: 0
- Execution Time: ~41 seconds
- Coverage: API, CSV parsing, SSRF & Security Guard, Detection Heuristics, Synthetic OCR, Token Verifier, Relational Database Models.
