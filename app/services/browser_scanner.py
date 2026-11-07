import asyncio
import re
import time
from urllib.parse import urljoin, urlparse
from typing import Optional, Any
from playwright.async_api import async_playwright, Browser, Playwright

from app.config import settings
from app.services.security_guard import SecurityGuard
from app.services.network_guard import NetworkGuard, new_guarded_context

# Reusable browser singleton reference
_shared_playwright: Optional[Playwright] = None
_shared_browser: Optional[Browser] = None
_shared_loop = None
_lock: Optional[asyncio.Lock] = None


def _get_loop_lock(current_loop) -> asyncio.Lock:
    global _lock, _shared_loop
    if _lock is None or _shared_loop != current_loop:
        _lock = asyncio.Lock()
    return _lock


async def get_shared_browser() -> Browser:
    """
    Retrieve or initialize a shared Playwright Chromium browser.
    Thread-safe and concurrency-safe across coroutines and event loops.
    """
    global _shared_playwright, _shared_browser, _shared_loop
    current_loop = asyncio.get_running_loop()
    lock = _get_loop_lock(current_loop)

    async with lock:
        if (
            _shared_browser is None
            or not _shared_browser.is_connected()
            or _shared_loop != current_loop
        ):
            if _shared_browser:
                try:
                    await _shared_browser.close()
                except Exception:
                    pass
            if _shared_playwright:
                try:
                    await _shared_playwright.stop()
                except Exception:
                    pass

            _shared_loop = current_loop
            _shared_playwright = await async_playwright().start()
            _shared_browser = await _shared_playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        return _shared_browser


async def close_shared_browser() -> None:
    """Safely shut down the shared browser instance."""
    global _shared_playwright, _shared_browser, _shared_loop, _lock
    if _shared_browser:
        try:
            await _shared_browser.close()
        except Exception:
            pass
        _shared_browser = None
    if _shared_playwright:
        try:
            await _shared_playwright.stop()
        except Exception:
            pass
        _shared_playwright = None
    _shared_loop = None
    _lock = None


# Known provider script / domain patterns
PROVIDER_PATTERNS = {
    "google_recaptcha": [
        "google.com/recaptcha",
        "gstatic.com/recaptcha",
        "recaptcha.net/recaptcha",
    ],
    "hcaptcha": [
        "hcaptcha.com",
        "js.hcaptcha.com",
    ],
    "cloudflare_turnstile": [
        "challenges.cloudflare.com/turnstile",
    ],
}

# Signatures for anti-bot interstitial challenge screens
UNKNOWN_CHALLENGE_PATTERNS = [
    "just a moment...",
    "checking if the site connection is secure",
    "verifying you are human",
    "cf-challenge-running",
    "challenge-stage",
    "datadome",
    "perimeterx",
    "px-captcha",
    "aws-waf-captcha",
    "attention required! | cloudflare",
]

CONTACT_PAGE_KEYWORDS = [
    "contact",
    "contact-us",
    "contactus",
    "get-in-touch",
    "reach-us",
    "support",
    "about/contact",
]


def detect_captcha_in_html(page_html: str, page_title: str = "") -> dict[str, Any]:
    """
    Examine DOM HTML content and title to classify CAPTCHA presence,
    distinguishing active widgets, passive scripts, and unknown challenge pages.
    """
    html_lower = page_html.lower()
    title_lower = page_title.lower()

    # 1. Check for Unknown / Anti-bot Interstitials
    has_unknown_challenge = any(
        pattern in html_lower or pattern in title_lower
        for pattern in UNKNOWN_CHALLENGE_PATTERNS
    )

    detected_providers = []
    is_active_widget = False
    is_invisible = False

    # 2. Check for Google reCAPTCHA
    if any(p in html_lower for p in PROVIDER_PATTERNS["google_recaptcha"]):
        detected_providers.append("google_recaptcha")
        if 'class="g-recaptcha"' in html_lower or "class='g-recaptcha'" in html_lower or "g-recaptcha" in html_lower:
            is_active_widget = True
        if 'data-size="invisible"' in html_lower or "data-size='invisible'" in html_lower or "grecaptcha.execute" in html_lower:
            is_invisible = True

    # 3. Check for hCaptcha
    if any(p in html_lower for p in PROVIDER_PATTERNS["hcaptcha"]):
        if "hcaptcha" not in detected_providers:
            detected_providers.append("hcaptcha")
        if 'class="h-captcha"' in html_lower or "class='h-captcha'" in html_lower or "h-captcha" in html_lower:
            is_active_widget = True

    # 4. Check for Cloudflare Turnstile
    if any(p in html_lower for p in PROVIDER_PATTERNS["cloudflare_turnstile"]):
        if "cloudflare_turnstile" not in detected_providers:
            detected_providers.append("cloudflare_turnstile")
        if 'cf-turnstile' in html_lower:
            is_active_widget = True

    # 5. Check for Contact Form indicators
    has_contact_form = False
    if "<form" in html_lower:
        has_input_elements = any(tag in html_lower for tag in ["<input", "<textarea", "<button", "<select"])
        contact_semantic_indicators = [
            "email", "message", "subject", "comments", "textarea", "name=", "inquiry",
            "feedback", "support", "contact", "reach", "send", "submit"
        ]
        has_semantic_markers = any(ind in html_lower for ind in contact_semantic_indicators)
        if has_input_elements or has_semantic_markers:
            has_contact_form = True

    # Determine status & classification
    if has_unknown_challenge:
        status = "unsupported_challenge"
        human_review = True
        method = "anti_bot_interstitial_detection"
        if not detected_providers:
            detected_providers.append("unknown_anti_bot_challenge")
    elif detected_providers:
        status = "captcha_detected"
        human_review = True  # Third-party CAPTCHA challenge mandates human review
        method = "dom_widget_and_script_pattern" if is_active_widget else "provider_script_marker"
    else:
        status = "no_known_captcha_detected"
        human_review = False
        method = "form_and_dom_scan"

    return {
        "status": status,
        "detected_providers": detected_providers,
        "is_active_challenge": is_active_widget,
        "is_invisible": is_invisible,
        "has_contact_form": has_contact_form,
        "human_review_required": human_review,
        "detection_method": method,
    }


async def inspect_local_demo(html: str) -> dict:
    """
    Inspect a locally supplied HTML demo page.
    Compatible with existing tests and endpoints.
    """
    start_time = time.perf_counter()
    # Supplied HTML is untrusted: its scripts/subresources must never reach the network
    # (otherwise a demo page could probe internal services). All egress is blocked.
    guard = NetworkGuard(block_all_network=True, label="inspect-demo")
    try:
        browser = await get_shared_browser()
        context = await new_guarded_context(browser, guard)
    except Exception as launch_err:  # browser could not be started: report, do not crash the request
        await guard.close()
        return {
            "success": False,
            "status": "inspection_failed",
            "error": f"Browser unavailable: {type(launch_err).__name__}",
            "detected_providers": [],
            "inspection_duration_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }

    try:
        page = await context.new_page()
        # Set HTML directly without external navigation
        await page.set_content(html, wait_until="domcontentloaded")

        page_title = await page.title()
        page_html = await page.content()

        detection = detect_captcha_in_html(page_html, page_title)
        duration_ms = (time.perf_counter() - start_time) * 1000

        return {
            "success": True,
            "status": detection["status"],
            "detected_providers": detection["detected_providers"],
            "page_title": page_title,
            "is_active_challenge": detection["is_active_challenge"],
            "human_review_required": detection["human_review_required"],
            "contact_form_found": detection["has_contact_form"],
            "detection_method": detection["detection_method"],
            "inspection_duration_ms": round(duration_ms, 2),
        }

    except Exception as error:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return {
            "success": False,
            "status": "inspection_failed",
            "error": str(error),
            "detected_providers": [],
            "inspection_duration_ms": round(duration_ms, 2),
        }

    finally:
        await context.close()
        await guard.close()


async def inspect_website(
    url: str,
    check_security: bool = True,
    allow_loopback: bool = False,
) -> dict[str, Any]:
    """
    Safely inspect a website URL using Playwright.
    Enforces SSRF protections, navigation timeouts, and contact discovery.
    """
    start_time = time.perf_counter()

    # 1. Security & Authorization Pre-Check
    if check_security:
        allowed, reason = SecurityGuard.validate_target_url(
            url, enforce_live_scan=True, allow_loopback=allow_loopback
        )
        if not allowed:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return {
                "success": False,
                "scan_status": "failed",
                "error": f"Security restriction: {reason}",
                "detected_providers": [],
                "page_title": None,
                "contact_page_url": None,
                "contact_form_found": False,
                "captcha_detected": False,
                "captcha_provider": None,
                "detection_method": "security_guard_precheck",
                "is_active_challenge": False,
                "human_review_required": False,
                "inspection_duration_ms": round(duration_ms, 2),
            }

    # Every navigation, redirect hop and subresource goes through the egress guard
    # (SSRF validation + DNS-pinned fetch). TLS certificate validation stays enabled.
    guard = NetworkGuard(allow_loopback=allow_loopback, label="batch-scan")
    try:
        browser = await get_shared_browser()
        context = await new_guarded_context(
            browser,
            guard,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        )
    except Exception as launch_err:  # e.g. Chromium missing / crashed
        await guard.close()
        return {
            "success": False,
            "scan_status": "failed",
            "error": f"Browser unavailable: {type(launch_err).__name__}",
            "detected_providers": [],
            "page_title": None,
            "contact_page_url": None,
            "contact_form_found": False,
            "captcha_detected": False,
            "captcha_provider": None,
            "detection_method": "browser_unavailable",
            "is_active_challenge": False,
            "human_review_required": False,
            "inspection_duration_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }

    try:
        page = await context.new_page()
        page.set_default_navigation_timeout(settings.REQUEST_TIMEOUT_MS)

        try:
            response = await page.goto(url, wait_until="domcontentloaded")
            http_status = response.status if response else 200
        except Exception as nav_err:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return {
                "success": False,
                "scan_status": "failed",
                "error": f"Navigation error: {str(nav_err)}",
                "detected_providers": [],
                "page_title": None,
                "contact_page_url": None,
                "contact_form_found": False,
                "captcha_detected": False,
                "captcha_provider": None,
                "detection_method": "navigation_failure",
                "network_guard": guard.summary(),
                "is_active_challenge": False,
                "human_review_required": False,
                "inspection_duration_ms": round(duration_ms, 2),
            }

        page_title = await page.title()
        landing_html = await page.content()

        detection = detect_captcha_in_html(landing_html, page_title)
        contact_page_url = None

        if not detection["has_contact_form"] and detection["status"] != "unsupported_challenge":
            try:
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "elements => elements.map(el => ({href: el.getAttribute('href'), text: el.innerText.trim()}))"
                )
                landing_url = guard.effective_url(page.url)
                base_domain = urlparse(landing_url).netloc.lower()

                for link in links:
                    href = link.get("href") or ""
                    text = (link.get("text") or "").lower()

                    is_contact_link = any(
                        kw in href.lower() or kw in text
                        for kw in CONTACT_PAGE_KEYWORDS
                    )

                    if is_contact_link:
                        resolved_url = urljoin(landing_url, href)
                        resolved_domain = urlparse(resolved_url).netloc.lower()

                        if resolved_domain == base_domain:
                            contact_page_url = resolved_url
                            try:
                                await page.goto(contact_page_url, wait_until="domcontentloaded")
                                contact_html = await page.content()
                                contact_title = await page.title()
                                contact_detection = detect_captcha_in_html(contact_html, contact_title)

                                if contact_detection["detected_providers"] or contact_detection["has_contact_form"]:
                                    detection = contact_detection
                                    page_title = contact_title
                            except Exception:
                                pass
                            break
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start_time) * 1000
        captcha_detected = len(detection["detected_providers"]) > 0 or detection["status"] == "unsupported_challenge"
        provider_name = ", ".join(detection["detected_providers"]) if detection["detected_providers"] else None

        return {
            "success": True,
            "scan_status": detection["status"],
            "page_title": page_title,
            "contact_page_url": contact_page_url,
            "contact_form_found": detection["has_contact_form"],
            "captcha_detected": captcha_detected,
            "captcha_provider": provider_name,
            "detection_method": detection["detection_method"],
            "is_active_challenge": detection["is_active_challenge"],
            "human_review_required": detection["human_review_required"],
            "error_details": None,
            "network_guard": guard.summary(),
            "inspection_duration_ms": round(duration_ms, 2),
        }

    except Exception as general_err:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return {
            "success": False,
            "scan_status": "failed",
            "page_title": None,
            "contact_page_url": None,
            "contact_form_found": False,
            "captcha_detected": False,
            "captcha_provider": None,
            "detection_method": "unhandled_exception",
            "is_active_challenge": False,
            "human_review_required": False,
            "error_details": str(general_err),
            "inspection_duration_ms": round(duration_ms, 2),
        }

    finally:
        await context.close()
        await guard.close()
