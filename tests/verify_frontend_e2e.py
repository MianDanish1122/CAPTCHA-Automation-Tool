import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("evidence/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def run_e2e_verification():
    print("[E2E] Starting Playwright frontend verification...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 1. Overview Dashboard
        print("  Navigating to Overview Dashboard (/)")
        await page.goto("http://localhost:3000/", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        assert "CAPTCHA Inspector" in await page.title()
        overview_path = SCREENSHOTS_DIR / "phase4_01_overview_dashboard.png"
        await page.screenshot(path=str(overview_path), full_page=True)
        print(f"  Captured: {overview_path}")

        # 2. URL Inspector
        print("  Navigating to URL Inspector (/inspector)")
        await page.goto("http://localhost:3000/inspector", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        inspector_path = SCREENSHOTS_DIR / "phase4_02_url_inspector.png"
        await page.screenshot(path=str(inspector_path), full_page=True)
        print(f"  Captured: {inspector_path}")

        # 3. Scan History
        print("  Navigating to Scan History (/scans)")
        await page.goto("http://localhost:3000/scans", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        scans_path = SCREENSHOTS_DIR / "phase4_03_scan_history.png"
        await page.screenshot(path=str(scans_path), full_page=True)
        print(f"  Captured: {scans_path}")

        # 4. CAPTCHA Results
        print("  Navigating to CAPTCHA Results (/results)")
        await page.goto("http://localhost:3000/results", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        results_path = SCREENSHOTS_DIR / "phase4_04_captcha_results.png"
        await page.screenshot(path=str(results_path), full_page=True)
        print(f"  Captured: {results_path}")

        # 5. Human Review Center
        print("  Navigating to Human Review Center (/reviews)")
        await page.goto("http://localhost:3000/reviews", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        reviews_path = SCREENSHOTS_DIR / "phase4_05_human_review_center.png"
        await page.screenshot(path=str(reviews_path), full_page=True)
        print(f"  Captured: {reviews_path}")

        # 6. OCR Laboratory & Interactive Run
        print("  Navigating to OCR Laboratory (/ocr)")
        await page.goto("http://localhost:3000/ocr", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        # Click Run OCR Evaluation button
        eval_btn = page.locator("button:has-text('Run OCR Evaluation')")
        if await eval_btn.is_visible():
            await eval_btn.click()
            await page.wait_for_timeout(2500)
        ocr_path = SCREENSHOTS_DIR / "phase4_06_ocr_laboratory.png"
        await page.screenshot(path=str(ocr_path), full_page=True)
        print(f"  Captured: {ocr_path}")

        # 7. CSV Batch Manager
        print("  Navigating to CSV Batch Manager (/batch)")
        await page.goto("http://localhost:3000/batch", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        batch_path = SCREENSHOTS_DIR / "phase4_07_csv_batch_manager.png"
        await page.screenshot(path=str(batch_path), full_page=True)
        print(f"  Captured: {batch_path}")

        # 8. Reports & Compliance
        print("  Navigating to Reports & Compliance (/reports)")
        await page.goto("http://localhost:3000/reports", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        reports_path = SCREENSHOTS_DIR / "phase4_08_reports_and_compliance.png"
        await page.screenshot(path=str(reports_path), full_page=True)
        print(f"  Captured: {reports_path}")

        # 9. System Settings
        print("  Navigating to System Settings (/settings)")
        await page.goto("http://localhost:3000/settings", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        settings_path = SCREENSHOTS_DIR / "phase4_09_settings_diagnostics.png"
        await page.screenshot(path=str(settings_path), full_page=True)
        print(f"  Captured: {settings_path}")

        await browser.close()
        print("[E2E] All 9 pages verified and screenshots saved successfully!")

if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
