# CAPTCHA Inspector - Feature Documents (one file per module)

Technology Brainz assignment: import a CSV of Contact Us pages, identify the CAPTCHA on each, and make sure CAPTCHAs do not stop the workflow.

## What "handle" means in this tool (read first)
| The tool DOES | The tool does NOT |
|---|---|
| Open the page in headless Chromium (Playwright) | Solve or bypass reCAPTCHA / hCaptcha / Turnstile |
| Detect and classify the CAPTCHA (provider, type, widget state) | Click, tick or interact with a live CAPTCHA |
| Save a screenshot and evidence | Submit any form or harvest tokens |
| Route every CAPTCHA to a **human review queue** so the batch keeps going | Work around robots.txt or access blocks |
| Solve **our own synthetic text CAPTCHAs** with OCR (OCR Laboratory) | |

Reason: solving or bypassing third-party CAPTCHAs is against their terms and would be unauthorised access. The workflow is not blocked: a CAPTCHA is identified, logged and queued, and the batch moves on to the next site.

## Modules
| # | File | Screen |
|---|---|---|
| 1 | 01_URL_INSPECTOR.md | URL Inspector |
| 2 | 02_SCAN_HISTORY.md | Scan History |
| 3 | 03_CAPTCHA_RESULTS.md | CAPTCHA Results |
| 4 | 04_HUMAN_REVIEW.md | Human Review |
| 5 | 05_OCR_LABORATORY.md | OCR Laboratory |
| 6 | 06_VERIFICATION.md | Verification |
| 7 | 07_CSV_BATCH_MANAGER.md | CSV Batch Manager |
| 8 | 08_REPORTS.md | Reports |
| 9 | 09_EVALUATION_AND_OVERVIEW.md | Evaluation and Overview |
| 10 | 10_SETTINGS_AND_SECURITY.md | Settings, login, security |

Typical flow: URL Inspector -> Scan History -> CAPTCHA Results -> Human Review. For many sites: CSV Batch Manager -> Reports.
