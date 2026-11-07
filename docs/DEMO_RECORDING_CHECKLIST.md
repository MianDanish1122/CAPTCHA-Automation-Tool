# Demo Recording Checklist

Use together with `DEMO_VIDEO_SCRIPT.md` (what to do/say) and `DEMO_ENVIRONMENT_GUIDE.md` (how to launch). Tick every box before pressing record.

## A. Environment (≈ 10 min)
- [ ] Demo database freshly reset **after** the rehearsal (`python -m scripts.demo_env setup --reset`) and the backend restarted
- [ ] Backend (8000), dashboard (3000) and demo website (8090) running; `http://127.0.0.1:8000/health` returns `{"status":"healthy"}`
- [ ] Rehearsal passed on this machine today (`python tests\demo_rehearsal.py` → 18/18, 0 leak findings) — then reset again
- [ ] Internet works (verification scenes call the providers' **test** endpoints) — or you are prepared to show the honest `provider_unavailable` result
- [ ] First OCR run already warmed (model loaded) — do it during the practice run
- [ ] Credentials file open **privately** on another monitor/window; never visible in the capture

## B. Privacy and secrets (the audience must see none of these)
- [ ] Recording only the **browser window** (or a fixed region), not the whole desktop
- [ ] Browser: clean profile or private window; **bookmarks bar hidden; saved passwords/autofill off**; no extensions visible; zoom 100 %; one tab
- [ ] Address bar shows only `localhost:3000` / `127.0.0.1` URLs
- [ ] OS notifications off (Focus Assist / Do Not Disturb), OneDrive/Teams/Slack/mail closed, taskbar auto-hidden or cropped out
- [ ] No terminal in frame. If a terminal must show, use a fresh window with a short prompt (`function prompt { '> ' }`), not your profile path
- [ ] **Never open:** the Settings page (prints local file-system paths), `.env`, `demo_runtime\demo_credentials.txt`, the Docs/Swagger link, the browser dev-tools/Network tab (shows bearer tokens), File Explorer
- [ ] The password is typed/pasted into the masked field only; pasting from a window that is outside the capture
- [ ] Only demo identities appear (`demo_operator`, `demo_operator@demo.invalid`); no real name/e-mail
- [ ] No real company names or third-party URLs in the Inspector (use `http://127.0.0.1:8090/`; the two refusal examples are an internal IP and `example.com`)

## C. Content accuracy (say / do not say)
- [ ] Say "**synthetic**" every time the 99.3 % / 100 % OCR numbers are mentioned; the on-screen amber/scope notes confirm it
- [ ] Say "**official test keys**" for verification scene ①② and "**simulated**" for ③; say "**local validation**" for ④
- [ ] State that **no production CAPTCHA is solved or bypassed** — detected and routed to a human
- [ ] Do not say "real verification" for test-key results; do not say "bypass", "defeat", "automate" about reCAPTCHA/hCaptcha/Turnstile
- [ ] Show at least **two failure cases**: policy refusal (scene 4) and verification failures/simulation (scene 10)
- [ ] If the single OCR evaluation misses, keep it and say failures are reported
- [ ] Do not edit away provider results; do not splice takes in a way that changes outputs

## D. Recording setup
- [ ] 1920×1080 (or 1440×900 as rehearsed), 30 fps, system + microphone audio; mic test done; quiet room
- [ ] Cursor highlighted/enlarged; pause 1–2 s on each result so it is readable
- [ ] Total length 5–7 min (script is ≈ 7:00 at a calm pace; scene 5 can be shortened)

## E. After recording (leak review — scrub the video, not just the files)
- [ ] Watch the whole video at 0.5× looking only at: address bar, tab titles, window title bars, taskbar, notification pop-ups, any path or e-mail
- [ ] Pause on the login scene: password shows as dots only
- [ ] Search the audio for spoken passwords/keys (none expected)
- [ ] Add captions or on-screen labels for **TEST KEYS** and **SIMULATED** if the audience may miss them
- [ ] Stop all three servers; delete `demo_runtime\` if no longer needed (it holds the demo passwords)
- [ ] Do not commit recordings that contain anything from section B; keep evidence in `evidence/demo_rehearsal/` (genuine rehearsal screenshots, no credentials)
- [ ] Share only the final video; do not share `demo_credentials.txt` or the demo database

## F. Quick reference — expected numbers on screen
| Where | Value |
| :--- | :--- |
| Evaluation, start | URL scans **0**, Pages inspected **0** (empty state) |
| Held-out table | legacy 97/300 (32.33 %), tuned 109/300 (36.33 %), custom 298/300 (99.33 %), hybrid 298/300 (99.33 %) — **own synthetic generator only** |
| Inspector scan of demo site | completed, **4 pages**, **1 contact page** |
| OCR benchmark (50 samples, held-out `test` split) | hybrid **50/50 (100 %)**; legacy **10/50 (20 %)**, char ≈ 70.9 % |
| Verification | ① provider test key → CONFIRMED ② Turnstile spent → `timeout-or-duplicate`, NOT VERIFIED ③ SIMULATED, provider called false ④ LOCAL VALIDATION |
| Evaluation, end | scans 1 · pages 4 · with CAPTCHA 1 (25 %) · attempts 4 (provider-confirmed 1, simulated 1) · human review 1 |
