# Technology Brainz — CAPTCHA Inspector
## Project Architecture & Engineering Design

## 1. System Overview

**CAPTCHA Inspector** is an enterprise-grade backend system designed for bulk website inspection, contact form detection, CAPTCHA provider identification, SSRF-safe scanning, synthetic OCR benchmarking, and CSV compliance reporting.

The system is built with a layered, decoupled service architecture to support both standalone CLI/headless execution and future integration with a Next.js / TypeScript frontend.

```mermaid
flowchart TD
    Client["Client / API Consumer / Future Next.js UI"] -->|HTTP REST Requests| FastAPI["FastAPI Application (app/main.py)"]
    
    subgraph APILayer ["API Routing Layer (app/routes/)"]
        WebsitesRoute["/api/websites (Import, Demo Inspect, Batch Jobs)"]
        CaptchaRoute["/api/captcha (OCR Demo, Benchmark, Token Verify)"]
        HealthRoute["/health, / (Probes & Metadata)"]
    end

    FastAPI --> WebsitesRoute
    FastAPI --> CaptchaRoute
    FastAPI --> HealthRoute

    subgraph ServiceLayer ["Service Layer (app/services/)"]
        CSVService["csv_importer.py (RFC 4180 Ingestion & URL Validator)"]
        GuardService["security_guard.py (SSRF, Private IP, DNS Rebinding Guard)"]
        ScannerService["browser_scanner.py (Playwright Pool & DOM Heuristics)"]
        BatchService["batch_processor.py (Bounded Concurrency Pipeline)"]
        OCRService["ocr_service.py (OpenCV Vision + Tesseract OCR)"]
        TokenService["token_verifier.py (Google Siteverify Integration)"]
        ReportService["report_generator.py (RFC 4180 CSV Audit Exporter)"]
    end

    WebsitesRoute --> CSVService
    WebsitesRoute --> ScannerService
    WebsitesRoute --> BatchService
    WebsitesRoute --> ReportService

    CaptchaRoute --> OCRService
    CaptchaRoute --> TokenService

    BatchService --> GuardService
    GuardService --> ScannerService

    subgraph DataLayer ["Data & Persistence Layer"]
        DBEngine["SQLAlchemy 2.0 ORM Engine (app/database.py)"]
        SQLiteDB[("SQLite Database (data/captcha_tool.db)")]
        BatchTable["batch_jobs Table (app/models.py)"]
        InspectionTable["website_inspections Table (app/models.py)"]
    end

    BatchService --> DBEngine
    ReportService --> DBEngine
    DBEngine --> BatchTable
    DBEngine --> InspectionTable
    DBEngine --> SQLiteDB
```

---

## 2. Technology Stack

### Backend (Phase 1 Implemented)
- **Language**: Python 3.12 (CPython)
- **Web Framework**: FastAPI v0.162.0 with Starlette and Pydantic v2
- **Browser Automation**: Playwright 1.64.1 (Async Chromium Headless)
- **Computer Vision & Image Processing**: OpenCV (`cv2`) 5.0.0 and Pillow 13.0.0
- **OCR Engine**: Tesseract OCR v5.5.0 via `pytesseract`
- **Data Persistence**: SQLAlchemy 2.1.8 with SQLite (`data/captcha_tool.db`)
- **Testing & Quality Assurance**: Pytest 9.2.0, AnyIO, Starlette TestClient

### Frontend (Planned for Subsequent Phase)
- **Framework**: Next.js (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Component System**: Modern, responsive SaaS dashboard with live batch progress streaming, interactive CAPTCHA visualizer, and CSV report export.

---

## 3. Core Component Subsystems

### 3.1 Security Guard (`app/services/security_guard.py`)
Enforces strict defense-in-depth against Server-Side Request Forgery (SSRF) and unintended network intrusion:
- **Default Isolation**: `ENABLE_LIVE_SCAN=false` strictly blocks external HTTP calls unless explicitly configured.
- **Protocol Enforcing**: Only `http` and `https` allowed; `file://`, `ftp://`, `javascript:` rejected.
- **Private Subnet & Loopback Rejection**: RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`), and carrier-grade NAT (`100.64.0.0/10`) are rejected.
- **Cloud Metadata Defense**: Explicitly blocks cloud instance metadata endpoints (`169.254.169.254`, `fd00:ec2::254`).
- **DNS Rebinding Protection**: Resolves all A/AAAA records before navigation; if any resolved IP belongs to a forbidden subnet, the request is aborted.

### 3.2 Detection Engine & Browser Pool (`app/services/browser_scanner.py`)
- **Browser Pooling**: Implements thread-safe, loop-aware Chromium browser pooling to eliminate full process restarts per page inspection.
- **Detection Heuristics**:
  - Distinguishes active widget containers (`.g-recaptcha`, `.h-captcha`, `.cf-turnstile`, challenge iframes) from passive vendor script tags.
  - Classifies anti-bot interstitial screens (Cloudflare "Just a Moment", Datadome, PerimeterX/HUMAN) as `unsupported_challenge`.
  - Marks `human_review_required = True` whenever third-party challenges are detected, guaranteeing zero automated bypass attempts.
  - Accurately identifies contact forms by parsing `<form>` elements containing interactive input controls (`<input>`, `<textarea>`, `<button>`, `<select>`) or semantic contact keywords.

### 3.3 Batch Processing Pipeline (`app/services/batch_processor.py`)
- **Bounded Concurrency**: Bounded with `asyncio.Semaphore(settings.MAX_CONCURRENT_PAGES)` (default: 3) to prevent resource starvation or DoS against target servers.
- **Fault-Tolerant Continuation**: Per-site navigation timeouts and unexpected HTTP failures are caught and logged without aborting remaining batch items.
- **Database Persistence**: State transitions (`pending` -> `scanning` -> `completed` / `failed`) and metrics are persisted in SQLite.

### 3.4 Synthetic OCR & Benchmark Service (`app/services/ocr_service.py`)
- **Synthetic CAPTCHA Generator**: Synthesizes variable-length alphanumeric images with geometric lines, character rotations, and salt-and-pepper noise dots using Pillow.
- **Computer Vision Filtering**: Applies OpenCV bilateral filter for edge-preserving denoising, Otsu adaptive thresholding, and morphological opening.
- **Inference Configuration**: Configured with `--oem 3 --psm 7` (Single text line) to ensure authentic character confidence extraction and avoid the Tesseract 5 LSTM zero-confidence anomaly.
- **Limitation Reporting**: Evaluates accuracy against known ground truth while explicitly documenting that modern behavioral CAPTCHAs cannot be solved by traditional OCR.

### 3.5 Token Verification Client (`app/services/token_verifier.py`)
- Integrates Google's official public reCAPTCHA test keys:
  - Site Key: `6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI`
  - Secret Key: `6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe`
- Performs server-side validation against `https://www.google.com/recaptcha/api/siteverify`.
- Implements comprehensive verification matrix: Valid test response, Missing token, Invalid token, and Expired/Reused token.

---

## 4. Database Schema Design

```mermaid
erDiagram
    BATCH_JOB ||--o{ WEBSITE_INSPECTION : contains
    
    BATCH_JOB {
        string id PK "UUID4"
        string status "pending | scanning | completed | failed"
        int total_records
        int processed_records
        int successful_records
        int failed_records
        datetime created_at
        datetime updated_at
    }

    WEBSITE_INSPECTION {
        string id PK "UUID4"
        string batch_id FK "References batch_jobs.id"
        string company_name
        string website_url
        string scan_status "completed | captcha_detected | unsupported_challenge | failed"
        string page_title
        string contact_page_url
        boolean contact_form_found
        boolean captcha_detected
        string captcha_provider
        string detection_method
        boolean is_active_challenge
        boolean human_review_required
        string error_details
        float inspection_duration_ms
        datetime created_at
    }
```

---

## 5. Windows Concurrency & Subprocess Considerations
- Configured with `WindowsProactorEventLoopPolicy` in `app/main.py`.
- Uvicorn should be run directly without `--reload` on Windows to avoid parent/child process pipe destruction when Playwright child processes are active.
