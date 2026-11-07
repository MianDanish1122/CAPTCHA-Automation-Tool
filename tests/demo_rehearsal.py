"""
Rehearsal of the recorded demonstration: performs every step of docs/DEMO_VIDEO_SCRIPT.md in a real browser
against the DEMO environment, times each step, checks the expected output, and scans every page the audience
would see for leaked personal/internal details.

    (demo environment running: backend :8000, frontend :3000, demo site :8090)
    python tests/demo_rehearsal.py            # reads demo_runtime/demo_credentials.txt (never printed)

Output: evidence/demo_rehearsal/rehearsal_report.json + screenshots of the real results.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREDS = ROOT / "demo_runtime" / "demo_credentials.txt"
OUT = ROOT / "evidence" / "demo_rehearsal"
BACKEND, FRONTEND, SITE = "http://127.0.0.1:8000", "http://localhost:3000", "http://127.0.0.1:8090/"


def load_creds():
    creds = {}
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"(operator|admin)\s+username=(\S+)\s+password=(\S+)", line)
        if m:
            creds[m.group(1)] = (m.group(2), m.group(3))
    return creds


class Rehearsal:
    def __init__(self, secrets_to_hide):
        self.steps, self.leaks, self.console, self.failed, self.http = [], [], [], [], []
        patterns = [r"C:\\Users", r"C:/Users", r"AppData", r"OneDrive", r"\bHp\b", r"@gmail", r"@outlook",
                    r"JWT_SECRET", r"AUDIT_HMAC", r"BEGIN (RSA|PRIVATE)", r"eyJ[A-Za-z0-9_-]{10,}\.", r"\.env\b",
                    r"password\s*[:=]", r"Bearer\s+[A-Za-z0-9._-]{12,}"]
        self.regexes = [re.compile(p, re.I) for p in patterns]
        self.secrets = [s for s in secrets_to_hide if s]

    def scan(self, where, text):
        for rx in self.regexes:
            m = rx.search(text)
            if m:
                self.leaks.append({"where": where, "pattern": rx.pattern, "context": text[max(0, m.start() - 30):m.end() + 30]})
        for s in self.secrets:
            if s in text:
                self.leaks.append({"where": where, "pattern": "<a demo secret value>", "context": "[redacted]"})

    def step(self, name, started, ok, detail=""):
        dur = round(time.perf_counter() - started, 1)
        self.steps.append({"step": name, "ok": bool(ok), "seconds": dur, "detail": str(detail)[:240]})
        print(("PASS " if ok else "FAIL ") + f"{name} ({dur}s)" + (f" -- {detail}" if detail and not ok else ""))


async def main() -> int:
    from playwright.async_api import async_playwright
    creds = load_creds()
    op_user, op_pw = creds["operator"]
    adm_pw = creds["admin"][1]
    R = Rehearsal([op_pw, adm_pw])
    OUT.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = await ctx.new_page()
        page.on("console", lambda m: R.console.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: R.failed.append(f"{r.method} {r.url}"))
        page.on("response", lambda r: R.http.append(f"{r.status} {r.url}") if r.status >= 400 else None)

        async def seen(name):
            await page.wait_for_timeout(500)
            R.scan(name + " (text)", await page.inner_text("body"))
            html = re.sub(r"<input[^>]*type=\"password\"[^>]*>", "<input password-field>", await page.content())
            R.scan(name + " (html)", html)
            await page.screenshot(path=str(OUT / f"{name}.png"))

        async def api(path, token, method="get", data=None):
            fn = getattr(ctx.request, method)
            kw = {"headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}}
            if data is not None:
                kw["data"] = json.dumps(data)
            r = await fn(BACKEND + path, **kw)
            return await r.json()

        # S1 login ---------------------------------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        await page.fill('input[type="text"]', op_user)
        await page.fill('input[type="password"]', op_pw)
        await seen("01_login_filled")
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{FRONTEND}/", timeout=20000)
        await page.wait_for_load_state("networkidle")
        token = await page.evaluate("localStorage.getItem('captcha_token')")
        R.secrets.append(token)
        await seen("02_after_login")
        R.step("S1 login", t, bool(token))

        # S2 evaluation dashboard (empty state + held-out table) ---------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/evaluation", wait_until="networkidle")
        await page.wait_for_selector("text=Held-out benchmark", timeout=15000)
        body = await page.inner_text("body")
        await seen("03_evaluation_start")
        s = await api("/api/stats/summary", token)
        ok = (s["inspections"]["url_scans_total"] == 0 and s["pages"]["pages_inspected"] == 0
              and set(s["ocr"]["heldout_benchmarks"]["by_engine"]) == {"tesseract_legacy", "tesseract_tuned", "custom_mlp", "hybrid"}
              and "own synthetic CAPTCHA generator only" in body and "99.33" in body)
        R.step("S2 evaluation dashboard: zero scans, 4 held-out engines, scope caveat on screen", t, ok, json.dumps(s["pages"]))

        # S3 inspect the owned demo site (UI) ----------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/inspector", wait_until="networkidle")
        await page.fill("input[type='text'], input[type='url'], input:not([type])", SITE)
        async with page.expect_response(lambda r: "/api/websites/inspect-url" in r.url, timeout=120000):
            await page.click("form button[type='submit']")  # synchronous crawl: the response arrives when it is done
        await page.wait_for_timeout(2500)
        await seen("04_inspector_result")
        scans = await api("/api/websites/scans?limit=5", token)
        sc = scans["scans"][0] if scans["scans"] else {}
        ok = scans["total"] == 1 and sc.get("status") == "completed"
        R.step("S3 inspect demo site via UI -> scan completed", t, ok, json.dumps({k: sc.get(k) for k in ("status", "pages_crawled", "contact_pages_found")}))
        scan_id = sc.get("id")

        # S3b safe failure: the guard refuses internal / non-allow-listed targets (UI message) ------------
        for bad, expect in (("http://169.254.169.254/latest/meta-data/", "metadata"), ("https://example.com", "allowlist")):
            t = time.perf_counter()
            await page.goto(f"{FRONTEND}/inspector", wait_until="networkidle")
            await page.fill("input[type='text'], input[type='url'], input:not([type])", bad)
            async with page.expect_response(lambda r: "/api/websites/inspect-url" in r.url, timeout=30000) as ri:
                await page.click("form button[type='submit']")
            status = (await ri.value).status
            await page.wait_for_timeout(800)
            txt = await page.inner_text("body")
            await seen("04b_policy_refusal_" + expect)
            R.step(f"S3b policy refusal for {bad}", t, status == 400 and "Security restriction" in txt, f"HTTP {status}")

        # S4 scan history + evidence ----------------------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/scans?scan_id={scan_id}", wait_until="networkidle")
        await page.wait_for_selector("text=View Evidence", timeout=20000)
        await seen("05_scan_pages")
        # open the evidence of the contact page (the one with the CAPTCHA)
        cards = page.locator("text=View Evidence")
        await cards.nth(min(1, await cards.count() - 1)).click()
        img = page.locator("img[alt='Page inspection screenshot']")
        await img.wait_for(state="visible", timeout=15000)
        nat = await img.evaluate("e => e.naturalWidth")
        await seen("06_evidence_screenshot")
        R.step("S4 pages listed + screenshot evidence renders", t, nat > 0 and await cards.count() >= 2, f"naturalWidth={nat}")

        # S5 CAPTCHA results ---------------------------------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/results", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        txt = (await page.inner_text("body")).lower()
        await seen("07_captcha_results")
        R.step("S5 CAPTCHA results show reCAPTCHA + human-review strategy", t, "recaptcha" in txt and "review" in txt)

        # S6 human review (decide a case) -----------------------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/reviews", wait_until="networkidle")
        await page.wait_for_selector("text=Review Now", timeout=15000)
        await seen("08_review_queue")
        await page.locator("text=Review Now").first.click()
        await page.fill("textarea", "Demo: production-style reCAPTCHA on the owned demo site; needs a person.")
        await seen("09_review_dialog")
        await page.click("button:has-text('Mark Manually Verified')")
        await page.wait_for_timeout(1500)
        rv = await api("/api/captcha/reviews?status=manually_verified", token)
        hist = rv["reviews"][0] if rv["reviews"] else {}
        R.step("S6 human review decision recorded with identity", t,
               rv["summary"]["manually_verified"] == 1 and hist.get("reviewed_by") == op_user, hist.get("reviewed_by"))

        # S7 OCR laboratory ----------------------------------------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/ocr", wait_until="networkidle")
        body = await page.inner_text("body")
        R.step("S7a OCR page states the synthetic-generator-only scope", t, "OWN synthetic CAPTCHA generator only" in body)
        t = time.perf_counter()
        await page.click("text=Run OCR Evaluation")
        await page.wait_for_timeout(3000)
        await seen("10_ocr_single")
        ev = await api("/api/stats/summary", token)
        R.step("S7b single OCR evaluation stored with true label", t, ev["ocr"]["evaluations"] >= 1, ev["ocr"]["evaluations"])

        async def bench(engine, label):
            tb = time.perf_counter()
            await page.select_option("select[aria-label='OCR engine']", engine)
            await page.select_option("select[aria-label='Dataset split']", "test")
            await page.locator("select").filter(has=page.locator("option[value='50']")).select_option("50")
            async with page.expect_response(lambda r: "/api/captcha/ocr-benchmark" in r.url and r.request.method == "POST", timeout=120000) as ri:
                await page.click("text=Run Benchmark")
            resp = await (await ri.value).json()
            await page.wait_for_timeout(800)
            await seen(f"11_ocr_benchmark_{label}")
            R.step(f"S7 benchmark {label}: 50 held-out-split samples", tb, resp["total_samples"] == 50,
                   f"exact={resp['exact_match_rate_percent']}% char={resp['mean_character_accuracy']}% latency={resp['mean_execution_time_ms']}ms")
            return resp

        h = await bench("hybrid", "hybrid")
        l = await bench("tesseract_legacy", "legacy")
        R.step("S7 hybrid clearly beats legacy on the same 50 samples", time.perf_counter(),
               h["exact_matches"] > l["exact_matches"], f"{h['exact_matches']}/50 vs {l['exact_matches']}/50")

        # S8 verification ----------------------------------------------------------------------------------------------
        await page.goto(f"{FRONTEND}/verification", wait_until="networkidle")
        sel = page.locator("form select")

        async def verify(provider, scenario, expect, label):
            tv = time.perf_counter()
            await sel.nth(0).select_option(provider)
            await page.wait_for_selector(f"option[value='{scenario}']", state="attached", timeout=5000)
            await sel.nth(1).select_option(scenario)
            async with page.expect_response(lambda r: "/verify-token" in r.url, timeout=30000):
                await page.click("text=Run verification")
            await page.wait_for_timeout(700)
            panel = await page.inner_text("[data-testid='verification-result']")
            await seen(f"12_verification_{label}")
            R.step(f"S8 verification: {label}", tv, all(e in panel for e in expect), panel.replace("\n", " ")[:160])

        await verify("google_recaptcha", "test:0", ["OFFICIAL TEST KEYS", "CONFIRMED BY PROVIDER", "Provider called: true"], "recaptcha_test_key")
        await verify("cloudflare_turnstile", "test:2", ["OFFICIAL TEST KEYS", "timeout-or-duplicate", "NOT VERIFIED"], "turnstile_already_spent")
        await verify("google_recaptcha", "sim:expired", ["SIMULATED", "NOT VERIFIED", "Provider called: false"], "simulated_expired")
        await verify("hcaptcha", "missing", ["LOCAL VALIDATION", "rejected_missing_token", "Provider called: false"], "missing_token")

        # S9 final dashboard + report --------------------------------------------------------------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/evaluation", wait_until="networkidle")
        await page.wait_for_selector("text=Verification outcomes by scenario", timeout=15000)
        await seen("13_evaluation_final")
        async with page.expect_download(timeout=20000) as dl:
            await page.click("button:has-text('Download evaluation report')")
        report = Path(await (await dl.value).path()).read_text(encoding="utf-8")
        R.scan("downloaded report", report)
        (OUT / "downloaded_report.md").write_text(report, encoding="utf-8")
        s = await api("/api/stats/summary", token)
        R.step("S9 dashboard + report reflect the demo run", t,
               s["inspections"]["url_scans_total"] == 1 and s["verification"]["attempts"] == 4
               and s["verification"]["simulated_attempts"] == 1 and "custom_mlp" in report and "Denominator" in report,
               json.dumps({"scans": s["inspections"]["url_scans_total"], "verif": s["verification"]["attempts"]}))

        # S9b Settings page is now safe to show: no local paths, only safe values ----------------------------------
        t = time.perf_counter()
        await page.goto(f"{FRONTEND}/settings", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        stxt = await page.inner_text("body")
        await seen("14_settings_page")
        s_api = await api("/api/websites/settings", token)
        api_text = json.dumps(s_api)
        no_paths = not (re.search(r"[A-Za-z]:", api_text) or "\\\\" in api_text or "AppData" in api_text
                        or "OneDrive" in api_text or "Users" in api_text)
        R.step("S9b Settings page + API expose no local paths (evidence/, tesseract only)", t,
               no_paths and s_api["evidence_dir"] == "evidence/" and s_api["tesseract_cmd"] == "tesseract"
               and "evidence/" in stxt, json.dumps({k: s_api[k] for k in ("evidence_dir", "tesseract_cmd", "reports_dir")}))

        # S10 logout ----------------------------------------------------------------------------------------------------------
        await page.click("button[title='Sign Out']")
        await page.wait_for_url(f"{FRONTEND}/login", timeout=15000)
        await browser.close()

    # The two deliberate policy refusals (scene 4) return HTTP 400 and the browser logs them; nothing else may.
    expected_400 = [e for e in R.http if e.startswith("400 ") and "/api/websites/inspect-url" in e]
    R.http = [e for e in R.http if e not in expected_400]
    R.console = [c for c in R.console if "status of 400" not in c] if len(expected_400) == 2 else R.console
    passed = sum(s["ok"] for s in R.steps)
    report = {"expected_policy_refusals_http_400": len(expected_400), "steps": R.steps, "total_seconds": round(sum(s["seconds"] for s in R.steps), 1),
              "leak_findings": R.leaks, "console_errors": R.console, "failed_requests": R.failed,
              "http_errors": R.http, "passed": passed, "total": len(R.steps)}
    (OUT / "rehearsal_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(R.steps)} steps ok; leak findings: {len(R.leaks)}; console errors: {len(R.console)}; "
          f"failed requests: {len(R.failed)}; HTTP>=400: {len(R.http)}; machine time {report['total_seconds']}s")
    for leak in R.leaks:
        print("LEAK:", leak["where"], leak["pattern"], leak["context"])
    return 0 if passed == len(R.steps) and not R.leaks and not R.console and not R.failed else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
