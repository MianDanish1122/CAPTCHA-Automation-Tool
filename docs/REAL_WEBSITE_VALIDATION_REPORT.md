# Real Website Validation Report

Run date: 2026-11-07. Tool: `python -m scripts.real_site_validation` (same engine as the batch workflow). Evidence: `evidence/final_qa/real_sites/` (`results.json`, per-site JSON, screenshots, `run_log.txt`, `robots_check.json`).

## Sample and rules
The four sites you approved, taken from the employer CSV (its own Contact Page URLs). Rules enforced by code, not by promise: robots.txt first and a stop on any restriction; one visit per site at least 8 s apart; egress limited to the approved hosts plus GET-only CAPTCHA-provider widget hosts; the form is filled only under a no-transmission lockdown; nothing is submitted; no CAPTCHA is clicked.

## Results

| Site | CSV expected | Robots / access | Detected | Widget | Forms / filled | Result |
|---|---|---|---|---|---|---|
| barrett.net | invisible reCAPTCHA | robots allowed | Google reCAPTCHA, subtype **invisible** | iframe loaded | 3 forms / 4 fields | **Match** (subtype agrees) |
| breadtopia.com | Turnstile | robots allowed | Cloudflare Turnstile (managed / non-interactive) | iframe loaded | 6 forms / 4 fields | **Match** |
| bigfrog.com | hCaptcha | robots allowed, but the contact page returned **HTTP 403** | none (page not inspected) | n/a | n/a | **Not accessible** |
| wilton.com | reCAPTCHA | robots.txt returned a **Cloudflare challenge** (HTTP 403, `cf-mitigated`) | not inspected | n/a | n/a | **Not accessible** |

Stopped, not worked around: no retry, no header changes, no alternative route for wilton.com or bigfrog.com. A substitute site needs your approval.

## What this does and does not prove
- 2 of 4 sites were eligible for scoring; 2/2 agree. **This is a demonstration, not an accuracy benchmark.** A rate over 2 sites says nothing statistical.
- 50 % of the sample could not be inspected. That is a genuine finding about real-world access (bot protection), not a tool failure.
- Big Frog was visited with the honest crawler user agent; it may be that agent being refused.

## Finding fixed after the run
The Breadtopia result originally listed **hCaptcha as well as Turnstile**. Rendered-DOM evidence showed only Turnstile; the extra entry came from the older static detector matching the text "hcaptcha.com" in the page source. The shared detector now reports providers seen only as source text as `unconfirmed_static_mentions` instead of detections (two regression tests). The live evidence file was **not** regenerated (no further requests to the site); it still shows the pre-fix list.

## Evidence of the no-transmission policy
Form probe policy flags on both inspected sites: `network_locked`, `browser_offline`, `submit_shield` true; `submit_clicked`, `enter_pressed`, `captcha_touched`, `data_transmitted` false. The pages' own CAPTCHA telemetry POSTs and requests during the fill were refused by the guard (logged in `run_log.txt`). Local proof with a request-logging server: zero requests reached the server for JS submit, `requestSubmit`, fetch, XHR, `sendBeacon`, image beacons and Enter key (`tests/test_realworld_stage1_network_policy.py`, `..._stage4_form_probe.py`).
