import asyncio
import re
import time
from urllib.parse import urljoin, urlparse
from typing import Optional, Any
from playwright.async_api import async_playwright, Browser, Playwright

from app.config import settings
from app.services.security_guard import SecurityGuard, same_site
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


def _failure(start_time: float, error: str, method: str, **extra) -> dict[str, Any]:
    base = {
        "success": False,
        "scan_status": "failed",
        "error": error,
        "error_details": error,
        "detected_providers": [],
        "page_title": None,
        "contact_page_url": None,
        "contact_form_found": False,
        "captcha_detected": False,
        "captcha_provider": None,
        "detection_method": method,
        "is_active_challenge": False,
        "human_review_required": False,
        "inspection_duration_ms": round((time.perf_counter() - start_time) * 1000, 2),
    }
    base.update(extra)
    return base


async def inspect_website(
    url: str,
    check_security: bool = True,
    allow_loopback: bool = False,
    *,
    expected_contact_page: Optional[str] = None,
    evidence_dir=None,
    evidence_name: str = "site",
    respect_robots: bool = False,
    probe_forms: bool = False,
    user_agent: Optional[str] = None,
) -> dict[str, Any]:
    """
    Safely inspect a website URL using Playwright (shared engine for the batch workflow).

    Enforces SSRF protections, navigation timeouts and contact discovery. Optional extras used by the batch pipeline:
      expected_contact_page  visit the CSV's Contact Page directly; fall back to landing-page discovery if it fails
      respect_robots         check robots.txt/access restrictions FIRST and stop (no workaround) if restricted
      evidence_dir           save a screenshot of the inspected page there (relative path returned)
      user_agent             override the browser UA (the real-site validation sends the honest crawler UA)
      probe_forms            record the form field inventory and fill it with synthetic data in a no-transmission
                             lockdown (never submits, never touches a CAPTCHA)
    """
    from app.services.captcha_detection import detect_on_page  # lazy: avoids a circular import
    from app.services.robots_check import fetch_and_evaluate

    start_time = time.perf_counter()

    # 1. Security & Authorization Pre-Check
    if check_security:
        for candidate in [url] + ([expected_contact_page] if expected_contact_page else []):
            allowed, reason = SecurityGuard.validate_target_url(
                candidate, enforce_live_scan=True, allow_loopback=allow_loopback
            )
            if not allowed:
                return _failure(start_time, f"Security restriction: {reason}", "security_guard_precheck")

    # Every navigation, redirect hop and subresource goes through the egress guard
    # (SSRF validation + DNS-pinned fetch). TLS certificate validation stays enabled.
    # Provider widget hosts are allowed GET-only; any non-GET request is aborted (read-only inspection).
    guard = NetworkGuard(allow_loopback=allow_loopback, label="batch-scan",
                         provider_resources=True, read_only=True)
    try:
        browser = await get_shared_browser()
        context = await new_guarded_context(
            browser,
            guard,
            user_agent=user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        )
    except Exception as launch_err:  # e.g. Chromium missing / crashed
        await guard.close()
        return _failure(start_time, f"Browser unavailable: {type(launch_err).__name__}", "browser_unavailable")

    evidence: dict[str, Any] = {}
    try:
        page = await context.new_page()
        page.set_default_navigation_timeout(settings.REQUEST_TIMEOUT_MS)
        wait_kw = dict(settle_ms=settings.DETECTION_SETTLE_MS, evidence_wait_ms=settings.DETECTION_EVIDENCE_WAIT_MS)

        # 2. robots.txt / access restriction check (stop, never work around)
        robots_status = None
        if respect_robots:
            robots = await fetch_and_evaluate(page, expected_contact_page or url, settings.CRAWLER_USER_AGENT)
            robots_status = robots["robots_status"]
            evidence["robots"] = {k: robots.get(k) for k in ("robots_status", "http_status", "reason", "robots_url")}
            if not robots["proceed"]:
                status = "blocked_by_robots" if robots_status == "disallowed" else "blocked_by_challenge"
                return _failure(start_time, robots["reason"], "robots_or_access_restriction",
                                scan_status=status, robots_status=robots_status,
                                evidence=evidence, network_guard=guard.summary())

        # 3. Navigate: CSV contact page first (single visit), else landing page + discovery
        http_status = 200
        contact_source = None
        contact_page_url = None
        detection = None
        page_title = None
        landed = False

        if expected_contact_page:
            try:
                response = await page.goto(expected_contact_page, wait_until="domcontentloaded")
                http_status = response.status if response else 200
                if http_status < 400:
                    landed = True
                    contact_source = "csv"
                    contact_page_url = guard.effective_url(page.url)
                else:
                    evidence["csv_contact_page_http_status"] = http_status
            except Exception as nav_err:
                evidence["csv_contact_page_error"] = type(nav_err).__name__

        if not landed:
            try:
                response = await page.goto(url, wait_until="domcontentloaded")
                http_status = response.status if response else 200
            except Exception as nav_err:
                return _failure(start_time, f"Navigation error: {str(nav_err)}", "navigation_failure",
                                robots_status=robots_status, evidence=evidence, network_guard=guard.summary())
            if http_status >= 400:
                return _failure(start_time, f"HTTP {http_status} from the website", "http_error",
                                robots_status=robots_status, evidence=evidence, network_guard=guard.summary())

        page_title = await page.title()
        detection = await detect_on_page(page, guard, **wait_kw)

        if not landed and not detection["has_contact_form"] and detection["status"] != "unsupported_challenge":
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
                    if not any(kw in href.lower() or kw in text for kw in CONTACT_PAGE_KEYWORDS):
                        continue
                    resolved_url = urljoin(landing_url, href)
                    if same_site(urlparse(resolved_url).netloc.lower(), base_domain):
                        contact_page_url = resolved_url
                        contact_source = "discovered"
                        try:
                            await page.goto(contact_page_url, wait_until="domcontentloaded")
                            contact_title = await page.title()
                            contact_detection = await detect_on_page(page, guard, **wait_kw)
                            if contact_detection["detected_providers"] or contact_detection["has_contact_form"]:
                                detection = contact_detection
                                page_title = contact_title
                        except Exception:
                            pass
                        break
            except Exception:
                pass

        # 4. Evidence: screenshot of the page that was actually inspected
        screenshot_rel = None
        if evidence_dir is not None:
            try:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                shot = evidence_dir / f"{evidence_name}.png"
                await page.screenshot(path=str(shot), full_page=False)
                screenshot_rel = shot.relative_to(settings.EVIDENCE_DIR.parent).as_posix()
            except Exception:
                screenshot_rel = None

        # 5. Optional non-transmitting form probe
        form_probe = None
        if probe_forms:
            from app.services.form_probe import probe_and_fill
            form_probe = await probe_and_fill(page, context, guard)
            if evidence_dir is not None and form_probe.get("filled_fields"):
                try:  # genuine screenshot of the synthetically filled (never submitted) form
                    shot = evidence_dir / f"{evidence_name}_filled.png"
                    await page.screenshot(path=str(shot), full_page=False)
                    form_probe["filled_screenshot"] = shot.relative_to(settings.EVIDENCE_DIR.parent).as_posix()
                except Exception:
                    pass

        duration_ms = (time.perf_counter() - start_time) * 1000
        captcha_detected = len(detection["detected_providers"]) > 0 or detection["status"] == "unsupported_challenge"
        provider_name = ", ".join(detection["detected_providers"]) if detection["detected_providers"] else None
        summary = guard.summary()
        evidence.update({
            "final_url": guard.effective_url(page.url),
            "http_status": http_status,
            "contact_source": contact_source,
            "settle": detection.get("settle"),
            "observability_note": detection.get("observability_note"),
            "blocked_requests": [{"url": b["url"][:200], "reason": b["reason"][:160]} for b in summary["blocked_requests"][:50]],
            "blocked_request_count": len(summary["blocked_requests"]),
            "provider_requests": summary["provider_requests"][:50],
        })

        return {
            "success": True,
            "scan_status": detection["status"],
            "page_title": page_title,
            "contact_page_url": contact_page_url,
            "contact_source": contact_source,
            "contact_form_found": detection["has_contact_form"],
            "captcha_detected": captcha_detected,
            "captcha_provider": provider_name,
            "detected_providers": detection["detected_providers"],
            "detection_method": detection["detection_method"],
            "is_active_challenge": detection["is_active_challenge"],
            "human_review_required": detection["human_review_required"],
            "error_details": None,
            "captcha_subtype": detection.get("captcha_subtype"),
            "widget_state": detection.get("widget_state"),
            "widget_loaded": detection.get("widget_loaded", False),
            "detections": detection.get("detections", []),
            "blocked_provider_resources": detection.get("blocked_provider_resources", []),
            "robots_status": robots_status,
            "screenshot_path": screenshot_rel,
            "form_probe": form_probe,
            "evidence": evidence,
            "network_guard": summary,
            "inspection_duration_ms": round(duration_ms, 2),
        }

    except Exception as general_err:
        return _failure(start_time, str(general_err), "unhandled_exception",
                        evidence=evidence, network_guard=guard.summary())

    finally:
        await context.close()
        await guard.close()
