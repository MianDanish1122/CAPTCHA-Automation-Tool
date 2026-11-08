# 2. Scan History

**Purpose:** permanent record of every inspection ever run. This is where you see what was detected and of which type.

## How to use
1. Open `/scans`.
2. Search by URL, domain or scan id. Filter: All / Completed / Crawling / Failed. Use refresh for new scans.
3. Click **Inspect** on a row to open that scan's pages and screenshots.

## Columns
Target, scan id, status, pages crawled, contact pages found, CAPTCHA providers found, duration, time.

## Reading a row
- **Completed + provider name** (for example Google reCAPTCHA): CAPTCHA identified.
- **Completed + None Detected + pages > 0**: pages were read and no CAPTCHA was found.
- **Failed**: the page could not be read (timeout, blocked, unreachable). The reason is shown. This is not evidence that the site has no CAPTCHA.
