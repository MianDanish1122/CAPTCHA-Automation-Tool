> **Superseded** by `docs/DEMO_VIDEO_SCRIPT.md`, `docs/DEMO_RECORDING_CHECKLIST.md` and `docs/DEMO_ENVIRONMENT_GUIDE.md`. This early plan predates the security and evaluation work and contains a local file-system path; do not use it for recording.

# 3–5 Minute Live Demonstration Plan

This walkthrough is designed for technical interviewers and stakeholders to demonstrate the complete capabilities of the **CAPTCHA Inspection & Verification Tool**.

---

## Demonstration Script & Timeline

### Step 1: Starting the Application (0:00 - 0:30)
1. Open PowerShell or Terminal in the project root:
   ```powershell
   cd C:\Users\Hp\OneDrive\Desktop\captcha-automation-tool
   .\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Explain:
   - Application is running on FastAPI 2.0 with asynchronous lifespan management.
   - SQLite database automatically initializes at startup.
   - Playwright browser pool is ready for headless Chromium automation.
   - `ENABLE_LIVE_SCAN=false` is enforced by default to guarantee SSRF safety until explicitly authorized.

---

### Step 2: Opening Interactive Swagger UI (0:30 - 0:50)
1. Open a browser to:
   [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
2. Highlight:
   - Tagged grouping: **Website Inspection & Batches** and **CAPTCHA OCR & Token Verification**.
   - Strict Pydantic input/output schemas.

---

### Step 3: Uploading & Validating CSV (0:50 - 1:20)
1. In Swagger, navigate to `POST /api/websites/import`.
2. Click **Try it out** and upload `sample_websites.csv`.
3. Click **Execute**:
   - Show how valid domains (`https://example.com`, `https://demo.com`) are parsed and normalized.
   - Show how invalid rows (missing URLs, malformed schemes) are isolated into `errors` without breaking the batch.

---

### Step 4 & 5: Local CAPTCHA Provider Detection (1:20 - 2:00)
1. Open `POST /api/websites/inspect-demo`.
2. Paste the HTML content of `tests/fixtures/google_recaptcha.html`:
   - Click **Execute**: Show detection of `google_recaptcha` and `is_active_challenge: true`.
3. Paste the HTML content of `tests/fixtures/cloudflare_turnstile.html`:
   - Click **Execute**: Show detection of `cloudflare_turnstile`.
4. Paste the HTML content of `tests/fixtures/normal_contact_form.html`:
   - Click **Execute**: Show `no_known_captcha_detected`, `contact_form_found: true`.
5. Point out:
   - The scanner distinguishes active interactive widgets from passive vendor script loaders.

---

### Step 6 & 7: Batch Processing & Failure Resilience (2:00 - 2:50)
1. Open `POST /api/websites/scan-batch`.
2. Provide a batch payload referencing diverse test fixtures:
   ```json
   {
     "websites": [
       {"company_name": "Acme Global", "website_url": "fixture://normal_contact_form.html"},
       {"company_name": "Nexus Security", "website_url": "fixture://google_recaptcha.html"},
       {"company_name": "Fortress Guard", "website_url": "fixture://unknown_challenge.html"},
       {"company_name": "Faulty Host", "website_url": "https://192.168.1.1"}
     ]
   }
   ```
3. Click **Execute** and copy the returned `batch_id`.
4. Open `GET /api/websites/batches/{batch_id}`:
   - Observe real-time counters: `processed_records`, `successful_records`, `failed_records`.
5. Open `GET /api/websites/batches/{batch_id}/results`:
   - Show how `https://192.168.1.1` was immediately blocked by the `SecurityGuard` (Private IP / SSRF rejection).
   - Show how `unknown_challenge.html` was safely classified as `unsupported_challenge` with `human_review_required: true`.
   - Emphasize that the batch continued to completion without crashing.

---

### Step 8: Synthetic OCR Demonstration (2:50 - 3:30)
1. Open `POST /api/captcha/ocr-demo`.
2. Execute with sample text (or leave default to auto-generate):
   - Review OpenCV vision preprocessing (Bilateral filter, Otsu thresholding, morphological noise removal).
   - Review Tesseract OCR extraction, confidence percentage, and inference duration.
3. Open `POST /api/captcha/ocr-benchmark` and run on 3 samples:
   - Review the limitations disclaimer explaining why OCR cannot bypass modern behavioral CAPTCHAs.

---

### Step 9: Official Test-Token Verification (3:30 - 4:10)
1. Open `POST /api/captcha/verify-token`.
2. Test official Google test credentials:
   - Pass `token: "VALID_TEST_RESPONSE"` -> returns `success: true`, status `verified`.
   - Pass `token: ""` -> returns `missing-input-response`.
   - Pass `token: "ANY", simulate_status: "reused"` -> returns `timeout-or-duplicate`.
3. Note: Server-side cryptographic token verification follows Google reCAPTCHA's official verification protocol.

---

### Step 10: Generating & Downloading Report (4:10 - 4:45)
1. Open `GET /api/websites/batches/{batch_id}/report`.
2. Click **Execute** and download the CSV.
3. Open the CSV in Excel or Notepad:
   - Show the 11 standard columns (Company Name, Website URL, Website Status, Contact Page Found, CAPTCHA Detected, CAPTCHA Provider, Inspection Status, Human Review Required, Error Details, Scan Timestamp, Duration).
4. Point the audience to `evidence/TEST_EVIDENCE.md` and `evidence/screenshots/` for complete audit artifacts.

---

## Feature Classification Matrix (Implemented vs Tested vs Simulated)

| Component / Feature | Operational Classification | Description |
| :--- | :--- | :--- |
| **CSV Import & Parser** | **Fully Implemented & Verified** | RFC 4180 parsing, UTF-8 normalization, URL syntax checks. |
| **Local Demo Inspection** | **Fully Implemented & Verified** | Playwright headless Chromium DOM analysis. |
| **Batch Processing Engine** | **Fully Implemented & Verified** | Asynchronous queue, `asyncio.Semaphore` concurrency, SQLite persistence. |
| **SSRF & Security Guard** | **Fully Implemented & Verified** | Private IP blocking, RFC 1918, DNS resolution, protocol enforcement. |
| **Tesseract OCR Benchmark** | **Fully Implemented & Verified** | Pillow synthetic generator, OpenCV filters, Tesseract OCR v5.5.0. |
| **Token Verification** | **Implemented & Test-Key Verified** | Server-side verification using Google's official test keys and test simulation modes. |
| **Live Scanning of Unknown External Sites** | **Safety Guarded (`ENABLE_LIVE_SCAN=false`)** | Enabled only when authorized domains are configured to protect interviewer networks and prevent unauthorized scraping. |
