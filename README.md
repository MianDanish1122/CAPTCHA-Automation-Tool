# CAPTCHA Inspection & Verification Tool

A production-grade, asynchronous Python backend application built with **FastAPI**, **Playwright**, **SQLAlchemy**, **OpenCV**, and **Tesseract OCR**. Designed for bulk website inspection, contact page discovery, CAPTCHA provider identification, SSRF-safe scanning, synthetic OCR benchmarking, and CSV compliance reporting.

---

## 🌟 Key Features

- **Bulk CSV Ingestion & Validation**: Flexible header mapping, scheme and format validation, row-by-row error reporting.
- **High-Precision CAPTCHA Detection**:
  - Google reCAPTCHA v2 Checkbox
  - Google reCAPTCHA Invisible
  - hCaptcha Interactive Widget
  - Cloudflare Turnstile
  - Unknown / Anti-Bot Interstitials (Cloudflare "Just a Moment", Datadome, PerimeterX/HUMAN) classified for `human_review_required`.
- **Active Challenge vs. Script Distinction**: Accurately distinguishes passive third-party scripts from active challenge widgets presented to the user.
- **SSRF & Security Isolation**: DNS resolution filtering, private IP/loopback rejection, domain allowlisting, and configurable `ENABLE_LIVE_SCAN=false` default.
- **Asynchronous Batch Execution**: Bounded concurrency (`asyncio.Semaphore`), pooled browser contexts, fault-tolerant execution across ~200 sites.
- **Persistent Audit Logging**: SQLite database powered by SQLAlchemy 2.0 tracking batch metrics, timing, and per-site inspection results.
- **Synthetic OCR & Verification Demonstration**:
  - Image generation with distortions, noise lines, and salt-and-pepper artifacts.
  - Image preprocessing using OpenCV (Gaussian blur, grayscale, Otsu thresholding).
  - Tesseract OCR text recognition with benchmark accuracy reporting.
  - Official Google reCAPTCHA server-side test token verification.
- **Downloadable CSV Reports**: One-click download of itemized scan audits.

---

## 🏗️ Technology Stack

- **Framework**: FastAPI (Python 3.12)
- **Browser Automation**: Playwright (Async Chromium)
- **Computer Vision & OCR**: OpenCV (`cv2`), Pillow (`PIL`), Tesseract OCR (`pytesseract`)
- **Database & Persistence**: SQLite, SQLAlchemy 2.0
- **Testing & Verification**: Pytest, Asyncio, Playwright Test Harness

---

## 🚀 Quick Start Guide (Windows)

### 1. Prerequisites
- Python 3.12+
- Tesseract OCR installed (default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- Virtual environment with dependencies installed.

### 2. Activate Environment & Run Application
```powershell
# Navigate to project directory
cd C:\Users\Hp\OneDrive\Desktop\captcha-automation-tool

# Start FastAPI server
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
> [!NOTE]
> Do not use `--reload` on Windows when using Playwright to prevent event loop / subprocess termination conflicts.

### 3. Access Swagger UI & Documentation
- Interactive API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health Check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🧪 Running Tests & QA

```powershell
# Run full automated Pytest suite
.\venv\Scripts\python.exe -m pytest tests/ -v

# Run legacy regression scripts
.\venv\Scripts\python.exe test_csv_importer.py
.\venv\Scripts\python.exe test_browser_scanner.py
```

---

## 📖 Detailed Documentation

- [System Architecture](docs/ARCHITECTURE.md)
- [Implementation Roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Security & SSRF Policy](docs/SECURITY.md)
- [Testing Strategy & Fixtures](docs/TESTING.md)
- [Live Demonstration Guide (3-5 mins)](docs/DEMO_PLAN.md)
- [Final QA Verification Report](docs/FINAL_QA_REPORT.md)
- [Test Evidence & Verification Audit](evidence/TEST_EVIDENCE.md)
