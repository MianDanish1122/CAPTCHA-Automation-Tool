"""Stage 2 (real-world QA): shared rendered-page CAPTCHA detection engine."""
import http.server
import threading

import pytest

from app.services.browser_scanner import get_shared_browser
from app.services.captcha_detection import classify_observation, detect_on_page
from app.services.network_guard import NetworkGuard, new_guarded_context


def obs(**kw):
    base = {"containers": [], "scripts": [], "iframes": [], "token_fields": [], "badges": 0, "inline_hits": []}
    base.update(kw)
    return base


def only(result):
    assert len(result["detections"]) == 1, result
    return result["detections"][0]


# ------------------------------------------------------------------ pure classification
def test_nothing_found():
    r = classify_observation(obs())
    assert r["detections"] == [] and r["primary"] is None and not r["any_widget_loaded"]


def test_recaptcha_v2_checkbox_iframe_loaded():
    d = only(classify_observation(obs(
        scripts=["https://www.google.com/recaptcha/api.js"],
        containers=[{"cls": "g-recaptcha", "has_sitekey": True, "size": None}],
        iframes=[{"src": "https://www.google.com/recaptcha/api2/anchor?k=x&size=normal", "visible": True}])))
    assert d["provider"] == "google_recaptcha" and d["subtype"] == "v2_checkbox"
    assert d["widget_state"] == "iframe_loaded" and d["widget_loaded"] is True


def test_recaptcha_invisible_by_size_param():
    d = only(classify_observation(obs(
        iframes=[{"src": "https://www.google.com/recaptcha/api2/anchor?k=x&size=invisible", "visible": False}])))
    assert d["subtype"] == "invisible"


def test_recaptcha_v3_script_only_render_param():
    d = only(classify_observation(obs(scripts=["https://www.google.com/recaptcha/api.js?render=6LabcdefSITEKEY"])))
    assert d["subtype"] == "v3_score_based" and d["widget_state"] == "script_only" and d["widget_loaded"] is False


def test_recaptcha_enterprise_marked():
    d = only(classify_observation(obs(
        scripts=["https://www.google.com/recaptcha/enterprise.js?render=KEY"])))
    assert d["subtype"].startswith("enterprise")


def test_recaptcha_badge_only_counts_as_loaded_invisible():
    d = only(classify_observation(obs(badges=1, scripts=["https://www.google.com/recaptcha/api.js?render=K"])))
    assert d["subtype"] == "invisible" and d["widget_state"] == "badge_only" and d["widget_loaded"]


def test_hcaptcha_checkbox_and_invisible():
    d = only(classify_observation(obs(
        containers=[{"cls": "h-captcha", "size": None}],
        iframes=[{"src": "https://newassets.hcaptcha.com/captcha/v1/x/static/hcaptcha.html#frame=checkbox", "visible": True}])))
    assert d["provider"] == "hcaptcha" and d["subtype"] == "checkbox" and d["widget_loaded"]
    d2 = only(classify_observation(obs(containers=[{"cls": "h-captcha", "size": "invisible"}])))
    assert d2["subtype"] == "invisible" and d2["widget_state"] == "container_only" and not d2["widget_loaded"]


def test_turnstile_variants():
    d = only(classify_observation(obs(
        containers=[{"cls": "cf-turnstile", "appearance": "interaction-only"}],
        iframes=[{"src": "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/x", "visible": True}])))
    assert d["provider"] == "cloudflare_turnstile" and d["subtype"] == "interaction_only" and d["widget_loaded"]
    d2 = only(classify_observation(obs(scripts=["https://challenges.cloudflare.com/turnstile/v0/api.js"],
                                       containers=[{"cls": "cf-turnstile"}])))
    assert d2["subtype"] == "managed_or_non_interactive" and d2["widget_state"] == "container_only"


def test_frame_urls_from_playwright_count_as_iframes():
    r = classify_observation(obs(), frame_urls=["https://js.hcaptcha.com/1/frame.html"])
    assert only(r)["provider"] == "hcaptcha" and r["any_widget_loaded"]


def test_lookalike_hosts_are_not_providers():
    r = classify_observation(obs(
        scripts=["https://evil.example/recaptcha/api.js", "https://hcaptcha.com.evil.example/1/api.js",
                 "https://challenges.cloudflare.com.evil.example/turnstile/v0/api.js"],
        iframes=[{"src": "https://www.google.com/maps/embed", "visible": True}]))
    assert r["detections"] == []


def test_token_field_values_are_never_collected():
    # the collector only exposes the field NAME; the classifier has no value channel at all
    r = classify_observation(obs(token_fields=[{"name": "g-recaptcha-response"}]))
    assert "value" not in str(r)
    assert only(r)["provider"] == "google_recaptcha"


def test_observability_note_when_provider_resources_blocked_and_nothing_seen():
    r = classify_observation(obs(), blocked_provider_resources=["https://www.google.com/recaptcha/api.js"])
    assert r["observability_note"] and "NOT evidence of absence" in r["observability_note"]


def test_multiple_providers_reported():
    r = classify_observation(obs(
        scripts=["https://www.google.com/recaptcha/api.js", "https://js.hcaptcha.com/1/api.js"]))
    assert set(r["providers"]) == {"google_recaptcha", "hcaptcha"}


# ------------------------------------------------------------------ real Chromium on a local site
INLINE_DELAYED = b"""<html><head><title>Contact</title></head><body><form method=post action=/x>
<input name=email><textarea name=msg></textarea><div id=slot></div></form>
<script>setTimeout(function(){
  var d=document.createElement('div'); d.className='g-recaptcha'; d.setAttribute('data-sitekey','K');
  document.getElementById('slot').appendChild(d);
  var s=document.createElement('script'); s.src='https://www.google.com/recaptcha/api.js';
  document.head.appendChild(s); }, 1200);</script></body></html>"""

NO_CAPTCHA = b"""<html><head><title>Hello</title></head><body><form method=post action=/x>
<input name=email><textarea name=msg></textarea></form></body></html>"""

V3_SCRIPT = b"""<html><head><title>C</title></head><body><form><input name=a><textarea name=b></textarea></form>
<script src="https://www.google.com/recaptcha/api.js?render=SITEKEYSITEKEY"></script></body></html>"""

IFRAME_HC = b"""<html><head><title>C</title></head><body><form><input name=a><textarea name=b></textarea>
<div class="h-captcha" data-sitekey="K"></div></form>
<iframe src="https://newassets.hcaptcha.com/captcha/v1/x/static/hcaptcha.html" width=300 height=80></iframe></body></html>"""

PAGES = {"/delayed": INLINE_DELAYED, "/none": NO_CAPTCHA, "/v3": V3_SCRIPT, "/hc": IFRAME_HC}


class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = PAGES.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def site():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


async def _detect(url, **kw):
    guard = NetworkGuard(allow_loopback=True, read_only=True, label="t-detect")
    browser = await get_shared_browser()
    ctx = await new_guarded_context(browser, guard)
    try:
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        return await detect_on_page(page, guard, **kw)
    finally:
        await ctx.close()
        await guard.close()


@pytest.mark.anyio
async def test_no_captcha_page_reports_none(site):
    r = await _detect(site + "/none", settle_ms=1500, evidence_wait_ms=800)
    assert r["detected_providers"] == [] and r["widget_state"] == "none" and r["widget_loaded"] is False
    assert r["human_review_required"] is False


@pytest.mark.anyio
async def test_javascript_delayed_widget_is_found_by_rendered_detection(site):
    """The static HTML at domcontentloaded has NO recaptcha marker; the rendered DOM gets one after ~1.2s."""
    r = await _detect(site + "/delayed", settle_ms=1500, evidence_wait_ms=4000)
    assert "google_recaptcha" in r["detected_providers"], r
    assert r["human_review_required"] is True
    assert r["detection_method"].startswith("rendered_dom")


@pytest.mark.anyio
async def test_script_only_v3_is_flagged_but_not_reported_as_loaded_widget(site):
    r = await _detect(site + "/v3", settle_ms=1500, evidence_wait_ms=800)
    assert "google_recaptcha" in r["detected_providers"]
    assert r["captcha_subtype"] == "v3_score_based"
    assert r["widget_loaded"] is False and r["widget_state"] == "script_only"


TEXT_MENTION = b"""<html><head><title>C</title></head><body><form><input name=a><textarea name=b></textarea></form>
<script>var cfg = {"note": "we may use hcaptcha.com one day"};</script><div class="cf-turnstile" data-sitekey="K"></div></body></html>"""
PAGES["/mention"] = TEXT_MENTION
PAGES["/mention_only"] = b"<html><head><title>C</title></head><body><p>docs: see hcaptcha.com for details</p></body></html>"


@pytest.mark.anyio
async def test_static_text_mention_is_not_reported_as_a_provider(site):
    """Regression from breadtopia.com: 'hcaptcha.com' appeared as text, only Turnstile was a real widget."""
    r = await _detect(site + "/mention", settle_ms=1500, evidence_wait_ms=500)
    assert r["detected_providers"] == ["cloudflare_turnstile"]
    assert r["unconfirmed_static_mentions"] == ["hcaptcha"]


@pytest.mark.anyio
async def test_text_only_mention_means_no_captcha_and_no_review(site):
    r = await _detect(site + "/mention_only", settle_ms=1500, evidence_wait_ms=500)
    assert r["detected_providers"] == [] and r["status"] == "no_known_captcha_detected"
    assert r["human_review_required"] is False and r["unconfirmed_static_mentions"] == ["hcaptcha"]


@pytest.mark.anyio
async def test_provider_iframe_in_dom_detected_even_if_content_cannot_load(site):
    """Provider fetch is blocked (no network in CI) but the iframe element + container prove the embed."""
    r = await _detect(site + "/hc", settle_ms=1500, evidence_wait_ms=800)
    assert "hcaptcha" in r["detected_providers"]
    assert r["captcha_subtype"] == "checkbox"
