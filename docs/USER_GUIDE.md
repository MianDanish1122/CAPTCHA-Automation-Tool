# User Guide & Demonstration Checklist

## Roles
- **Operator**: inspect, classify, run OCR/verification, review CAPTCHA cases, download reports.
- **Administrator**: everything above plus users, audit trail and its verification (Settings page).
Accounts are created with `python -m app.cli create-admin` / `create-user` (prompted, never hard-coded).

## Evaluator workflow (matches the Evaluation page's 8 steps)

| Step | Page | What to do | What you should see |
| :-- | :-- | :--- | :--- |
| 1 | **Evaluation** | open it first | live metrics from stored data, each with its denominator and time range; a time-range filter; "Download evaluation report" |
| 2 | **URL Inspector** | enter an authorised URL (e.g. your local demo site `http://127.0.0.1:<port>/` in development) | crawl starts; contact pages are discovered; external domains are not crawled |
| 3 | **Scan History** → *Inspect* → *View Evidence* | review pages, forms, scores | per-page evidence and an authenticated screenshot |
| 4 | **CAPTCHA Results** | filter by provider | provider, challenge type, handling strategy (e.g. `queue_for_human_review`) |
| 5 | **OCR Laboratory** | *Run OCR Evaluation* (one synthetic CAPTCHA) and *Run Benchmark* (pick engine, split, samples) | image, true label, prediction, exact/character accuracy, latency; benchmark totals; runs are stored |
| 6 | **Verification** | choose provider + scenario → *Run verification* | a badge naming the **mode** (official test keys / simulated / local validation) and whether the **provider** confirmed |
| 7 | **Human Review** | open a pending case, decide, add notes | decision recorded with your identity; history kept |
| 8 | **Reports** / Evaluation | download the evaluation report (Markdown) or batch CSV | figures identical to the dashboard, with denominators |

## Reading the verification badges

| Badge | Meaning |
| :--- | :--- |
| **PROVIDER – OFFICIAL TEST KEYS** | the real provider endpoint answered with its published test secret; shows the integration works, **not** that a human solved a real challenge |
| **PROVIDER – REAL KEY** | verified by the provider with a secret you supplied |
| **SIMULATED – NO PROVIDER CALL** | generated locally to show error handling; can never succeed |
| **LOCAL VALIDATION** | rejected by the server before contacting the provider |
| **CONFIRMED BY PROVIDER / NOT VERIFIED** | `success` — true only when the provider itself said so |

## Safe usage rules
Only scan sites you are authorised to test; production CAPTCHAs are never solved — they appear in Human Review. Do not paste real users' tokens or production secrets into the verification form.

---

# Demo video — plan and checklist

> The current, rehearsed script is `docs/DEMO_VIDEO_SCRIPT.md` (with `DEMO_RECORDING_CHECKLIST.md` and `DEMO_ENVIRONMENT_GUIDE.md`). The summary below is the earlier outline.

The assignment requires a recorded demonstration showing **success and failure cases**. Recording is a human step; this is a rehearsed script (all steps have automated evidence in `evidence/phase7/e2e/`).

**Before recording:** backend + frontend running; a clean browser profile; DB with the held-out OCR results imported (`ocr_benchmark import-results`); local demo site available or the E2E script's page; internet on (live provider test keys); screen resolution 1440×900.

| Time | Scene | Say / show | Success or failure |
| :-- | :--- | :--- | :--- |
| 0:00–0:20 | Architecture slide / README top | what is solved (synthetic only), what is detected & routed to humans, no paid solver | — |
| 0:20–0:50 | Login → Evaluation dashboard | zero/real values, denominators, workflow steps | — |
| 0:50–1:30 | Inspect owned site → Scan History → evidence screenshot → CAPTCHA Results | reCAPTCHA detected, strategy = human review | **success** (detection), **safe failure** (not solved) |
| 1:30–2:20 | OCR Laboratory: one evaluation, then benchmark (hybrid, test split, 50 samples) | true label vs prediction, exact/char accuracy, latency; open the stored held-out table (custom 99.3 % vs legacy 32.3 %); mention it is the project's own generator | **success** + a visible miss if one occurs |
| 2:20–3:20 | Verification page: (a) reCAPTCHA official test key → confirmed; (b) Turnstile "token already spent" → genuine provider `timeout-or-duplicate`; (c) simulated expired → badge SIMULATED, not verified; (d) missing token → LOCAL VALIDATION | explain the four modes | **success + 3 failure cases** |
| 3:20–3:50 | Human Review: decide a case; show history | identity recorded | — |
| 3:50–4:30 | Evaluation → download report; show provider-confirmed vs simulated counts | numbers match | — |
| 4:30–5:00 | Security & limits | SSRF guard, auth/revocation, audit chain; limits: in-distribution OCR, test keys ≠ production proof | — |

**Checklist:** ☐ no secrets visible (hide `.env`, tokens) ☐ show a *failure* in OCR or verification ☐ state "test keys" wherever used ☐ say clearly that no production CAPTCHA was solved ☐ keep under 5:00 ☐ export with captions if possible.
