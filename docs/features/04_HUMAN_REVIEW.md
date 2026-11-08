# 4. Human Review (how CAPTCHAs are "handled")

**Purpose:** the queue of CAPTCHAs that a person must decide on. This is what keeps the workflow moving: the scanner never waits on a CAPTCHA; it records it here and continues.

## How to use
1. Open `/reviews`.
2. Click **Review Now** on an item. See the page URL, provider, challenge type, reason and screenshot.
3. Mark Approved / Rejected / Manually verified and add notes.

## Guarantees
- Each decision is stored with who made it and when (audit trail).
- The system never solves, clicks or bypasses the CAPTCHA itself.
- Confidence shows "-" when unknown (never "NaN%").
