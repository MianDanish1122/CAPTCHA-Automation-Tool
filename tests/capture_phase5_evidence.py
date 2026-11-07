import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

EVIDENCE_DIR = Path("evidence/phase5")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

async def wait_for_service(url: str, timeout: float = 30.0, name: str = "Service"):
    start = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start < timeout:
            try:
                res = await client.get(url, timeout=2.0)
                if res.status_code in (200, 304, 307):
                    print(f"[OK] {name} is up at {url} (HTTP {res.status_code})")
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    raise TimeoutError(f"Timed out waiting for {name} at {url}")

def kill_process(proc):
    if not proc:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
    except Exception:
        pass

async def main():
    print("=" * 70)
    print("   PHASE 5 EVIDENCE CAPTURE — SECURITY & AUTHENTICATION")
    print("=" * 70)

    # Ensure environment variables for server
    server_env = os.environ.copy()
    server_env["APP_ENV"] = "development"
    server_env["ALLOW_DEV_LOOPBACK"] = "true"
    server_env["ENABLE_LIVE_SCAN"] = "false"

    backend_proc = None
    frontend_proc = None

    try:
        # 1. Start FastAPI Backend
        print("[1/4] Launching FastAPI backend...")
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            env=server_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2. Start Next.js Frontend
        print("[2/4] Launching Next.js frontend (production build)...")
        frontend_proc = subprocess.Popen(
            "npm run start",
            cwd="frontend",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for both services
        await wait_for_service("http://127.0.0.1:8000/health", timeout=20.0, name="FastAPI Backend")
        await wait_for_service("http://localhost:3000/login", timeout=30.0, name="Next.js Frontend")

        # 3. Launch Playwright
        print("[3/4] Launching Playwright browser automation...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            page.on("console", lambda msg: print(f"  [BROWSER CONSOLE] {msg.type}: {msg.text}"))
            page.on("pageerror", lambda err: print(f"  [PAGE ERROR] {err}"))

            # --- SCREENSHOT 1: Login Screen ---
            print("Capturing Screenshot 1: Phase 5 Login Screen...")
            await page.goto("http://localhost:3000/login", wait_until="networkidle")
            await page.wait_for_timeout(1000)
            p1 = EVIDENCE_DIR / "phase5_01_login_screen.png"
            await page.screenshot(path=str(p1), full_page=True)
            print(f"[OK] Saved {p1}")

            # --- Authenticate as Operator ---
            print("Signing in as Operator...")
            await page.fill('input[type="text"]', "operator")
            await page.fill('input[type="password"]', "OperatorPass123!")
            await page.click('button[type="submit"]')
            
            # Wait for header and overview dashboard
            await page.wait_for_selector("header", timeout=15000)
            await page.wait_for_timeout(2000)

            # --- SCREENSHOT 2: Authenticated Overview ---
            print("Capturing Screenshot 2: Authenticated System Overview...")
            p2 = EVIDENCE_DIR / "phase5_02_authenticated_overview.png"
            await page.screenshot(path=str(p2), full_page=True)
            print(f"[OK] Saved {p2}")

            # --- SCREENSHOT 3: Operator Human Review Center ---
            print("Capturing Screenshot 3: Operator Human Review Queue...")
            await page.goto("http://localhost:3000/reviews", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            p3 = EVIDENCE_DIR / "phase5_03_operator_human_review.png"
            await page.screenshot(path=str(p3), full_page=True)
            print(f"[OK] Saved {p3}")

            # --- Switch to Admin Context ---
            print("Signing out and authenticating as Administrator...")
            logout_btn = page.locator('button[title="Sign Out"]')
            if await logout_btn.is_visible():
                await logout_btn.click()
                await page.wait_for_timeout(1500)
            else:
                await page.goto("http://localhost:3000/login", wait_until="networkidle")

            # Fill Admin Credentials
            await page.wait_for_selector('input[type="text"]', timeout=15000)
            await page.fill('input[type="text"]', "admin")
            await page.fill('input[type="password"]', "AdminSecure2026!")
            await page.click('button[type="submit"]')
            
            await page.wait_for_selector("header", timeout=15000)
            await page.wait_for_timeout(2000)

            # --- SCREENSHOT 4: Admin Audit Logs in Settings ---
            print("Capturing Screenshot 4: Administrative Audit Trail & System Security...")
            await page.goto("http://localhost:3000/settings", wait_until="networkidle")
            await page.wait_for_timeout(3000)
            p4 = EVIDENCE_DIR / "phase5_04_admin_audit_logs.png"
            await page.screenshot(path=str(p4), full_page=True)
            print(f"[OK] Saved {p4}")

            await browser.close()

        print("\n" + "=" * 70)
        print("   ALL 4 PHASE 5 SCREENSHOTS CAPTURED SUCCESSFULLY")
        print("=" * 70)

    finally:
        print("[4/4] Cleaning up server processes...")
        kill_process(backend_proc)
        kill_process(frontend_proc)
        print("[DONE] Server processes terminated.")

if __name__ == "__main__":
    asyncio.run(main())
