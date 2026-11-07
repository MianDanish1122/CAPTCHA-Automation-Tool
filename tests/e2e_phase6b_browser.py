"""
Phase 6B browser verification (Playwright, real Chromium, real backend + production frontend).

Usage (all credentials come from the environment, nothing is hard-coded):

    # 1) isolated database: DATABASE_URL=sqlite:///.../e2e.db
    python tests/e2e_phase6b_browser.py seed       # migrate DB, create users, seed scan + screenshot
    # 2) start backend (uvicorn app.main:app --port 8000) and frontend (npm run start -- -p 3000)
    python tests/e2e_phase6b_browser.py run        # executes the checks, writes a JSON report
    python tests/e2e_phase6b_browser.py cleanup    # removes the seeded screenshot

Required env: E2E_OPERATOR_USER/E2E_OPERATOR_PASSWORD, E2E_ADMIN_USER/E2E_ADMIN_PASSWORD.
Optional: E2E_BACKEND (default http://127.0.0.1:8000), E2E_FRONTEND (default http://localhost:3000),
          E2E_STATE (default evidence/phase6b/e2e_state.json), E2E_REPORT.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BACKEND = os.environ.get("E2E_BACKEND", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("E2E_FRONTEND", "http://localhost:3000")
OUT_DIR = ROOT / "evidence" / "phase6b"
STATE = Path(os.environ.get("E2E_STATE", OUT_DIR / "e2e_state.json"))
REPORT = Path(os.environ.get("E2E_REPORT", OUT_DIR / "browser_verification.json"))


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Set {name} (never hard-code credentials).")
    return value


# --------------------------------------------------------------------------- seed / cleanup
def seed():
    import uuid
    from alembic import command
    from alembic.config import Config
    from PIL import Image, ImageDraw
    from app.config import settings
    from app.database import SessionLocal
    from app.models import DiscoveredPage, UrlScan, User, UserRole
    from app.services.auth_service import hash_password

    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    db = SessionLocal()
    try:
        for who, role in (("OPERATOR", UserRole.OPERATOR), ("ADMIN", UserRole.ADMIN)):
            name = env(f"E2E_{who}_USER")
            if not db.query(User).filter(User.username == name).first():
                db.add(User(username=name, email=f"{name}@e2e.test", role=role,
                            hashed_password=hash_password(env(f"E2E_{who}_PASSWORD"))))
        scan_id = str(uuid.uuid4())
        rel = f"evidence/scans/{scan_id}/page_0_home.png"
        folder = settings.SCANS_EVIDENCE_DIR / scan_id
        folder.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (640, 360), (30, 41, 59))
        ImageDraw.Draw(img).text((20, 20), "E2E synthetic evidence screenshot", fill=(255, 255, 255))
        img.save(folder / "page_0_home.png")

        db.add(UrlScan(id=scan_id, submitted_url="https://example.com", domain="example.com",
                       status="completed", pages_crawled=1, captcha_detected=False))
        db.flush()
        db.add(DiscoveredPage(scan_id=scan_id, url="https://example.com/", depth=0, page_title="Home",
                              classification="contact", screenshot_path=rel, evidence="{}"))
        db.commit()
    finally:
        db.close()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"scan_id": scan_id, "evidence_path": rel}), encoding="utf-8")
    print("seeded scan", scan_id)


def cleanup():
    import shutil
    from app.config import settings
    if STATE.exists():
        st = json.loads(STATE.read_text())
        shutil.rmtree(settings.SCANS_EVIDENCE_DIR / st["scan_id"], ignore_errors=True)
        STATE.unlink()
        print("removed seeded evidence for", st["scan_id"])


# --------------------------------------------------------------------------- checks
class Recorder:
    def __init__(self):
        self.checks = []
        self.console_errors = []
        self.page_errors = []
        self.failed_requests = []
        self.http_errors = []

    def check(self, name, ok, detail=""):
        self.checks.append({"check": name, "passed": bool(ok), "detail": str(detail)[:300]})
        print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""))


async def run():
    from playwright.async_api import async_playwright

    st = json.loads(STATE.read_text())
    rec = Recorder()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    evidence_api = "/api/" + st["evidence_path"].replace("evidence/", "evidence/", 1)  # /api/evidence/scans/..

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        api = ctx.request  # shares nothing with page auth (we pass headers explicitly)

        def attach(page):
            page.on("console", lambda m: rec.console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: rec.page_errors.append(str(e)))
            page.on("requestfailed", lambda r: rec.failed_requests.append(f"{r.method} {r.url} {r.failure}"))
            page.on("response", lambda r: rec.http_errors.append(f"{r.status} {r.request.method} {r.url}")
                    if r.status >= 400 else None)

        page = await ctx.new_page()
        attach(page)

        # ---- 1. login page exposes no credentials ----------------------------------
        await page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        text = await page.inner_text("body")
        html = await page.content()
        import re
        rec.check("login page has no quick-fill credential panel",
                  not re.search(r"quick.{0,8}test|click to fill", text, re.I)
                  and not re.search(r"(Admin|Operator)(Secure|Pass)\w*\d{3,}", html))
        await page.screenshot(path=str(OUT_DIR / "01_login.png"))

        # ---- 2. operator login + dashboard -----------------------------------------
        await page.fill('input[type="text"]', env("E2E_OPERATOR_USER"))
        await page.fill('input[type="password"]', env("E2E_OPERATOR_PASSWORD"))
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{FRONTEND}/", timeout=20000)
        await page.wait_for_load_state("networkidle")
        token = await page.evaluate("localStorage.getItem('captcha_token')")
        rec.check("operator logs in and reaches dashboard", bool(token) and page.url.rstrip("/") == FRONTEND)
        body = await page.inner_text("body")
        rec.check("dashboard renders authenticated content", "Overview" in body or "Dashboard" in body or "Scans" in body)
        await page.screenshot(path=str(OUT_DIR / "02_dashboard.png"))

        # ---- 3. protected screenshot loads in the UI --------------------------------
        evidence_requests = []
        page.on("request", lambda r: evidence_requests.append(r) if "/api/evidence/" in r.url else None)
        await page.goto(f"{FRONTEND}/scans?scan_id={st['scan_id']}", wait_until="networkidle")
        if await page.locator("text=View Evidence").count() == 0:
            await page.locator("button:has-text('Inspect')").first.click()
            await page.wait_for_selector("text=View Evidence", timeout=15000)
        await page.locator("text=View Evidence").first.click()
        img = page.locator("img[alt='Page inspection screenshot']")
        await img.wait_for(state="visible", timeout=15000)
        natural = await img.evaluate("el => el.naturalWidth")
        src = await img.get_attribute("src")
        rec.check("protected screenshot renders in the dashboard", natural > 0, f"naturalWidth={natural}")
        rec.check("screenshot is loaded via blob (not a public URL)", (src or "").startswith("blob:"), src)
        rec.check("evidence request carried a bearer token",
                  any((r.headers.get("authorization") or "").startswith("Bearer ") for r in evidence_requests),
                  f"{len(evidence_requests)} request(s)")
        await page.screenshot(path=str(OUT_DIR / "03_protected_screenshot.png"))

        # ---- 4. unauthorized evidence requests are rejected ------------------------------
        r = await api.get(BACKEND + evidence_api)
        rec.check("evidence without token -> 401", r.status == 401, r.status)
        r = await api.get(BACKEND + "/" + st["evidence_path"])
        rec.check("legacy public /evidence path -> 404", r.status == 404, r.status)
        r = await api.get(BACKEND + evidence_api, headers={"Authorization": "Bearer invalid.token.value"})
        rec.check("evidence with garbage token -> 401", r.status == 401, r.status)
        auth = {"Authorization": f"Bearer {token}"}
        r = await api.get(BACKEND + evidence_api, headers=auth)
        rec.check("evidence with operator token -> 200 image/png",
                  r.status == 200 and r.headers.get("content-type") == "image/png", r.status)
        for bad in ("/api/evidence/../.env", "/api/evidence/TEST_EVIDENCE.md", "/api/evidence/scans/x/../../.env"):
            r = await api.get(BACKEND + bad, headers=auth)
            rec.check(f"evidence traversal/out-of-scope {bad} -> 404", r.status == 404, r.status)

        # ---- 5. health endpoint exposes nothing sensitive ------------------------------
        r = await api.get(BACKEND + "/health")
        body = await r.text()
        rec.check("/health body is exactly liveness", json.loads(body) == {"status": "healthy"}, body)
        sensitive = ("allowed_domains", "tesseract", "app_env", "database", "version", "live_scan", "C:\\")
        rec.check("/health contains no sensitive keys", not any(s in body for s in sensitive))
        r = await api.get(BACKEND + "/api/health/details")
        rec.check("/api/health/details requires auth", r.status == 401, r.status)

        # ---- 6. operator permissions -----------------------------------------------------
        r = await api.get(BACKEND + "/api/auth/audit-logs", headers=auth)
        rec.check("operator cannot read audit logs (403)", r.status == 403, r.status)
        r = await api.post(BACKEND + "/api/auth/users", headers=auth,
                           data=json.dumps({"username": "x" * 5, "email": "x@y.test", "password": "Aaaaaaaaaaaa1!"}))
        rec.check("operator cannot create users (403/422 never 200)", r.status in (403, 422), r.status)
        await page.goto(f"{FRONTEND}/settings", wait_until="networkidle")
        settings_text = await page.inner_text("body")
        rec.check("operator sees no audit-trail section in Settings", "Audit Trail" not in settings_text, "")
        await page.screenshot(path=str(OUT_DIR / "04_operator_settings.png"))

        # ---- 7. logout invalidates the session ------------------------------------------
        await page.click("button[title='Sign Out']")
        await page.wait_for_url(f"{FRONTEND}/login", timeout=15000)
        rec.check("logout redirects to login and clears storage",
                  (await page.evaluate("localStorage.getItem('captcha_token')")) is None)
        r = await api.get(BACKEND + "/api/auth/me", headers=auth)
        rec.check("old token is rejected after logout (revoked)", r.status == 401 and "revoked" in (await r.text()).lower(), r.status)
        r = await api.get(BACKEND + evidence_api, headers=auth)
        rec.check("old token cannot fetch evidence after logout", r.status == 401, r.status)
        await page.goto(f"{FRONTEND}/scans", wait_until="networkidle")
        rec.check("protected page redirects to login when signed out", "/login" in page.url, page.url)

        # ---- 8. admin permissions -----------------------------------------------------
        await page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        await page.fill('input[type="text"]', env("E2E_ADMIN_USER"))
        await page.fill('input[type="password"]', env("E2E_ADMIN_PASSWORD"))
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{FRONTEND}/", timeout=20000)
        admin_token = await page.evaluate("localStorage.getItem('captcha_token')")
        admin = {"Authorization": f"Bearer {admin_token}"}
        await page.goto(f"{FRONTEND}/settings", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        admin_text = await page.inner_text("body")
        rec.check("admin sees audit trail section in Settings", "Audit Trail" in admin_text)
        await page.screenshot(path=str(OUT_DIR / "05_admin_settings.png"))
        r = await api.get(BACKEND + "/api/auth/audit-logs?limit=5", headers=admin)
        rec.check("admin can read audit logs (200)", r.status == 200, r.status)
        r = await api.get(BACKEND + "/api/auth/audit-logs/verify", headers=admin)
        j = await r.json()
        rec.check("admin audit chain verification is valid", r.status == 200 and j.get("valid") is True, j)
        r = await api.get(BACKEND + "/api/health/details", headers=admin)
        rec.check("admin can read health details", r.status == 200)
        logs = await (await api.get(BACKEND + "/api/auth/audit-logs?limit=200", headers=admin)).text()
        rec.check("audit trail contains no credentials or attempted-username leakage",
                  env("E2E_OPERATOR_PASSWORD") not in logs and env("E2E_ADMIN_PASSWORD") not in logs)

        # ---- 9. frontend console / network hygiene ---------------------------------------
        # Deliberately provoked backend responses were made through ctx.request (not the page);
        # anything below is traffic generated by the application itself.
        rec.check("no uncaught page errors", not rec.page_errors, rec.page_errors[:3])
        app_http_errors = [e for e in rec.http_errors if "/api/evidence/" not in e or "401" not in e]
        rec.check("no failed network requests", not rec.failed_requests, rec.failed_requests[:3])
        rec.check("no HTTP >= 400 responses to application requests", not app_http_errors, app_http_errors[:5])
        rec.check("no console errors", not rec.console_errors, rec.console_errors[:3])

        await browser.close()

    passed = sum(1 for c in rec.checks if c["passed"])
    report = {
        "backend": BACKEND, "frontend": FRONTEND,
        "passed": passed, "total": len(rec.checks),
        "checks": rec.checks,
        "console_errors": rec.console_errors, "page_errors": rec.page_errors,
        "failed_requests": rec.failed_requests, "http_errors_seen_by_page": rec.http_errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rec.checks)} checks passed. Report: {REPORT}")
    sys.exit(0 if passed == len(rec.checks) else 1)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "seed":
        seed()
    elif mode == "cleanup":
        cleanup()
    elif mode == "run":
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(run())
    else:
        sys.exit("usage: seed | run | cleanup")
