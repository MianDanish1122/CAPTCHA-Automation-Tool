# Screen-by-screen testing guide (what every page and button does)

For a person testing the CAPTCHA Inspector locally for the first time. The tool **looks at** websites, **identifies** CAPTCHAs, **records** evidence and **hands every CAPTCHA to a human**. It never solves a real CAPTCHA, never bypasses a block and never submits a form.

Address: `http://localhost:3000/login` (operator account from `demo_runtime\demo_credentials.txt`).

## The big picture (one minute)
```
 URL Inspector ──► Scan History ──► CAPTCHA Results ──► Human Review
 (one website)     (all scans)       (CAPTCHAs found)    (a person decides)

 CSV Batch Manager ──► results + "Expected vs Detected" ──► Reports (downloads)
 (many websites from a CSV)

 OCR Laboratory / Verification  = tests on OUR OWN synthetic CAPTCHAs and the providers' official TEST keys
 Evaluation / Overview          = totals and charts built from what was really run
```

## 1. URL Inspector (one website)
**What it does:** opens one website in a real headless Chromium, looks for contact/support pages, inspects forms and detects CAPTCHA markers, saves a screenshot of each page.

| Control | Meaning |
|---|---|
| Target Website URL | The page to start from. A home page lets the tool *discover* contact pages. A contact-page URL inspects that page. |
| Max Pages to Crawl (1–20) | Upper limit of pages visited. Keep small (5). |
| Crawl Depth (0–3) | How many link-hops from the start page. 0 = only the page you typed. |
| Allow Localhost / Loopback | Lets you scan **your own** local test site (e.g. `http://127.0.0.1:8090/`). Real websites do not need it. |
| Asynchronous / Background | Starts the scan and returns immediately; results appear later in Scan History. |
| Start Live Inspection | Runs the crawl. |

**Top cards after a run:** Crawled Pages, Contact Touchpoints (contact pages/forms found), CAPTCHA Detected (Yes/No), Crawl Duration.
**"Discovered Pages & Evidence (n)":** one row per page the tool actually inspected, with the CAPTCHA provider and an **Inspect** button (screenshot + details).
**Safety:** only websites on the server allow-list can be scanned; others are refused with a clear message.

> **If it shows "Crawled pages 1, CAPTCHA No" and the Discovered list is empty (0): the page was NOT inspected.** See "Known problems" below: the page timed out and the screen wrongly said Completed.

## 2. Scan History
**What it does:** a permanent list of every inspection ever run (not just this session). Search box (URL/domain/scan id), filters (All / Completed / Crawling / Failed), refresh button.
Columns: target, scan id, status, pages, contact pages, CAPTCHA providers found, duration, time. **Inspect** opens that scan's pages and screenshots.
**You should see one row per inspection.** `Pages 1, Contact 0, None Detected` normally means "one page was visited"; if the Discovered list is empty it means that page was not read (timeout).

## 3. CAPTCHA Results
**What it does:** only pages where a CAPTCHA was found. Provider badge (Google reCAPTCHA / hCaptcha / Turnstile), review status, **Inspect** for evidence. The filter "CAPTCHA Detections Only" hides clean pages.

## 4. Human Review
**What it does:** the queue of CAPTCHAs that a person must look at. The system will never solve them.
**Review Now** opens the item, shows the evidence and lets the operator mark Approved / Rejected / Manually verified with notes. Every decision is recorded with who made it.

## 5. OCR Laboratory
Scope: **our own synthetic text CAPTCHAs only** (not reCAPTCHA/hCaptcha/Turnstile).
- **Run OCR Evaluation:** generates a distorted image for the text shown, runs the computer-vision pipeline and a text reader, and shows whether it read it correctly, with timing.
- **Randomize:** new random text. **Engine / Split / Samples + Run Benchmark:** measures accuracy on many generated images (the reported 99.3% is this benchmark, on our own generator).

## 6. Verification
**What it does:** sends a token to the **provider's official verification service** using the providers' published **test** keys, and records the real answer (verified / failed / already used / missing token / provider unavailable). It never fakes a success. The table "Recorded attempts" lists what was really run.

## 7. CSV Batch Manager (the employer's workflow)
1. **Choose CSV** then **Import & Validate CSV**. The summary shows total / valid / invalid rows, "Columns preserved (n)", row-numbered errors and warnings.
2. Tick **"Automatically start batch scan"** to scan straight away, or use **Launch Batch Scan** after validating.
3. For each site the tool checks robots.txt first, opens the CSV's Contact Page, identifies the CAPTCHA and compares it with the CSV's "Captcha" column.
4. **Results table:** status, detected CAPTCHA, contact form, result. **Details** shows robots status, widget state, expected value and a screenshot.
5. **Expected vs Detected** card: *Match*, *Mismatch*, *Not detected*, *Not accessible* (site blocked/unreachable), *Not verified* (no expected value). The percentage uses only inspected rows that have an expected value; the sample size is stated.
6. Buttons: **Download CSV Audit Report**, and **CSV / Markdown** for the Expected-vs-Detected report.

## 8. Reports
List of past batches with **Export CSV** (the audit report). Counters: total batches, CAPTCHAs documented, verified clean sites.

## 9. Evaluation and Overview
Totals and charts computed from stored runs (scans, pages, CAPTCHA types, OCR, verification, errors, review cases). They show nothing invented: with no data they show empty/zero.

## 10. Settings
System diagnostics and policies (read-only view): backend status, crawler limits, security guard (allow-list, SSRF rules), OCR engine, and the tamper-evident **audit trail** (admin only).

---

## Problems found while preparing this guide (now fixed)
These defects were found when testing the URL Inspector on https://barrett.net/support/contact-us/ and have been fixed (tests in `tests/test_realworld_screen_fixes.py`):

1. **A timed-out page was shown as "Completed".** A scan in which no page could be read is now **Failed**, with the reason and a note that this is not evidence of "no CAPTCHA". Partial failures stay Completed with a note. The default page timeout (`CRAWLER_PAGE_TIMEOUT_MS`) is now 30 s (was 10 s).
2. **Human Review showed `Unknown` provider and `NaN%` confidence.** The API now sends the field names the screen reads; confidence shows "-" when it is not measured.
3. **CAPTCHA Results showed `-` and a blank Forms column.** Fixed the same way.

Per-page confidence is intentionally not measured, so the screens show "-" rather than an invented number.

## A clean test you can do right now
1. **URL Inspector** → `http://127.0.0.1:8090/` (local demo store; tick *Allow Localhost*) → expect 4 pages, a CAPTCHA, a review item.
2. **CSV Batch Manager** → `demo_runtime\demo_batch_test.csv` (local fixtures) → expect the Expected-vs-Detected card (4 Match, 1 Mismatch, 1 Not accessible, 1 Not verified) and downloads.
3. **CSV Batch Manager** → `demo_runtime\real_pick_2.csv` (2 real sites) → expect real results or an honest "Not accessible".
