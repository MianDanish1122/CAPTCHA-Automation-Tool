# CAPTCHA INSPECTOR — Next.js Enterprise Frontend

**Technology Brainz — Automated Security & CAPTCHA Intelligence Dashboard (Phase 4)**

A modern, responsive, SaaS-grade web application built with **Next.js 16 (App Router)**, **TypeScript**, and **Tailwind CSS**, fully integrated with the FastAPI backend (`http://127.0.0.1:8000`).

---

## 🌟 Key Features

1. **System Overview Dashboard (`/`)**: Real-time telemetry, active security policies, provider breakdown distribution, and recent scans.
2. **Smart URL Inspector (`/inspector`)**: Configurable web crawler with real-time progress indicators, `max_pages` and `max_depth` limits, loopback toggle, and evidence screenshot modals.
3. **Scan History (`/scans`)**: Comprehensive audit trail of all automated crawler executions with slide-out details drawer and itemized discovered pages.
4. **CAPTCHA Results (`/results`)**: Cross-scan intelligence table with provider filtering (reCAPTCHA, hCaptcha, Turnstile, Synthetic OCR) and deep token evidence inspect.
5. **Human Review Center (`/reviews`)**: Dedicated operator queue for auditing high-risk challenges, approving exceptions, rejecting false positives, or marking verified with operator notes.
6. **OCR Laboratory (`/ocr`)**: Interactive synthetic CAPTCHA generation, OpenCV visual preprocessing pipeline (Bilateral filtering + Otsu binarization + opening), and automated benchmark suite.
7. **CSV Batch Manager (`/batch`)**: Drag-and-drop CSV validation, live batch crawler progress tracking, itemized target review, and instant compliance report download.
8. **Audit Reports (`/reports`)**: Centralized repository of generated CSV compliance reports for audit trails and security verification.
9. **Settings & Diagnostics (`/settings`)**: Real-time diagnostics for FastAPI server, Tesseract OCR path, Playwright browser engine, and SSRF allowlist policies.

---

## 🛠️ Technology Stack

- **Framework**: Next.js 16.4.5 (App Router, Turbopack)
- **Language**: TypeScript 5 (Strict type checking)
- **Styling**: Tailwind CSS v4 with custom dark navy sidebar (`#0f172a`) and light canvas
- **Icons**: Lucide React
- **API Client**: Native `fetch` with centralized TypeScript definitions (`lib/api.ts` & `lib/types.ts`)

---

## 🚀 Quickstart

### Prerequisites
- Node.js 18+ (tested with Node 20 / 22)
- FastAPI backend running on `http://127.0.0.1:8000`

### 1. Configuration (.env.local)
Create a `.env.local` file in the `frontend/` directory (or use default fallback):
```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 2. Development Mode
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### 3. Production Build & Execution
```bash
# Typecheck
npx tsc --noEmit

# Production Build
npm run build

# Start Production Server
npm run start -- -p 3000
```

---

## 📁 Project Structure

```
frontend/
├── app/
│   ├── layout.tsx         # Global layout with persistent dark navy sidebar and header
│   ├── page.tsx           # Overview Dashboard with real metrics and provider distribution
│   ├── globals.css        # Tailwind CSS imports and root variables
│   ├── inspector/page.tsx # URL Inspector & Crawler configuration
│   ├── scans/page.tsx     # Scan History with slide-out drawer
│   ├── results/page.tsx   # Cross-scan CAPTCHA Results & filters
│   ├── reviews/page.tsx   # Human Review Center with operator decision actions
│   ├── ocr/page.tsx       # Synthetic OCR Laboratory & Benchmark Runner
│   ├── batch/page.tsx     # CSV Batch Importer, Validator, & Pipeline
│   ├── reports/page.tsx   # Compliance Report Archive & CSV Download
│   └── settings/page.tsx  # System Settings & Engine Diagnostics
├── components/
│   ├── Sidebar.tsx        # Responsive dark navy sidebar navigation with live badge
│   ├── Header.tsx         # Top bar with real-time FastAPI connection pulse & quick actions
│   ├── Card.tsx           # Reusable SaaS card container
│   ├── StatCard.tsx       # KPI metric card with icons and trends
│   ├── Badge.tsx          # Color-coded provider & status pill badges
│   ├── Modal.tsx          # Accessible dialog modal
│   ├── Drawer.tsx         # Slide-out side drawer for scan inspection
│   └── EvidenceViewer.tsx # Screenshot, DOM tokens, and raw JSON evidence inspector
├── lib/
│   ├── types.ts           # Complete TypeScript interface definitions
│   └── api.ts             # Centralized API service with error handling
├── package.json
└── tsconfig.json
```

---

## 🔒 Security & Architecture Compliance
- **Zero-Bypass Architecture**: The dashboard strictly adheres to compliance principles. Third-party CAPTCHAs are never bypassed; operator human reviews are recorded in an auditable ledger.
- **SSRF Safe**: Crawler options respect domain allowlists and private IP protections.
- **Real Backend Telemetry**: All numbers, tables, metrics, and progress bars are computed from live FastAPI and SQLite database records.
