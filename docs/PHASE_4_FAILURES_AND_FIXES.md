# Phase 4 Acceptance Testing: Failures and Fixes Log

**Date:** November 7, 2026  
**Environment:** Windows 11, Python 3.12, FastAPI, SQLite, Next.js 16.4.5, Playwright, Pytest  
**Branch:** `phase-4-final-acceptance`  
**Test Suite:** End-to-End Acceptance Test Automation (`tests/run_acceptance_tests.py`)

---

## Overview

During the independent Phase 4 Final Acceptance Testing, the full-stack system was evaluated end-to-end against real backend services, real database records, and actual browser viewport interactions. Local test fixtures were utilized to enforce the **Zero-Bypass Architecture** without relying on mock data or bypass services.

Five technical discrepancies were detected during test harness execution. All five issues were diagnosed down to root causes, resolved with minimal surgical code edits, and verified across both backend unit tests (71/71 passing) and automated browser acceptance tests (29/29 passing).

---

## Detailed Defect Analysis & Remediations

### Defect 1: Windows Console CP1252 Encoding Crash (`UnicodeEncodeError`)

- **Classification:** Test Harness / Platform Compatibility
- **Component:** `tests/run_acceptance_tests.py`
- **Severity:** High (blocked test execution on Windows)
- **Symptom:**
  ```text
  UnicodeEncodeError: 'charmap' codec can't encode character '\u2713' in position 0: character maps to <undefined>
  ```
- **Root Cause:**
  The Windows command shell defaults to the Windows-1252 (cp1252) code page. When standard output attempted to write UTF-8 checkmark symbols (`✓`), the Python runtime raised an unhandled `UnicodeEncodeError`.
- **Remediation:**
  Reconfigured `sys.stdout` to UTF-8 on Windows environments and replaced non-standard symbols with universally compatible ASCII markers:
  ```python
  if hasattr(sys.stdout, 'reconfigure'):
      sys.stdout.reconfigure(encoding='utf-8')
  ```
- **Verification:**
  Test harness runs cleanly to completion without encoding faults across Windows PowerShell and Command Prompt.

---

### Defect 2: Database Schema Column Discrepancy on Human Review Audit

- **Classification:** Schema / Database Integration
- **Component:** `tests/run_acceptance_tests.py` & SQLite Database Audit
- **Severity:** Medium (false negative in automated DB audit)
- **Symptom:**
  ```text
  sqlite3.OperationalError: no such column: reviewer_notes
  ```
- **Root Cause:**
  The test verification script queried `SELECT reviewer_notes, updated_at FROM human_reviews`, but the actual SQLAlchemy model defined in [app/models.py](file:///c:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/models.py#L90-L115) defines the columns as `operator_notes` and `resolved_at`.
- **Remediation:**
  Updated the test query in `tests/run_acceptance_tests.py` to match the production schema:
  ```python
  cursor.execute(
      "SELECT id, status, decision, operator_notes, resolved_at FROM human_reviews WHERE id = ?",
      (review_id,)
  )
  ```
- **Verification:**
  Database audit test passed, verifying persistent update of operator notes (`"Confirmed reCAPTCHA v2 checkbox widget present on contact form."`) and timestamp `resolved_at`.

---

### Defect 3: Synthetic OCR Benchmark Response Field Aliases

- **Classification:** API Contract / Frontend Integration
- **Component:** [app/routes/captcha.py](file:///c:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/routes/captcha.py#L290-L325)
- **Severity:** Medium (frontend metrics display empty values)
- **Symptom:**
  The OCR Laboratory page and acceptance test assertions reported missing summary fields (`mean_character_accuracy`, `exact_matches`, `mean_execution_time_ms`, `technical_limitations_summary`).
- **Root Cause:**
  The backend OCR benchmark function returned snake_case keys (`character_accuracy_pct`, `exact_match_rate_pct`, `average_duration_ms`, `limitations_analysis`), whereas the frontend TypeScript component and integration tests expected standardized summary aliases.
- **Remediation:**
  Enhanced `POST /api/captcha/ocr-benchmark` in `app/routes/captcha.py` to calculate and return both sets of keys:
  ```python
  results = benchmark_synthetic_ocr(samples=request.samples)
  total_samples = results.get("total_samples", request.samples)
  exact_pct = results.get("exact_match_rate_pct", 0.0)
  exact_count = round(total_samples * (exact_pct / 100.0))
  
  return {
      "success": True,
      **results,
      "exact_matches": exact_count,
      "exact_match_rate_percent": exact_pct,
      "mean_character_accuracy": results.get("character_accuracy_pct", 0.0),
      "mean_execution_time_ms": results.get("average_duration_ms", 0.0),
      "technical_limitations_summary": results.get("limitations_analysis", ""),
  }
  ```
- **Verification:**
  OCR benchmark returned HTTP 200 with 100% field coverage, verified by `test_11` in acceptance runner and visualized in `acceptance_07_desktop_ocr_benchmarked.png`.

---

### Defect 4: CSV Import Summary Counts Missing from JSON Response

- **Classification:** API Contract / Frontend Integration
- **Component:** [app/routes/websites.py](file:///c:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/routes/websites.py#L98-L115)
- **Severity:** Low (inconvenient client-side recalculation)
- **Symptom:**
  `POST /api/websites/import` returned `{"success": true, "websites": [...], "invalid_rows": 2}`, but frontend file upload dropzone and batch creation workflows expected explicit `valid_count`, `invalid_count`, `total_rows`, and `message`.
- **Remediation:**
  Augmented the import route response dictionary in `app/routes/websites.py`:
  ```python
  valid_websites = result.get("websites", [])
  invalid_rows = result.get("invalid_rows", len(result.get("errors", [])))
  result["valid_count"] = len(valid_websites)
  result["invalid_count"] = invalid_rows
  result["total_rows"] = len(valid_websites) + invalid_rows
  result["message"] = f"CSV validated successfully ({len(valid_websites)} valid, {invalid_rows} invalid)."
  ```
- **Verification:**
  `POST /api/websites/import` returns full row metrics, matching batch wizard requirements without regression.

---

### Defect 5: Primary Key Serialization Mismatch (`scan_id` vs `id`) Causing Client Crash

- **Classification:** Frontend Runtime Crash / State Serialization
- **Component:** [app/models.py](file:///c:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/models.py#L139-L155) & [frontend/app/scans/page.tsx](file:///c:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/frontend/app/scans/page.tsx#L170-L230)
- **Severity:** Critical (caused React client render exception on `/scans`)
- **Symptom:**
  Navigating to `http://localhost:3000/scans` threw:
  ```text
  TypeError: Cannot read properties of undefined (reading 'slice')
  ```
  The table failed to render scan rows, which in turn caused the Playwright acceptance test for the scan history drawer to time out waiting for table row selectors.
- **Root Cause:**
  `UrlScan.to_dict()` serialized the primary key strictly as `"scan_id": self.id`. The Next.js frontend TypeScript model declared `id: string`. As a result, `scan.id` was `undefined`, and `scan.id.slice(0, 8)` threw a runtime error.
- **Remediation:**
  1. Updated `UrlScan.to_dict()` in `app/models.py` to provide both `"id": self.id` and `"scan_id": self.id`:
     ```python
     def to_dict(self) -> dict:
         return {
             "id": self.id,
             "scan_id": self.id,
             "submitted_url": self.submitted_url,
             ...
         }
     ```
  2. Applied defensive fallback in `frontend/app/scans/page.tsx`:
     ```typescript
     const sId = scan.id || (scan as any).scan_id || '';
     ```
  3. Recompiled frontend production bundle with `npm run build`.
- **Verification:**
  The Scan History page renders cleanly with responsive rows and inspection buttons. Playwright test `UI: Scan History Slide-Out Drawer` passed, capturing `acceptance_04_desktop_scans_drawer.png`.

---

## Summary Matrix

| ID | Component | Error Type | Severity | Status | Verified In |
|---|---|---|---|---|---|
| 1 | `tests/run_acceptance_tests.py` | Windows cp1252 `UnicodeEncodeError` | High | Resolved | Runner execution |
| 2 | `tests/run_acceptance_tests.py` | SQLite column `reviewer_notes` vs `operator_notes` | Medium | Resolved | DB Audit Test #9 |
| 3 | `app/routes/captcha.py` | Benchmark metric alias mismatch | Medium | Resolved | API Test #11 |
| 4 | `app/routes/websites.py` | CSV import response missing counts | Low | Resolved | API Test #13 |
| 5 | `app/models.py` / `scans/page.tsx` | `UrlScan.to_dict()` `scan_id` vs `id` | Critical | Resolved | UI Test #19 & Build |
