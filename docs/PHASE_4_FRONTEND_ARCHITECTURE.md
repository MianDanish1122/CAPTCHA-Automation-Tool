# Phase 4: Frontend Architecture Document
**Technology Brainz — CAPTCHA Inspector Dashboard**
**Version:** 2.0.0 (Phase 4 Final Delivery)

---

## 1. Executive Summary & Architectural Goals

The **CAPTCHA Inspector Dashboard** is an enterprise-grade, responsive SaaS web interface designed to provide security operators and automated compliance auditors complete observability and control over website inspection, CAPTCHA classification, and form discovery workflows.

Built on **Next.js 16 App Router**, **TypeScript 5**, and **Tailwind CSS**, the frontend establishes a single pane of glass connected directly to the existing **FastAPI backend (`http://127.0.0.1:8000`)**.

### Primary Architectural Tenets
1. **Real-Time Backend Connection (No Mock Data)**: Every KPI metric, chart distribution, crawler log, and screenshot viewer is powered by live FastAPI endpoints.
2. **Zero-Bypass Architecture**: Adheres strictly to security and compliance boundaries. Third-party challenges (Google reCAPTCHA, Cloudflare Turnstile, hCaptcha) are surfaced for **Human-in-the-Loop Operator Verification**, while synthetic/owned challenges are tested with local OpenCV/Tesseract pipelines.
3. **Enterprise SaaS Design System**: Consistent dark navy sidebar (`#0f172a`), clean canvas (`#f8fafc`), standardized badges, accessible dialog modals, and slide-out drawers.
4. **Type-Safe Contract**: Strict TypeScript interfaces mirror SQLAlchemy backend models and Pydantic schemas.

---

## 2. Technology Stack & Framework Selection

| Layer | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Framework** | Next.js (App Router) | 16.4.5 | High-performance server-rendered and client components with Turbopack compilation |
| **Language** | TypeScript | 5.x | Strict compile-time type safety across all API calls and UI state |
| **Styling** | Tailwind CSS | 4.x | Utility-first responsive styling with custom CSS design tokens |
| **Iconography** | Lucide React | 1.70.0 | High-contrast, semantic SVG iconography |
| **HTTP Client** | Native `fetch` API | Standard | Zero-dependency, stream-capable HTTP transport with custom `ApiError` handler |
| **Testing** | Playwright Chromium | 1.58.0 | Headless browser end-to-end verification and visual evidence capture |

---

## 3. Directory & File Organization

```
frontend/
├── app/
│   ├── layout.tsx              # Root HTML shell, fonts, global layout with Sidebar & Header
│   ├── globals.css             # Tailwind imports & CSS theme custom properties
│   ├── page.tsx                # Overview Dashboard (/): KPIs, provider breakdown, recent scans
│   ├── inspector/page.tsx      # URL Inspector (/inspector): Crawler controls, live progress, discovered pages
│   ├── scans/page.tsx          # Scan History (/scans): Historical audit log, search, itemized drawer
│   ├── results/page.tsx        # CAPTCHA Results (/results): Cross-scan challenge discovery & filters
│   ├── reviews/page.tsx        # Human Review Center (/reviews): Operator queue, decision form, audit notes
│   ├── ocr/page.tsx            # OCR Laboratory (/ocr): Synthetic generator, OpenCV pipeline, benchmarks
│   ├── batch/page.tsx          # CSV Batch Manager (/batch): Drag-and-drop CSV validation & batch pipeline
│   ├── reports/page.tsx        # Audit Reports (/reports): Compliance archives & instant CSV export
│   └── settings/page.tsx       # System Settings (/settings): Diagnostics, allowlists, engine paths
├── components/
│   ├── Sidebar.tsx             # Dark navy sidebar (#0f172a) with live pending review badge
│   ├── Header.tsx              # Sticky top bar with FastAPI health pulse indicator
│   ├── Card.tsx                # SaaS container wrapper with title, subtitle, and action buttons
│   ├── StatCard.tsx            # KPI metric card with icon, value, and accent color scheme
│   ├── Badge.tsx               # Color-coded badges for providers, scan statuses, and review decisions
│   ├── Modal.tsx               # Reusable dialog modal with Escape key handling and backdrop
│   ├── Drawer.tsx              # Slide-out drawer for inspecting scan results without page reload
│   └── EvidenceViewer.tsx      # Tabbed visualizer for screenshots, matched DOM tokens, and raw JSON
├── lib/
│   ├── types.ts                # TypeScript schemas for all API payloads and models
│   └── api.ts                  # Centralized, strongly-typed API client
├── package.json
└── tsconfig.json
```

---

## 4. UI/UX Design System & Color Tokens

### 4.1. Color Palette
- **Sidebar Background**: `#0f172a` (Slate 900)
- **Canvas Background**: `#f8fafc` (Slate 50)
- **Primary Brand Color**: `#2563eb` (Blue 600) with hover `#1d4ed8` (Blue 700)
- **Card Background**: `#ffffff` with border `#e2e8f0` (Slate 200)

### 4.2. CAPTCHA Provider Badges
- **Google reCAPTCHA**: Blue theme (`bg-blue-50 text-blue-700 border-blue-200`)
- **Cloudflare Turnstile**: Amber/Orange theme (`bg-amber-50 text-amber-700 border-amber-200`)
- **hCaptcha**: Purple theme (`bg-purple-50 text-purple-700 border-purple-200`)
- **Synthetic Text OCR**: Teal/Emerald theme (`bg-teal-50 text-teal-700 border-teal-200`)
- **No CAPTCHA**: Slate/Gray theme (`bg-slate-100 text-slate-600 border-slate-200`)
- **Unknown Challenge**: Rose/Red theme (`bg-rose-50 text-rose-700 border-rose-200`)

---

## 5. API Client & Communication Layer

The API client (`frontend/lib/api.ts`) manages all requests to the FastAPI backend:
- Configurable base URL via `process.env.NEXT_PUBLIC_API_BASE_URL` (defaults to `http://127.0.0.1:8000`).
- Unified JSON error extraction with `ApiError` class.
- Support for `multipart/form-data` during CSV upload (`uploadCsv`).
- Polling-friendly methods for asynchronous scan and batch tracking (`getScanResults`, `getBatch`).
- Direct file download URL generation for compliance CSV export (`getBatchReportUrl`).
- Static screenshot resolution via `/evidence/` endpoint.

---

## 6. End-to-End Workflow Diagram

```
+-------------------------------------------------------------------------+
|                         Next.js App Router (Port 3000)                  |
|                                                                         |
|  [Overview]  [URL Inspector]  [Scan History]  [Reviews]  [OCR Lab]      |
+------------------------------------+------------------------------------+
                                     |  REST API Calls
                                     v
+------------------------------------+------------------------------------+
|                         FastAPI Backend (Port 8000)                     |
|                                                                         |
|   /api/websites/inspect-url       -> Playwright Headless Browser        |
|   /api/captcha/reviews            -> Human Review Lifecycle             |
|   /api/captcha/ocr-demo           -> OpenCV Filters + Tesseract LSTM    |
|   /api/websites/import            -> CSV Importer & Validator           |
|   /api/websites/batches/{id}/report -> CSV Audit Report Exporter        |
|   /evidence/                      -> Static Screenshot Service          |
+-------------------------------------------------------------------------+
```

---

## 7. Security & Compliance Architecture

1. **SSRF Guarding**: The frontend provides a loopback toggle specifically for local fixtures and QA, while production scans enforce strict public IP allowlists.
2. **Zero-Bypass Policy**: Automated scraping and bypass of live third-party CAPTCHAs is strictly avoided. When reCAPTCHA, Turnstile, or hCaptcha widgets are found, the system routes them to `/reviews` where human operators submit audit judgments.
3. **No Secret Leaks**: Test keys and API secrets are managed server-side and never exposed to client-side bundles.
