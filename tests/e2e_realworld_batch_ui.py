"""
Browser E2E (real Chromium, real backend, isolated DB) for the real-world QA batch workflow:
CSV with the employer's column layout -> validation summary (columns preserved, warnings) -> batch scan using the
shared engine on local fixtures -> results table -> expected-vs-detected card -> authenticated CSV/Markdown downloads.

    python tests/e2e_realworld_batch_ui.py seed   # migrate (alembic head) + create operator
    python tests/e2e_realworld_batch_ui.py run
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FRONTEND, BACKEND = "http://localhost:3000", "http://127.0.0.1:8000"
OUT = (Path(os.environ["E2E_OUT_DIR"]) / "batch_ui") if os.environ.get("E2E_OUT_DIR") else ROOT / "evidence" / "final_qa" / "batch_ui"  # E2E_OUT_DIR keeps tracked evidence untouched

CSV = (
    "Company,Website,City,State,Category,Platform,Captcha,Contact Page,Notes\n"
    "Plain Shop,fixture://normal_contact_form.html,Austin,TX,Home,Shopify,none,,keep-this-note\n"
    "RC Shop,fixture://google_recaptcha.html,Reno,NV,Home,BigCommerce,reCAPTCHA,,\n"
    "Wrong Shop,fixture://hcaptcha.html,Ames,IA,Food,WooCommerce,reCAPTCHA,,\n"
    "Turnstile Shop,fixture://cloudflare_turnstile.html,Troy,NY,Food,WooCommerce,some novel thing,,\n"
    "Blocked Shop,fixture://unknown_challenge.html,Mesa,AZ,Toys,Shopify,hCaptcha,,\n"
    "=Evil(),fixture://normal_contact_form.html,Tulsa,OK,Toys,Shopify,none,,\n"
    ",https://missing-name.example,X,X,X,X,none,,\n"
)


def env(k):
    return os.environ[k]


def seed():
    from alembic import command
    from alembic.config import Config
    from app.database import SessionLocal
    from app.models import User, UserRole
    from app.services.auth_service import hash_password
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
    print("seeded")


async def run() -> int:
    from playwright.async_api import async_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    checks, console = [], []

    def check(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
        print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""), flush=True)

    csv_path = Path(tempfile.mkdtemp()) / "employer_layout.csv"
    csv_path.write_text(CSV, encoding="utf-8")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
        page = await ctx.new_page()
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)

        await page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        await page.fill('input[type="text"]', env("E2E_OPERATOR_USER"))
        await page.fill('input[type="password"]', env("E2E_OPERATOR_PASSWORD"))
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{FRONTEND}/", timeout=20000)
        await page.wait_for_load_state("networkidle")  # let the post-login page settle before the next hard navigation

        await page.goto(f"{FRONTEND}/batch", wait_until="networkidle")
        await page.set_input_files("#csvFileInput", str(csv_path))
        await page.check("input[type=checkbox]")                    # auto-start the scan
        await page.click("button:has-text('Import & Validate CSV')")
        await page.wait_for_selector("text=CSV Validation Summary", timeout=20000)

        cols = await page.locator("[data-testid=preserved-columns]").inner_text()
        check("all 9 CSV columns reported as preserved", all(c in cols for c in
              ["Company", "Website", "City", "State", "Category", "Platform", "Captcha", "Contact Page", "Notes"]), cols)
        check("unmapped column 'Notes' reported as stored", "Notes" in cols and "stored but not used" in cols, cols)
        body = await page.inner_text("body")
        check("invalid row (missing name) listed with its row number", "VALIDATION ERRORS (1)" in body.upper() and "ROW #" in body.upper())
        check("unrecognised Captcha value produces a warning", "not recognised" in body)
        await page.screenshot(path=str(OUT / "01_validation_summary.png"))

        await page.wait_for_selector("[data-testid=evaluation-card]", timeout=120000)
        await page.wait_for_selector("[data-testid=batch-results-table]", timeout=30000)
        rows = await page.locator("[data-testid=batch-results-table] tbody tr").count()
        check("6 valid rows scanned and listed", rows == 6, rows)
        counts = {k: int(await page.locator(f"[data-testid=eval-count-{k}]").inner_text())
                  for k in ["match", "mismatch", "not_detected", "not_accessible", "not_verified"]}
        check("evaluation categories as expected (3 match, 1 mismatch, 1 not accessible, 1 not verified)",
              counts == {"match": 3, "mismatch": 1, "not_detected": 0, "not_accessible": 1, "not_verified": 1}, counts)
        note = await page.locator("[data-testid=eval-note]").inner_text()
        check("agreement computed over eligible records only, with sample size stated",
              "75" in note and "4 eligible" in note and "too small" in note and "excluded" in note, note)
        table = await page.locator("[data-testid=evaluation-table]").inner_text()
        check("evaluation table has the requested columns",
              all(h in table.upper() for h in ["WEBSITE", "EXPECTED", "DETECTED", "CONTACT PAGE", "WIDGET LOADED", "RESULT"]))
        check("formula-looking company name is shown as text, not executed", "=Evil()" in await page.inner_text("body"))
        await page.screenshot(path=str(OUT / "02_results_and_evaluation.png"), full_page=True)

        # details modal
        await page.locator("text=Details").first.click()
        await page.wait_for_selector("text=Batch Result:", timeout=10000)
        check("details modal opens with robots/widget/result summary", "Robots:" in await page.inner_text("body"))
        await page.screenshot(path=str(OUT / "03_details_modal.png"))
        close = page.get_by_role("button", name="Close", exact=True)
        if await close.count():
            await close.first.click()
        else:
            await page.keyboard.press("Escape")
        await page.wait_for_selector("text=Batch Result:", state="detached", timeout=5000)

        # authenticated downloads (plain <a href> could not send the bearer token)
        for label, suffix, needle in (("CSV", ".csv", "Website,Expected,Detected"), ("Markdown", ".md", "Expected vs detected")):
            async with page.expect_download(timeout=20000) as dl:
                await page.get_by_role("button", name=label, exact=True).click()
            d = await dl.value
            path = await d.path()
            text = Path(path).read_text(encoding="utf-8-sig")
            check(f"evaluation {label} downloads with the session token", d.suggested_filename.endswith(suffix) and needle in text,
                  d.suggested_filename)
            if suffix == ".csv":
                check("downloaded evaluation CSV has no live formula cells",
                      not any(l.startswith(("=", "+", "-", "@")) for l in text.splitlines()[1:]))
        async with page.expect_download(timeout=20000) as dl:
            await page.locator("button:has-text('Download CSV Audit Report')").click()
        d = await dl.value
        text = Path(await d.path()).read_text(encoding="utf-8-sig")
        check("batch audit report downloads (authenticated) with new columns",
              "Company Name" in text and "Result Category" in text and "'=Evil()" in text, d.suggested_filename)

        await page.goto(f"{FRONTEND}/reports", wait_until="networkidle")
        async with page.expect_download(timeout=20000) as dl:
            await page.locator("button:has-text('Export CSV')").first.click()
        d = await dl.value
        check("Reports page 'Export CSV' downloads a file", d.suggested_filename.endswith(".csv"))

        check("no browser console errors", not console, console[:3])
        await browser.close()

    (OUT / "results.json").write_text(json.dumps({"checks": checks, "console_errors": console}, indent=2), encoding="utf-8")
    ok = sum(c["passed"] for c in checks)
    print(f"{ok}/{len(checks)} checks passed")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    if sys.argv[1:] == ["seed"]:
        seed()
    else:
        sys.exit(asyncio.run(run()))
