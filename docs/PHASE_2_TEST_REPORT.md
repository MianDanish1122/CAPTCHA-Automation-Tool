# Technology Brainz — CAPTCHA Inspector
## Phase 2: Test & QA Verification Report

## 1. Overview & Execution Summary

- **Date**: November 7, 2026
- **Target Branch**: `phase-2-smart-crawler`
- **Environment**: Python 3.12.3 on Windows 11 (win32)
- **Framework**: `pytest-9.2.0`, `anyio-4.16.0`, `playwright-1.58.0`
- **Database**: SQLite 3 (`data/captcha_tool.db`)
- **Total Test Cases**: 52
- **Passed**: 52 (100%)
- **Failed**: 0 (0%)
- **Execution Time**: 31.43 seconds

---

## 2. Complete Test Suite Matrix

### A. Smart Crawler Engine & Heuristics (`tests/test_smart_crawler.py`)

| Test Function | Verification Scope | Status |
| :--- | :--- | :--- |
| `test_normalize_url_basic` | Lowercasing hosts, removing redundant default ports (`:80`, `:443`), stripping trailing slashes. | **PASSED** |
| `test_normalize_url_strips_tracking_params` | Removal of `utm_source`, `utm_medium`, `fbclid`, `gclid` while preserving essential functional query parameters (`id=123`). | **PASSED** |
| `test_normalize_url_relative_resolution` | Resolution of relative paths (`/contact-us`, `help.html`) against base URL. | **PASSED** |
| `test_normalize_url_invalid_schemes` | Rejection of non-web schemes (`javascript:`, `mailto:`, `tel:`, `#`). | **PASSED** |
| `test_is_same_domain` | Subdomain and root domain matching; rejection of foreign hostnames. | **PASSED** |
| `test_calculate_page_score_contact_page` | High contact score (>=0.70) when path, anchor, title, and form with textarea are detected. | **PASSED** |
| `test_calculate_page_score_support_page` | High support score (>=0.60) when path, title, and help desk keywords are detected. | **PASSED** |
| `test_calculate_page_score_general_landing_page` | General page classification (>=0.80) for root landing pages without contact forms. | **PASSED** |
| `test_validate_redirect_url_same_domain` | Permitted redirects within authorized same-domain scope. | **PASSED** |
| `test_validate_redirect_url_blocks_cross_domain` | Detection and interception of cross-domain redirects (e.g. to foreign attacker hosts). | **PASSED** |
| `test_validate_redirect_url_blocks_cloud_metadata` | Immediate rejection of redirects pointing to AWS/GCP cloud metadata IP (`169.254.169.254`). | **PASSED** |
| `test_crawler_full_discovery_pipeline` | Real Playwright Chromium crawling of multi-page site: homepage discovery, candidate prioritization, form inspection, Google reCAPTCHA detection, external link rejection, screenshot capture, and database persistence. | **PASSED** |
| `test_crawler_respects_max_pages_limit` | Strict adherence to `max_pages=2` limit even when additional outgoing links exist. | **PASSED** |
| `test_crawler_respects_depth_zero` | Crawling strictly confined to root page when `max_depth=0` is configured. | **PASSED** |
| `test_api_inspect_url_rejected_security` | Endpoint `POST /api/websites/inspect-url` returns HTTP 400 with SSRF policy explanation for unauthorized domains. | **PASSED** |
| `test_api_inspect_url_and_query_results` | End-to-end API lifecycle: `POST /inspect-url`, `GET /scans/{id}`, and `GET /scans/{id}/results`. | **PASSED** |
| `test_api_scans_not_found` | Endpoint `GET /api/websites/scans/{id}` correctly returns HTTP 404 for nonexistent scan IDs. | **PASSED** |

### B. Fixture CAPTCHA Detection (`tests/test_detection_fixtures.py`)

| Test Function | Target Provider / Scenario | Status |
| :--- | :--- | :--- |
| `test_fixture_normal_contact_form` | Standard HTML form without CAPTCHA markers. | **PASSED** |
| `test_fixture_google_recaptcha` | Google reCAPTCHA v2 checkbox widget + `human_review_required=True`. | **PASSED** |
| `test_fixture_invisible_recaptcha` | Google reCAPTCHA invisible token binding. | **PASSED** |
| `test_fixture_hcaptcha` | hCaptcha container + API script detection. | **PASSED** |
| `test_fixture_cloudflare_turnstile` | Cloudflare Turnstile `cf-turnstile` widget detection. | **PASSED** |
| `test_fixture_unknown_challenge` | Anti-bot interstitial challenge screen (`unsupported_challenge`). | **PASSED** |

### C. Backend API Integration (`tests/test_api_endpoints.py`)

| Test Function | Endpoint | Status |
| :--- | :--- | :--- |
| `test_home_endpoint` | `GET /` | **PASSED** |
| `test_health_endpoint` | `GET /health` | **PASSED** |
| `test_api_import_valid_csv` | `POST /api/websites/import` | **PASSED** |
| `test_api_import_invalid_file_extension` | `POST /api/websites/import` (non-csv) | **PASSED** |
| `test_api_inspect_demo` | `POST /api/websites/inspect-demo` | **PASSED** |
| `test_api_inspect_demo_batch` | `POST /api/websites/inspect-demo-batch` | **PASSED** |
| `test_api_scan_batch_and_report_lifecycle` | `POST /scan-batch`, `GET /batches/{id}`, report download | **PASSED** |
| `test_api_ocr_demo` | `POST /api/captcha/ocr-demo` | **PASSED** |
| `test_api_token_verification` | `POST /api/captcha/verify-token` | **PASSED** |

### D. CSV Importer Engine (`tests/test_csv_importer.py`)

| Test Function | Verification Scope | Status |
| :--- | :--- | :--- |
| `test_import_valid_csv` | RFC 4180 parsing, column mapping, URL normalization. | **PASSED** |
| `test_import_header_aliases` | Robust alias recognition (`Company`, `Website`, `Domain`). | **PASSED** |
| `test_import_missing_required_headers` | Graceful failure on missing mandatory columns. | **PASSED** |
| `test_import_invalid_rows` | Row-level validation and error tracking without pipeline crash. | **PASSED** |
| `test_import_empty_file` | Rejection of 0-byte uploaded files. | **PASSED** |

### E. OCR Benchmarking & Google reCAPTCHA Verification (`tests/test_ocr_and_token.py`)

| Test Function | Verification Scope | Status |
| :--- | :--- | :--- |
| `test_synthetic_captcha_generation` | TrueType font rendering, distorted canvas creation. | **PASSED** |
| `test_opencv_preprocessing` | Grayscale conversion, bilateral filtering, Otsu binarization. | **PASSED** |
| `test_ocr_single_run` | Tesseract v5 LSTM PSM 7 execution with non-zero confidence. | **PASSED** |
| `test_ocr_benchmark_dataset` | Honest ground-truth character and exact match reporting. | **PASSED** |
| `test_token_verification_missing_token` | Rejection of empty verification tokens. | **PASSED** |
| `test_token_verification_invalid_token` | Handling of malformed verification tokens. | **PASSED** |
| `test_token_verification_reused_token` | Handling of duplicate or expired token verification requests. | **PASSED** |
| `test_token_verification_official_test_approved` | Official Google test key validation (`6LeIxAc...`). | **PASSED** |

### F. Security & SSRF Defense Guard (`tests/test_security.py`)

| Test Function | Verification Scope | Status |
| :--- | :--- | :--- |
| `test_ip_allowed_public_ips` | Acceptance of public DNS addresses (`8.8.8.8`, `1.1.1.1`). | **PASSED** |
| `test_ip_rejected_private_ips` | Rejection of RFC 1918 subnets (`10.0.0.1`, `192.168.1.1`, `172.20.0.5`). | **PASSED** |
| `test_ip_rejected_loopback` | Rejection of loopback addresses (`127.0.0.1`). | **PASSED** |
| `test_ip_rejected_cloud_metadata` | Immediate rejection of cloud metadata (`169.254.169.254`). | **PASSED** |
| `test_validate_target_url_invalid_scheme` | Rejection of non-http schemes (`file:///etc/passwd`, `javascript:`). | **PASSED** |
| `test_validate_target_url_credentials` | Rejection of embedded credentials (`admin:pass@host`). | **PASSED** |
| `test_validate_target_url_live_scan_disabled` | Rejection of unauthorized domains when live scanning is off. | **PASSED** |

---

## 3. Standalone Verification Scripts

### Script 1: `python test_csv_importer.py`
```
========== CSV IMPORT TEST ==========
Success: True
Total valid websites: 2
Invalid rows: 2

Valid Websites:
{'company_name': 'Example Company', 'website_url': 'https://example.com', 'status': 'pending'}
{'company_name': 'Demo Store', 'website_url': 'https://demo.com', 'status': 'pending'}

Errors:
{'row': 4, 'reason': 'Invalid website URL.'}
{'row': 5, 'reason': 'Company name or website URL is missing.'}
=====================================
Result: PASS
```

### Script 2: `python test_browser_scanner.py`
```
========== PROVIDER DETECTION TESTS ==========
Test: Google reCAPTCHA -> Detected: ['google_recaptcha'] -> Result: PASS
Test: hCaptcha -> Detected: ['hcaptcha'] -> Result: PASS
Test: Cloudflare Turnstile -> Detected: ['cloudflare_turnstile'] -> Result: PASS
Test: No CAPTCHA -> Detected: [] -> Result: PASS
==============================================
Tests passed: 4/4
==============================================
Result: PASS
```

---

## 4. Evidence Verification & Artifacts

- **Crawler Evidence Screenshots**: Verified on disk under `evidence/scans/<scan_id>/`:
  - `page_1_root.png` (800x1280 render of homepage navigation)
  - `page_2_contact.png` (800x1280 render of contact page with reCAPTCHA widget)
  - `page_3_support.png` (800x1280 render of support/FAQ portal)
  - `page_4_about.png` (800x1280 render of general about page)
- **Database Records**: Confirmed persistence in SQLite (`url_scans` and `discovered_pages` tables) via direct ORM queries.
- **Safety Policy Verification**: Verified zero third-party form submissions and zero CAPTCHA puzzle cracking attempts across all test runs.
