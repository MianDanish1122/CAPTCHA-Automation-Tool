# Phase 4: Implementation Document
**Technology Brainz — CAPTCHA Inspector Dashboard**
**Date:** November 2026
**Branch:** `phase-4-frontend-dashboard`

---

## 1. Overview

In Phase 4, we built a complete, production-ready **Next.js 16 (App Router)** web dashboard inside the `frontend/` directory, connecting seamlessly to the existing FastAPI backend (`http://127.0.0.1:8000`).

The application enables automated website inspection, Playwright-driven contact page discovery, CAPTCHA classification, human review workflows, synthetic OCR experimentation, CSV batch audits, and compliance report downloads.

---

## 2. Page-by-Page Implementation Walkthrough

### 2.1. System Overview Dashboard (`frontend/app/page.tsx`)
- **Purpose**: Executive dashboard giving security operators an instant high-level overview of system status and inspection metrics.
- **Components & Features**:
  - **Quick Scan Launcher**: Header banner with URL input allowing immediate launch of an inspection.
  - **Diagnostic KPI Bar**: System Policy (Strict Allowlist vs Live), OCR Engine readiness (PyTesseract/OpenCV), and Review Queue count.
  - **Stat Cards**: Total Scans, Discovered Pages, CAPTCHAs Found, and Batch Jobs.
  - **CAPTCHA Distribution Bar**: Real-time breakdown of detected challenge providers (Google reCAPTCHA, Cloudflare Turnstile, hCaptcha, Synthetic OCR, Clean).
  - **Recent Scans Table**: Compact table listing recent crawl jobs with direct links to full inspection details.

### 2.2. Smart URL Inspector (`frontend/app/inspector/page.tsx`)
- **Purpose**: Primary interface for crawling authorized domains and discovering form structures.
- **Controls**:
  - Target URL input (`https://...` or `http://localhost:8000/...`).
  - `max_pages` slider (1 to 20 pages).
  - `max_depth` slider (0 = home only, up to 3 link levels).
  - Loopback toggle (`allow_loopback`) for testing local servers without SSRF rejection.
  - Background toggle (`background`) for asynchronous crawler execution.
- **Live Pipeline Tracker**: Step progress tracker showing initialization, link discovery, and CAPTCHA classification.
- **Discovered Pages Table**:
  - URL and page title.
  - Crawl depth (`L0`, `L1`, `L2`).
  - Contact page indicator.
  - Detected forms count.
  - Classified CAPTCHA provider badge.
  - Review status pill.
  - "Inspect Evidence" button opening the `EvidenceViewer` modal.

### 2.3. Scan History (`frontend/app/scans/page.tsx`)
- **Purpose**: Complete audit log of all crawler executions.
- **Features**:
  - Search by URL, domain, or Scan UUID.
  - Status filter tabs (`all`, `completed`, `crawling`, `failed`).
  - Table displaying domain, pages crawled, contact pages found, CAPTCHA providers, execution duration, and creation timestamp.
  - **Slide-Out Details Drawer (`components/Drawer.tsx`)**: Clicking "Inspect" opens a side drawer displaying the complete itemized list of discovered pages and allows drilling into screenshots without leaving the page.
  - Direct deep-linking via `?scan_id=...` query parameters.

### 2.4. CAPTCHA Results (`frontend/app/results/page.tsx`)
- **Purpose**: Unified cross-scan view of all detected CAPTCHA instances across inspected sites.
- **Features**:
  - Provider selector dropdown (All, reCAPTCHA, Turnstile, hCaptcha, Synthetic, Clean).
  - "CAPTCHA Detections Only" toggle to filter out pages with no challenge markers.
  - Search by URL or page title.
  - Columns: Target URL, Provider badge, Detection confidence score %, Handling strategy (`human_review`, `token_verification`, etc.), Forms count, Review status, and Evidence action.

### 2.5. Human Review & Verification Center (`frontend/app/reviews/page.tsx`)
- **Purpose**: Operator queue enforcing our **Zero-Bypass Architecture**.
- **Features**:
  - Filter tabs: `Needs Review` (pending), `Approved`, `Rejected`, `Verified`, `All`.
  - Operator metrics header displaying total pending reviews.
  - Review table with challenge type and confidence score.
  - **Operator Decision Modal**:
    - Displays full screenshot and matched script tokens.
    - Operator ID and auditable decision notes input.
    - Action buttons:
      - `Mark Manually Verified`: Records human verification in the database.
      - `Approve Exception`: Approves an audited bypass exception.
      - `Reject / False Positive`: Flags challenge as false alarm.
    - Connects directly to backend `PATCH /api/captcha/reviews/{review_id}`.

### 2.6. OCR Laboratory (`frontend/app/ocr/page.tsx`)
- **Purpose**: Interactive computer vision testing environment for synthetic and owned CAPTCHA challenges.
- **Interactive Generator**:
  - Custom text input (or "Randomize" generator).
  - Pillow image synthesis with skew, character rotation, and interference noise.
  - Preprocessing visualization:
    1. Distorted input image.
    2. OpenCV preprocessed image (Bilateral filter + Otsu binarization + opening).
  - Tesseract LSTM OCR prediction comparison with character-level accuracy % and execution time in milliseconds.
- **Automated Benchmark Suite**:
  - Sample size selector (5, 10, or 20 samples).
  - Calculates Exact Match Rate %, Mean Character Accuracy %, and Mean Execution Time per image.
  - Displays sample breakdown table.
  - Provides an honest architectural limitations analysis detailing why OCR is unsuitable for modern bot defenses and why token verification is required.

### 2.7. CSV Batch Manager (`frontend/app/batch/page.tsx`)
- **Purpose**: Mass website auditing from CSV input files.
- **Features**:
  - Drag-and-drop CSV file uploader (supports standard `company_name,website_url` format).
  - Instant validation summary displaying total rows, valid rows, and invalid rows with itemized error descriptions.
  - Batch audit launcher running in the background.
  - Live progress bar polling `GET /api/websites/batches/{batch_id}`.
  - Itemized results table for each audited company.
  - Direct download button for the generated CSV compliance audit report.

### 2.8. Reports & Compliance Exports (`frontend/app/reports/page.tsx`)
- **Purpose**: Central archive for downloading official audit compliance reports.
- **Features**:
  - KPI summary of total audit batches and verified clean targets.
  - Table of all completed batches with timestamp and processed count.
  - One-click "Export CSV" button directly streaming generated compliance reports from `GET /api/websites/batches/{batch_id}/report`.

### 2.9. System Settings & Diagnostics (`frontend/app/settings/page.tsx`)
- **Purpose**: Operational transparency and diagnostic visibility.
- **Features**:
  - FastAPI server status, environment, and base URL (`http://127.0.0.1:8000`).
  - Security Guard policies: SSRF protection status and authorized domain allowlists.
  - Crawler engine parameters: concurrency limits, page timeout, max depth.
  - OCR Engine diagnostics: PyTesseract installation status and executable path.
  - Evidence and report directory paths.

---

## 3. Reusable UI Components

- **`components/Sidebar.tsx`**: Dark navy theme (`#0f172a`), responsive mobile drawer, semantic iconography, and live badge displaying pending human reviews.
- **`components/Header.tsx`**: Top navigation with real-time ping to `/health`, showing green/red connection pills and quick-action shortcuts.
- **`components/EvidenceViewer.tsx`**: Tabbed viewer supporting screenshots, matched DOM script tokens, detected form inputs, and raw JSON.
- **`components/Modal.tsx`**: Accessible dialog with backdrop blur, keyboard `Escape` handler, and customizable action footer.
- **`components/Drawer.tsx`**: Slide-out drawer for inspecting scan results without page navigation.
- **`components/Badge.tsx`**: Semantic color coding for providers (`google_recaptcha`, `cloudflare_turnstile`, `hcaptcha`, `synthetic_text_captcha`, `no_captcha`) and workflow statuses.
- **`components/Card.tsx` & `components/StatCard.tsx`**: Consistent enterprise SaaS card containers.

---

## 4. Backend Enhancements

To ensure the frontend functions seamlessly without mock data, the FastAPI backend was enhanced with additive endpoints:
1. **Static Evidence Serving**: Mounted `app.mount("/evidence", StaticFiles(directory="evidence"), name="evidence")` in `app/main.py`.
2. **`GET /api/websites/overview-stats`**: Aggregates total scans, pages, CAPTCHAs, pending reviews, and provider distribution.
3. **`GET /api/websites/scans`**: Lists scans with pagination and status filtering.
4. **`GET /api/websites/batches`**: Lists batch jobs with pagination.
5. **`GET /api/websites/pages`**: Lists discovered pages across all scans with CAPTCHA and provider filters.
6. **`GET /api/websites/settings`**: Exposes diagnostic configuration and engine parameters.
7. **Base64 Image Support in `/api/captcha/ocr-demo`**: Returns encoded PNGs of synthetic input and OpenCV preprocessed output for the OCR visualizer.
