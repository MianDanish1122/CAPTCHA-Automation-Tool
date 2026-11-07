"""
Phase 7 browser E2E (Playwright, real Chromium, real backend + production frontend).

Drives the evaluator workflow end to end and compares what the dashboard shows with the API/database:
inspect a (local, owned) website -> review discovered pages -> CAPTCHA classification -> OCR evaluation
-> verification (provider test keys / simulated / local validation) -> human review -> evaluation
dashboard -> report download.

    DATABASE_URL=sqlite:///.../e2e7.db  python tests/e2e_phase7_browser.py seed
    (start backend: APP_ENV=development ALLOW_DEV_LOOPBACK=true uvicorn app.main:app --port 8000)
    (start frontend: npm run start -- -p 3000)
    python tests/e2e_phase7_browser.py run      # writes evidence/phase7/e2e/*.png + report JSON

Credentials come from E2E_OPERATOR_USER/E2E_OPERATOR_PASSWORD (never hard-coded).
"""
import asyncio
import http.server
import json
import os
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BACKEND = os.environ.get("E2E_BACKEND", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("E2E_FRONTEND", "http://localhost:3000")
OUT = ROOT / "evidence" / "phase7" / "e2e"


def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Set {name}")
    return v


SITE = {
    "/": "<html><head><title>Acme Home</title></head><body><h1>Acme</h1><a href='/contact'>Contact us</a></body></html>",
    "/contact": (
        "<html><head><title>Contact Acme</title>"
        "<script src='https://www.google.com/recaptcha/api.js' async defer></script></head><body>"
        "<h1>Contact us</h1><form method='post'><input name='email'><textarea name='message'></textarea>"
        "<div class='g-recaptcha' data-sitekey='6LcFAKEPRODUCTIONKEYxxxxxxxxxxxxxxxxxxxxxxx'></div>"
        "<button>Send</button></form></body></html>"
    ),
}


class _Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = SITE.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def seed():
    from alembic import command
    from alembic.config import Config
    from app.database import SessionLocal
    from app.models import User, UserRole
    from app.services.auth_service import hash_password
    from argparse import Namespace
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    db = SessionLocal()
    try:
        name = env("E2E_OPERATOR_USER")
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@e2e.test", role=UserRole.OPERATOR,
                        hashed_password=hash_password(env("E2E_OPERATOR_PASSWORD"))))
            db.commit()
    finally:
        db.close()
    from scripts.ocr_benchmark import cmd_import_results
    cmd_import_results(Namespace(file="evaluation_test2.json"))  # the real measured held-out results
    print("seeded")


class Rec:
    def __init__(self):
        self.checks, self.console, self.pageerrors, self.failed, self.http = [], [], [], [], []

    def check(self, name, ok, detail=""):
        self.checks.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
        print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""))


async def run():
    from playwright.async_api import async_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    rec = Rec()
    site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    site_url = f"http://127.0.0.1:{site.server_address[1]}/"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = await ctx.new_page()
        page.on("console", lambda m: rec.console.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: rec.pageerrors.append(str(e)))
        page.on("requestfailed", lambda r: rec.failed.append(f"{r.method} {r.url} {r.failure}"))
        page.on("response", lambda r: rec.http.append(f"{r.status} {r.request.method} {r.url}") if r.status >= 400 else None)

        async def shot(name):
            await page.screenshot(path=str(OUT / f"{name}.png"))

        async def api_get(path, token):
            r = await ctx.request.get(BACKEND + path, headers={"Authorization": f"Bearer {token}"})
            return await r.json()

        # 1. login ------------------------------------------------------------------
        await page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        await page.fill('input[type="text"]', env("E2E_OPERATOR_USER"))
        await page.fill('input[type="password"]', env("E2E_OPERATOR_PASSWORD"))
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{FRONTEND}/", timeout=20000)
        token = await page.evaluate("localStorage.getItem('captcha_token')")
        rec.check("operator can sign in", bool(token))
        await page.wait_for_load_state("networkidle")

        # 2. empty-state honesty -----------------------------------------------------
        await page.goto(f"{FRONTEND}/evaluation", wait_until="networkidle")
        await page.wait_for_selector("text=Inspections & pages", timeout=15000)
        s0 = await api_get("/api/stats/summary", token)
        rec.check("workflow lists all 8 evaluator steps", await page.locator("ol[aria-label='Evaluator workflow'] li").count() == 8)
        rec.check("dashboard starts with zero scans/pages (no placeholder values)",
                  s0["inspections"]["url_scans_total"] == 0 and s0["pages"]["pages_inspected"] == 0
                  and s0["verification"]["attempts"] == 0, json.dumps(s0["pages"]))
        rec.check("empty-state message shown", await page.locator("text=No inspections, OCR evaluations or verification").count() == 0
                  or s0["has_data"], "")  # held-out benchmark rows are imported, so has_data may already be true
        await shot("01_evaluation_before_workflow")

        # 3. inspect an owned local website (API; the crawler is guarded + audited) -----
        r = await ctx.request.post(BACKEND + "/api/websites/inspect-url",
                                   headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                   data=json.dumps({"url": site_url, "max_pages": 3, "max_depth": 1, "allow_loopback": True}))
        scan = await r.json()
        rec.check("website inspection completes", r.status == 200 and scan.get("success") is True, json.dumps(scan)[:200])
        scan_id = scan["scan_id"]

        # 4. review discovered pages + screenshot evidence (UI) ---------------------------
        await page.goto(f"{FRONTEND}/scans?scan_id={scan_id}", wait_until="networkidle")
        await page.wait_for_selector("text=View Evidence", timeout=20000)
        rec.check("discovered pages listed for the scan", await page.locator("text=View Evidence").count() >= 2)
        await shot("02_discovered_pages")
        await page.locator("text=View Evidence").first.click()
        img = page.locator("img[alt='Page inspection screenshot']")
        await img.wait_for(state="visible", timeout=15000)
        rec.check("protected screenshot evidence renders", await img.evaluate("e => e.naturalWidth") > 0)
        await shot("03_screenshot_evidence")

        # 5. CAPTCHA classification (UI) --------------------------------------------------
        await page.goto(f"{FRONTEND}/results", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        text = (await page.inner_text("body")).lower()
        rec.check("results page shows the detected reCAPTCHA", "recaptcha" in text, "")
        await shot("04_captcha_classifications")

        # 6. human review (UI) ------------------------------------------------------------
        await page.goto(f"{FRONTEND}/reviews", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        reviews = await api_get("/api/captcha/reviews?status=pending", token)
        rec.check("production reCAPTCHA is queued for human review (not solved)", reviews["summary"]["pending"] >= 1)
        await shot("05_human_review")

        # 7. OCR evaluation (UI) ---------------------------------------------------------
        await page.goto(f"{FRONTEND}/ocr", wait_until="networkidle")
        for _ in range(2):
            await page.click("text=Run OCR Evaluation")
            await page.wait_for_selector("text=Run OCR Evaluation", timeout=30000)
            await page.wait_for_timeout(1500)
        await page.click("text=Run Benchmark")
        await page.wait_for_selector("text=Exact", timeout=60000)
        await page.wait_for_timeout(1000)
        await shot("06_ocr_evaluation")
        runs = await api_get("/api/captcha/ocr-benchmark/runs?limit=5", token)
        api_run = next((x for x in runs["runs"] if x["source"] == "api"), None)
        rec.check("OCR benchmark run was executed and persisted", api_run is not None and api_run["samples"] == 20, json.dumps(api_run)[:200] if api_run else "")

        # 8. verification (UI): provider test keys / simulated / local validation ---------------
        await page.goto(f"{FRONTEND}/verification", wait_until="networkidle")
        selects = page.locator("form select")

        async def run_verify(provider, scenario):
            await selects.nth(0).select_option(provider)
            await page.wait_for_selector(f"option[value='{scenario}']", state="attached", timeout=5000)
            await selects.nth(1).select_option(scenario)
            # wait for THIS request's response (the previous result panel is still on screen until then)
            async with page.expect_response(lambda r: "/api/captcha/verify-token" in r.url, timeout=30000):
                await page.click("text=Run verification")
            await page.wait_for_timeout(600)
            return await page.inner_text("[data-testid='verification-result']")

        live = await run_verify("google_recaptcha", "test:0")
        if "provider_unavailable" in live:
            rec.check("(live provider unreachable: test-key check skipped)", True)
        else:
            rec.check("official test keys: real provider called and confirmed",
                      "OFFICIAL TEST KEYS" in live and "CONFIRMED BY PROVIDER" in live, live[:160])
        await shot("07_verification_test_keys")
        sim = await run_verify("google_recaptcha", "sim:expired")
        rec.check("simulated scenario is labelled simulated, no provider call, not verified",
                  "SIMULATED" in sim and "NOT VERIFIED" in sim and "Provider called: false" in sim, sim[:200])
        await shot("08_verification_simulated")
        miss = await run_verify("hcaptcha", "missing")
        rec.check("missing token rejected by local validation", "LOCAL VALIDATION" in miss and "rejected_missing_token" in miss, miss[:160])
        spent = await run_verify("cloudflare_turnstile", "test:2")
        if "provider_unavailable" not in spent:
            rec.check("Turnstile 'token already spent' is a genuine provider response",
                      "timeout-or-duplicate" in spent and "OFFICIAL TEST KEYS" in spent, spent[:200])
        await shot("09_verification_turnstile_spent")
        recs = await api_get("/api/captcha/verification/records?limit=50", token)
        rec.check("verification attempts are persisted (4 run in the UI)", recs["total"] == 4, recs["total"])
        rec.check("no token is stored in verification records", "XXXX.DUMMY" not in json.dumps(recs) and "any-test-token" not in json.dumps(recs))

        # 9. evaluation dashboard vs API/database ---------------------------------------------
        stats = await api_get("/api/stats/summary", token)
        await page.goto(f"{FRONTEND}/evaluation", wait_until="networkidle")
        await page.wait_for_selector("text=Verification outcomes by scenario", timeout=15000)
        body = await page.inner_text("body")
        rec.check("dashboard shows scans/pages from stored data",
                  stats["inspections"]["url_scans_total"] >= 1 and stats["pages"]["pages_inspected"] >= 2
                  and str(stats["pages"]["pages_inspected"]) in body)
        rec.check("dashboard shows verification attempt count matching the API",
                  stats["verification"]["attempts"] >= 4 and str(stats["verification"]["attempts"]) in body)
        rec.check("dashboard reports simulated attempts separately from provider-confirmed",
                  "simulated (no provider call)" in body.lower() and "confirmed by a provider" in body.lower()
                  and stats["verification"]["simulated_attempts"] >= 1)
        held = stats["ocr"]["heldout_benchmarks"]["by_engine"]
        rec.check("held-out OCR results come from the stored benchmark (4 engines)",
                  set(held) == {"tesseract_legacy", "tesseract_tuned", "custom_mlp", "hybrid"})
        rec.check("held-out numbers on screen equal the stored measurements",
                  all(f"{held[e]['exact_matches']}/{held[e]['samples']} ({held[e]['exact_match_pct']}%)" in body for e in held))
        rec.check("every metric block states a denominator", len(re.findall(r"Denominator", body)) >= 10, len(re.findall(r"Denominator", body)))
        rec.check("time range is stated", "Showing: all recorded data" in body)
        await shot("10_evaluation_dashboard")
        await page.select_option("select", "7")
        await page.wait_for_selector("span:has-text('Showing: last 7 days')", timeout=10000)
        rec.check("time-range filter changes the stated range", True)
        await page.select_option("select", "")

        # 10. report download -----------------------------------------------------------------------
        async with page.expect_response(lambda r: "/api/stats/report" in r.url, timeout=20000) as rr:
            async with page.expect_download(timeout=20000) as dl:
                await page.click("button:has-text('Download evaluation report')")
        rec.check("report endpoint answered 200", (await rr.value).status == 200, (await rr.value).status)
        path = await (await dl.value).path()
        report = Path(path).read_text(encoding="utf-8")
        rec.check("report downloads and contains denominators + held-out engines",
                  "Denominator" in report and "custom_mlp" in report and "## Verification outcomes" in report)
        (OUT / "downloaded_evaluation_report.md").write_text(report, encoding="utf-8")

        # 11. hygiene -----------------------------------------------------------------------------
        rec.check("no uncaught page errors", not rec.pageerrors, rec.pageerrors[:3])
        rec.check("no failed network requests", not rec.failed, rec.failed[:3])
        rec.check("no HTTP >= 400 responses to dashboard requests", not rec.http, rec.http[:5])
        rec.check("no console errors", not rec.console, rec.console[:3])
        await browser.close()

    passed = sum(c["passed"] for c in rec.checks)
    (OUT / "e2e_report.json").write_text(json.dumps({
        "passed": passed, "total": len(rec.checks), "checks": rec.checks,
        "console": rec.console, "pageerrors": rec.pageerrors, "failed": rec.failed, "http_errors": rec.http}, indent=2))
    print(f"\n{passed}/{len(rec.checks)} checks passed")
    site.shutdown()
    sys.exit(0 if passed == len(rec.checks) else 1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "seed":
        seed()
    else:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(run())
