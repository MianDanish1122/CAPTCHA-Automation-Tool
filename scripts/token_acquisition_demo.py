"""
Official TEST-KEY token acquisition + server-side validation, on a page WE own.

A local page embeds each provider's published TEST site key. The provider's widget runs in the browser
and issues a response token (test keys auto-pass by design: no puzzle exists, nothing is bypassed).
The token is then verified server-side through `verify_token` -> the provider's real `siteverify`
endpoint with the matching published TEST secret. Tokens are NOT printed or stored (only length).

    python -m scripts.token_acquisition_demo

This demonstrates the integration with the providers' official test infrastructure; it is not (and does
not claim to be) verification of a production challenge. Requires internet access to the providers.
"""
import asyncio
import http.server
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.token_verifier import PROVIDERS, verify_token  # noqa: E402

OUT = ROOT / "evidence" / "phase7" / "verification"

# One isolated page PER provider. A shared page made the providers' globals collide: hCaptcha's api.js ships a
# reCAPTCHA-compatibility layer (recaptchacompat=on by default), so `hcaptcha.render` on the shared page produced a
# *Google reCAPTCHA* iframe and the hCaptcha checkbox never existed (root cause of the earlier 20 s timeout).
PAGES = {
    "google_recaptcha": '<script src="https://www.google.com/recaptcha/api.js?render=explicit" async defer></script>'
                        '<div id="rc"></div>',
    "hcaptcha": '<script src="https://js.hcaptcha.com/1/api.js?render=explicit&recaptchacompat=off" async defer></script>'
                '<div id="hc"></div>',
    "cloudflare_turnstile": '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" async defer></script>'
                            '<div id="ts"></div>',
}


def page_for(provider: str) -> str:
    return ("<!doctype html><html><head><title>Owned test page</title></head><body>"
            "<h1>Owned test page (official TEST site key)</h1>" + PAGES[provider] + "</body></html>")


TEST_SITEKEYS = {
    "google_recaptcha": "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
    "hcaptcha": "10000000-ffff-ffff-ffff-000000000001",
    "cloudflare_turnstile": "1x00000000000000000000AA",
}


class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        provider = (parse_qs(urlparse(self.path).query).get("p") or ["google_recaptcha"])[0]
        data = page_for(provider if provider in PAGES else "google_recaptcha").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


async def acquire(page, provider: str):
    """Render the provider's TEST widget on our page and return the token it issues (or None)."""
    key = TEST_SITEKEYS[provider]
    if provider == "google_recaptcha":
        await page.wait_for_function("!!(window.grecaptcha && window.grecaptcha.render)", timeout=20000)
        await page.evaluate(f"window.__rc = grecaptcha.render('rc', {{sitekey: '{key}'}})")
        frame = page.frame_locator("#rc iframe[title='reCAPTCHA']")
        await frame.locator("#recaptcha-anchor").click(timeout=20000)
        await page.wait_for_function("grecaptcha.getResponse(window.__rc).length > 0", timeout=30000)
        return await page.evaluate("grecaptcha.getResponse(window.__rc)")
    if provider == "hcaptcha":
        await page.wait_for_function("!!(window.hcaptcha && window.hcaptcha.render)", timeout=20000)
        await page.evaluate(f"window.__hc = hcaptcha.render('hc', {{sitekey: '{key}'}})")
        frame = page.frame_locator("#hc iframe[title*='checkbox']")
        await frame.locator("#checkbox").click(timeout=20000)
        await page.wait_for_function("hcaptcha.getResponse(window.__hc).length > 0", timeout=30000)
        return await page.evaluate("hcaptcha.getResponse(window.__hc)")
    if provider == "cloudflare_turnstile":
        await page.wait_for_function("!!(window.turnstile && window.turnstile.render)", timeout=20000)
        await page.evaluate(f"window.__ts = turnstile.render(document.getElementById('ts'), {{sitekey: '{key}'}})")
        await page.wait_for_function("!!window.__ts && !!turnstile.getResponse(window.__ts)", timeout=30000)
        return await page.evaluate("turnstile.getResponse(window.__ts)")
    raise ValueError(provider)


async def main() -> int:
    from playwright.async_api import async_playwright
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for provider in PROVIDERS:
            page = await (await browser.new_context()).new_page()
            entry = {"provider": provider, "test_site_key_used": TEST_SITEKEYS[provider]}
            try:
                await page.goto(f"{url}?p={provider}", wait_until="load")
                token = await acquire(page, provider)
                entry["token_acquired_from_widget"] = bool(token)
                entry["token_length"] = len(token or "")
                if token:
                    verdict = await verify_token(provider, token, token_source="widget_test_key")
                    entry["verification"] = {k: verdict[k] for k in (
                        "verification_mode", "outcome", "success", "provider_called", "provider_verified",
                        "http_status", "error_codes", "hostname", "token_source")}
            except Exception as exc:
                entry["token_acquired_from_widget"] = False
                entry["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            results.append(entry)
            print(json.dumps(entry))
            await page.context.close()
        await browser.close()
    srv.shutdown()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "token_acquisition.json").write_text(json.dumps(
        {"note": "official TEST keys on an owned page; tokens not stored", "results": results}, indent=2), encoding="utf-8")
    ok = all(r.get("verification", {}).get("provider_verified") for r in results)
    print("ALL VERIFIED BY PROVIDER (test keys):", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    sys.exit(asyncio.run(main()))
