# Final Assignment Compliance Matrix

Classification: **A** implemented and verified · **B** implemented, not verified on real websites · **C** partially implemented · **D** not implemented · **E** blocked by missing authorisation or external conditions.

## 1. Original assignment — weighted re-evaluation

Scores are my estimates from the evidence, not an external grade. Ranges reflect what a grader could reasonably decide.

| Criterion | Weight | Before this stage | Now (est.) | What changed / why not higher |
|---|---:|---:|---:|---|
| Recognition / solving accuracy | 30 | 24–26 | **25–27** | OCR 99.3 % exact on the 300-sample held-out set (own generator). Real-page CAPTCHA *recognition* (provider + subtype + widget loaded) now works on live pages: 2/2 inspectable real sites. Not higher: only synthetic CAPTCHAs are solved; real sample is 2 sites. |
| Verification-token handling | 20 | 16–17 | **18–19** | hCaptcha test-key acquisition fixed (root cause: provider script collision) → 3/3 providers acquire and are verified by the provider. Not higher: no production keys. |
| Custom AI / authorised API | 20 | 16–17 | **16–17** | Unchanged (custom model + tuned Tesseract + hybrid; no paid solver, stated). |
| Reliability and error handling | 15 | 12–13 | **13–14** | robots/access stop, continue-after-failure, per-host pacing, honest not-accessible, fail-closed lockdown, two UI crash defects found and fixed. Not higher: SQLite/single process. |
| Interface and reporting | 10 | 8–9 | **9** | Batch page: preserved columns, warnings, per-site result, expected-vs-detected card, authenticated downloads; real-browser tested (16/16). |
| Code quality and documentation | 5 | 4 | **4** | Docs and tests added; demo video still not recorded. |
| **Total** | **100** | **80–86** | **85–90** | |

**Honest conclusion:** 95 is **not supported**. A defensible figure is **about 87 (range 85–90)**. Getting to 90+ requires things this stage cannot manufacture: the recorded demo video, a larger authorised real-site sample (and accessible sites), and production-key verification.

## 2. Employer's additional message — separate matrix

| Requirement | Class | Evidence / note |
|---|---|---|
| Use the employer CSV and its Contact Page URLs | **A** | All 200 rows import, 8 columns preserved, contact page used directly (`test_employer_csv_imports_...`, live run). |
| Preserve every CSV column | **A** | Original row stored as JSON; unmapped columns kept (test, browser E2E). |
| Open real Contact Us pages with Playwright | **A** (2 sites) / **E** (2 sites) | barrett.net, breadtopia.com inspected; bigfrog.com 403 and wilton.com Cloudflare challenge → blocked by external conditions. |
| Wait for JavaScript content, inspect iframes and provider scripts | **A** | Delayed-JS, iframe, script-only v3, no-CAPTCHA pages (tests); live Barrett/Breadtopia. |
| Identify provider and subtype | **A** | invisible reCAPTCHA matched on a real site; Turnstile managed mode on another. |
| Check whether the widget loaded | **A** | `widget_state` / `widget_loaded` per site. |
| Inspect form structure | **A** | Fields, labels, types, required, maxlength, pattern, submit buttons, CAPTCHA-in-form. |
| Fill forms with synthetic data, do not submit | **A** | Real-site fill 4/4 fields per inspected site under lockdown; zero-request proof locally. |
| Never click or bypass a live CAPTCHA, never harvest tokens | **A** | Policy flags in evidence; token fields only by name. |
| Respect robots.txt / access restrictions, stop when blocked | **A** | Stop paths tested (disallow, 401/403/429, challenge, 5xx); live: 2 stops. |
| Reasonable request rate | **A** | Per-host interval (default 5 s), live gap 8 s. |
| Human-review records | **A** | Created by the batch workflow for every CAPTCHA site (test). |
| Batch uses the same detection logic as single-site | **A** | One shared engine `captcha_detection.py`. |
| Continue after failures; record failures | **A** | Test + not-accessible category. |
| Expected-vs-detected report with five categories, eligible-only metrics, sample size stated | **A** | API, CSV, Markdown, UI card; browser-verified. |
| Fix legitimate www/apex redirects safely | **A** | Tests (allowed + bypass attempts blocked). |
| Provider widgets under a guarded network | **A** | Narrow policy; SSRF/DNS/TLS still enforced. |
| Improve hCaptcha test evidence | **A** | 3/3 test-key verifications; widget evidence screenshots. |
| CSV formula-injection protection | **A** | Unit tests and real download check. |
| Statistical accuracy on real sites | **C** | Sample of 2 eligible sites; explicitly not a benchmark. |
| Submitting contact forms / solving real CAPTCHAs | **E** | Excluded by the assignment text and by the no-transmission instruction; needs written authorisation. |
| Demonstration video | **D** (human) | Script updated; not recorded. |
| Production-key verification | **E** | No production keys supplied. |
