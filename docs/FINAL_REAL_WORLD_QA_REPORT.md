# Final Real-World QA Report

Technology Brainz - CAPTCHA Inspector. Stage: real-world QA, completion and production readiness. **Nothing is committed, pushed or deployed**; awaiting your review.

## 1. Outcome in one paragraph
The tool now inspects real contact pages the way the brief describes: it reads the employer CSV (all columns kept), goes to each row's Contact Page, respects robots.txt and access restrictions, waits for JavaScript widgets, identifies provider, subtype and whether the widget loaded, records the form's fields and shows it can be filled with fake data without sending anything, queues a human review, and reports expected-vs-detected honestly. On the four approved real sites: 2 inspected and matched (invisible reCAPTCHA, Turnstile), 2 blocked by bot protection and reported as not accessible. **Honest score: about 87/100 (range 85-90); 95 is not supported.**

## 2. Method
Baseline preserved first (445 passed; build 15/15; browser 30/30, 32/32, 19/19; commit `f5c7df8`; tag). Six controlled stages, each with new tests and regression runs, then real-site validation, then full browser regression.

## 3. What was built (by your priorities)
| Priority | Result |
|---|---|
| Preserve all CSV columns | Done; original row stored verbatim; unmapped columns kept |
| Use CSV Contact Page URLs | Done; fallback to discovery if missing/404 |
| Safe www/apex redirects | Done; only that pair; bypass attempts still blocked |
| Better JS / iframe detection | Done; rendered-DOM engine with bounded waits |
| Shared engine single-site + batch | Done; `captcha_detection.py` |
| Per-site results + human-review records | Done; one review record per CAPTCHA site, linked by `inspection_id` |
| Expected-vs-detected | Done; 5 categories, eligible-only metrics, API/CSV/Markdown/UI |
| hCaptcha test evidence | Done; root cause fixed; 3/3 providers verified (test keys) |
| CSV formula-injection protection | Done |
| Preserve security architecture | Done; all earlier tests pass; provider policy is narrow and keeps IP/DNS/TLS checks |
| No transmission / no CAPTCHA interaction | Enforced in code (lockdown, offline, submit shield); tested against a hostile page |
| robots.txt / access restrictions | Checked first; stops; no workaround |

## 4. Real websites
See `REAL_WEBSITE_VALIDATION_REPORT.md`. Summary: barrett.net Match, breadtopia.com Match, bigfrog.com Not accessible (HTTP 403), wilton.com Not accessible (Cloudflare challenge). Eligible sample = 2: demonstration only.

## 5. Findings worth your attention
- Two UI defects predating this stage (batch screen crash on scan; unauthenticated download links) were found only because this stage drove the real browser.
- A static-text false positive (hCaptcha on Breadtopia) was found by comparing rendered evidence with the detector's output, and fixed.
- Blocked sites are common; plan for a large not-accessible share in any bigger run.

## 6. Classification (A-E)
See `FINAL_ASSIGNMENT_COMPLIANCE_MATRIX.md`. Summary: A for everything buildable and verifiable; C for statistical accuracy on real sites; E for form submission / CAPTCHA solving (no authorisation) and production-key verification; D for the demo video (human).

## 7. Scope conflict (unchanged, flagged)
The assignment document excludes contact-form automation; the employer message asks for Playwright interaction. Implemented the safe intersection: inspection + non-submitting fill. Anything beyond needs written authorisation.

## 8. Deliverables
`REAL_WEBSITE_VALIDATION_REPORT.md`, `FINAL_FUNCTIONAL_TEST_REPORT.md`, `FINAL_SECURITY_REVIEW.md`, `FINAL_REMAINING_RISKS.md`, `FINAL_ASSIGNMENT_COMPLIANCE_MATRIX.md`, `FINAL_DEPLOYMENT_READINESS_CHECKLIST.md`, README section, demo-script addendum; evidence in `evidence/final_qa/`.

## 9. Decisions needed from you
1. Review the diff; approve (or not) a commit.
2. Substitute sites for wilton.com and bigfrog.com, or accept them as not accessible.
3. Whether to regenerate the Breadtopia live evidence (one more polite request).
4. Align the batch user agent with the honest crawler agent before production.
