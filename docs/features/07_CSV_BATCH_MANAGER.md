# 7. CSV Batch Manager (the employer's main workflow)

**Purpose:** import the 200-row CSV (`USA_Ecommerce_Platforms_200_Contact_Pages.csv`) and scan every Contact Us page.

## How to use
1. Open `/batch`.
2. **Choose CSV**, then **Import & Validate CSV**. The summary shows total / valid / invalid rows, columns preserved and row-numbered errors.
3. Tick "Automatically start batch scan", or click **Launch Batch Scan**.
4. Watch the results table fill in. Click **Details** for robots status, widget state, expected value and screenshot.
5. Download the reports.

## For each site the tool
1. Checks robots.txt (stops on disallow, 401/403/429, challenge, 5xx).
2. Waits between requests to the same host (pacing).
3. Opens the Contact Page, detects the CAPTCHA, saves a screenshot.
4. Queues CAPTCHAs for human review and continues with the next site.
5. Compares the detected CAPTCHA with the CSV's "Captcha" column.

## Expected vs Detected
Match, Mismatch, Not detected, Not accessible (blocked or unreachable), Not verified (no expected value). The percentage uses only inspected rows that have an expected value, and the sample size is shown.

## Honest expectation
Many real sites block automated access. Those rows show "Not accessible"; they are not forced.
