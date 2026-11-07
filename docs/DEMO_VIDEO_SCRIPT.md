# Demonstration Video Script (target 6:30–7:00, allowed 5–7 min)

Audience: a hiring team reviewing the *CAPTCHA Solving & Verification Tool* assignment.
Environment: the dedicated demo environment (`docs/DEMO_ENVIRONMENT_GUIDE.md`) — owned demo site, demo database, demo accounts, no arbitrary scanning.
Every "expected output" below was **observed in a full rehearsal** (`tests/demo_rehearsal.py`: 16/16 steps, 0 leak findings, 0 console errors; screenshots in `evidence/demo_rehearsal/`). Numbers that are deterministic are marked **fixed**; numbers that vary run-to-run are marked *varies*.

## The three claims you must keep straight (say them in your own words)

| Term | Say |
| :--- | :--- |
| **Real provider verification** | "The provider verified a token with *my own* site secret." This demo does **not** do this — no production keys are used. Say so. |
| **Official test-key verification** | "The real provider endpoint answers, but it is using the provider's published *test* secret, which is built to accept/reject any token. It shows the integration works; it does not prove a human solved a production challenge." |
| **Simulated scenario** | "Generated locally to show error handling. No provider call is made and a simulation can never succeed." |

And always: **production CAPTCHAs are never solved or bypassed here — they are detected and sent to a human.** The solver works only on this project's *own synthetic* CAPTCHAs.

## Scenes

| # | Time | Duration | Screen / page | Exact action | Expected genuine output | What to say |
| :-: | :-: | :-: | :--- | :--- | :--- | :--- |
| 0 | 0:00 | 0:35 | Title slide (not the app — keeps file paths off screen) | none | slide with: project name, "synthetic/owned data only", "no paid solver", "no production CAPTCHA is solved" | "This tool detects and classifies CAPTCHAs, solves *synthetic* text CAPTCHAs with a custom model I trained, verifies tokens against the providers' official endpoints, and sends any real protected challenge to a human. I'll show success cases and failure cases." |
| 1 | 0:35 | 0:20 | `http://localhost:3000/login` | Type `demo_operator`; paste the password from the credentials file (shown as dots); click **Sign In** | Dashboard loads; top-right shows `demo_operator · OPERATOR` | "Accounts are provisioned by an administrator — there are no default credentials. Sessions are revocable server-side." |
| 2 | 0:55 | 0:50 | **Evaluation** (sidebar) | Scroll slowly from top to the OCR block and the *Held-out benchmark* table | Workflow of 8 steps; **URL scans 0, Pages inspected 0** (empty state, not placeholders); each block shows "Denominator: …"; held-out table (**fixed**, n=300): `tesseract_legacy` 97/300 (32.33%), `tesseract_tuned` 109/300 (36.33%), `custom_mlp` 298/300 (99.33%), `hybrid` 298/300 (99.33%); amber note: *"Scope: images from this project's own synthetic CAPTCHA generator only…"* | "Everything here is computed from stored data and states its denominator. This table is the measured benchmark on 300 held-out images. **Important limit:** it applies only to this project's own synthetic generator — not to reCAPTCHA, hCaptcha or Turnstile, which are never solved here." |
| 3 | 1:45 | 0:40 | **URL Inspector** | URL field: `http://127.0.0.1:8090/` · Max pages 5 · leave *Allow Localhost* checked · click the submit button; wait for the result | Scan completes in ~10 s: **4 pages crawled, 1 contact page found**; a production-style reCAPTCHA on `/contact` | "I'm scanning my own demo site on this machine. The crawler runs through an SSRF guard: allow-listed targets only, no private or metadata addresses." |
| 4 | 2:25 | 0:20 | **Safe failure #1** — same Inspector page | Replace the URL with `http://169.254.169.254/latest/meta-data/` and submit | red message: *"Security restriction: … cloud metadata IP (169.254.169.254) is prohibited."* (`https://example.com` gives *"not in the authorized domains allowlist"*) | "A failure case: the guard refuses internal and non-allow-listed targets before any request is made. The demo cannot be used to scan arbitrary sites." |
| 5 | 2:45 | 0:30 | **Scan History** → *Inspect* the scan → *View Evidence* on the Contact page | open the evidence of the Contact page | list of the 4 pages; screenshot of the contact form loads in the dialog (it is fetched with the session token, not a public URL) | "Evidence screenshots are served only to signed-in users." |
| 6 | 3:15 | 0:20 | **CAPTCHA Results** | none | row for `google_recaptcha`, strategy **queue for human review** | "A production-style reCAPTCHA was detected. The system does **not** try to solve it: it queues it for a person." |
| 7 | 3:35 | 0:30 | **Human Review** | click **Review Now** → type a note → **Mark Manually Verified** | case status becomes *manually verified*; the decision is stored with your identity | "Decisions are append-only and attributed: who decided, when, and why." |
| 8 | 4:05 | 0:25 | **OCR Laboratory** — single evaluation | leave `8K2MN` or click *Randomize* → **Run OCR Evaluation** | distorted image + cleaned image; ground truth vs **OCR Prediction**; *Engine: hybrid (custom_mlp)*; exact match usually (*varies*; first call is slower, ~0.5 s, while the model loads) | "This CAPTCHA was generated here, so the true label is known and the result is a real measurement. The default engine is my custom glyph model with Tesseract as fallback." |
| 9 | 4:30 | 0:50 | **OCR Laboratory** — benchmark | Engine **Hybrid**, Split **Held-out test set**, Samples **50** → **Run Benchmark**; then Engine **Tesseract (legacy pipeline)** → **Run Benchmark** | **fixed** on the first 50 samples of the committed split: hybrid **50/50 (100%)**, char 100%, ~7 ms/image; legacy **10/50 (20%)**, char ≈ 70.9%, ≈ 265 ms/image (*latency varies*) | "Same 50 images, same metric code. The old Tesseract pipeline gets about one in five; the custom model gets all of them — **on this project's own generator**. The full held-out result is 99.3% on 300 images, and I'm not claiming it generalises to other CAPTCHA families." |
| 10 | 5:20 | 0:55 | **Verification** | Run these four, one after another (provider / scenario → **Run verification**): ① Google reCAPTCHA / *Official test key* ② Cloudflare Turnstile / *Official test key: token already spent* ③ Google reCAPTCHA / *Simulated: expired* ④ hCaptcha / *Missing token* | ① badge **PROVIDER – OFFICIAL TEST KEYS**, **CONFIRMED BY PROVIDER**, provider called: true, HTTP 200 · ② **PROVIDER – OFFICIAL TEST KEYS**, **NOT VERIFIED**, `rejected_timeout_or_duplicate` (a genuine Turnstile response) · ③ **SIMULATED – NO PROVIDER CALL**, **NOT VERIFIED**, provider called: false · ④ **LOCAL VALIDATION**, `rejected_missing_token`, provider called: false | ① "Real provider endpoint, official *test* keys — integration works; not proof of a solved production challenge." ② "Still the provider's answer: its test secret reports a token as already spent." ③ "No call at all — a simulation that can never succeed." ④ "Rejected by my server before any provider call." |
| 11 | 6:15 | 0:30 | **Evaluation** again → **Download evaluation report** | refresh; scroll to *Verification outcomes*; click the download button | **URL scans 1 · Pages inspected 4 · Pages with a CAPTCHA 1 (25%)**; verification **Attempts 4, Confirmed by a provider 1, Simulated 1**; human review 1 case; a `.md` report downloads (same figures + denominators) | "The dashboard and the report come from the same stored records; simulated attempts are counted separately from provider-confirmed ones." |
| 12 | 6:45 | 0:15 | Closing slide | none | slide listing limits | "Limits: OCR accuracy is for my own synthetic generator; test keys prove the integration, not production solving; no paid solver; no production CAPTCHA is bypassed. Thank you." |

Machine time for the whole sequence in the rehearsal was 69–86 s; the rest is narration and cursor movement. Total ≈ 7:00 at the pace above — trim narration or skip scene 5 for a 6:30 cut.

## Safe fallbacks while recording
- **Provider unreachable (offline):** scenes 10① and ② will honestly show `provider_unavailable` / NOT VERIFIED. Say "this is the outage path" or retry with internet; do not edit the result.
- **A single OCR evaluation misses:** keep it — say "failures are reported, not hidden", then show the benchmark.
- **Scan takes > 20 s:** wait; do not cut away. If it fails, run `python -m scripts.demo_env setup --reset` and restart the backend (see the environment guide).

## Do not say / do not show
- Do not say the system "solves reCAPTCHA/hCaptcha/Turnstile", "bypasses", "defeats" or "automates" them. Say "detects and routes to a human".
- Do not say 99.3% "accuracy" without "on the project's own synthetic generator".
- Do not describe test-key results as "real verification".
- Do not open the credentials file, `.env`, a terminal showing your Windows profile path, or the browser's saved-password list.
