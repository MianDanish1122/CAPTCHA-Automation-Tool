# 1. URL Inspector

**Purpose:** inspect one website. You give a URL; the tool opens it, finds contact/support pages and forms, and detects CAPTCHAs.

## How to use
1. Open `/inspector`.
2. Enter the Target Website URL (a contact-page URL inspects that page; a home page lets the tool discover contact pages).
3. Set Max Pages (1-20) and Crawl Depth (0-3). Use 1 and 0 for a single page.
4. Tick *Allow Localhost* only for your own local test site.
5. Click **Start Live Inspection**.

## What happens inside
- Checks the URL against the allow-list and SSRF rules (private/internal addresses are refused).
- Checks robots.txt; stops if the site disallows.
- Loads each page in Chromium, waits for it to settle, reads the rendered DOM, scripts and iframes.
- Detects Google reCAPTCHA, hCaptcha, Cloudflare Turnstile and others; records subtype and widget state.
- Counts forms, saves a screenshot, stores everything in the database.

## What you see
- Cards: Crawled Pages, Contact Touchpoints, CAPTCHA Detected, Crawl Duration.
- "Discovered Pages & Evidence": one row per page with provider, forms, handling (`human_review` or `no_challenge`) and an **Inspect** button (screenshot + details).

## Failure behaviour
If no page could be read (for example a timeout) the scan is **Failed** with the reason. It is never reported as "no CAPTCHA". Page timeout is 30 s (`CRAWLER_PAGE_TIMEOUT_MS`).
