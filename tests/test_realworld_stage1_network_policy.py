"""Stage 1 (real-world QA): apex/www redirects, narrow provider-widget policy, read-only and lockdown modes."""
import asyncio
import http.server
import socket
import threading

import pytest

from app.config import settings
from app.services.browser_scanner import get_shared_browser
from app.services.network_guard import NetworkGuard, new_guarded_context
from app.services.provider_hosts import is_provider_resource, provider_for_url
from app.services.security_guard import SecurityGuard, host_matches_allowed, same_site, strip_www


# ------------------------------------------------------------------ apex / www
@pytest.mark.parametrize("a,b,expected", [
    ("example.com", "www.example.com", True), ("www.example.com", "example.com", True),
    ("example.com", "example.com", True), ("EXAMPLE.com.", "www.example.com", True),
    ("mail.example.com", "example.com", False), ("example.com", "evil.com", False),
    ("example.com", "example.com.evil.com", False), ("www.example.com", "www.other.com", False),
    ("", "example.com", False),
])
def test_same_site(a, b, expected):
    assert same_site(a, b) is expected


def test_strip_www_only_strips_leading_label():
    assert strip_www("www.example.com") == "example.com"
    assert strip_www("awww.example.com") == "awww.example.com"
    assert strip_www("example.com") == "example.com"


def test_redirect_apex_to_www_allowed_but_other_hosts_still_blocked():
    ok, _ = SecurityGuard.validate_redirect_url("https://www.example.com/", "https://example.com/", enforce_live_scan=False)
    assert ok
    ok, _ = SecurityGuard.validate_redirect_url("https://example.com/", "https://www.example.com/x", enforce_live_scan=False)
    assert ok
    for bad in ("https://mail.example.com/", "https://evil.com/", "https://example.com.evil.com/"):
        ok, why = SecurityGuard.validate_redirect_url(bad, "https://example.com/", enforce_live_scan=False)
        assert not ok and "Cross-domain" in why


def test_redirect_to_private_ip_still_blocked_even_for_www():
    ok, _ = SecurityGuard.validate_redirect_url("http://10.0.0.1/", "https://www.example.com/", enforce_live_scan=False)
    assert not ok


@pytest.mark.parametrize("host,allowed,expected", [
    ("www.bigfrog.com", "bigfrog.com", True), ("bigfrog.com", "www.bigfrog.com", True),
    ("shop.bigfrog.com", "bigfrog.com", True), ("bigfrog.com.evil.com", "bigfrog.com", False),
    ("evilbigfrog.com", "bigfrog.com", False), ("mail.bigfrog.com", "www.bigfrog.com", False),
])
def test_allowlist_matching_handles_apex_www_pair_without_broadening(host, allowed, expected):
    assert host_matches_allowed(host, allowed) is expected


# ------------------------------------------------------------------ provider resource policy
PROVIDER_OK = [
    "https://www.google.com/recaptcha/api.js", "https://www.google.com/recaptcha/api2/anchor?k=x",
    "https://www.recaptcha.net/recaptcha/api.js", "https://www.gstatic.com/recaptcha/releases/abc/recaptcha__en.js",
    "https://js.hcaptcha.com/1/api.js", "https://newassets.hcaptcha.com/captcha/v1/x/static/hcaptcha.html",
    "https://hcaptcha.com/1/api.js", "https://challenges.cloudflare.com/turnstile/v0/api.js",
    "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/x",
]
PROVIDER_DENIED = [
    "https://www.google.com/maps", "https://www.google.com/", "https://www.google.com/search?q=recaptcha",
    "https://www.google.com.evil.com/recaptcha/api.js", "https://evil.com/recaptcha/api.js",
    "https://evilhcaptcha.com/1/api.js", "https://hcaptcha.com.evil.com/1/api.js",
    "https://challenges.cloudflare.com/other/", "https://cloudflare.com/turnstile/",
    "http://www.google.com/recaptcha/api.js",                      # plain http
    "https://user:pw@www.google.com/recaptcha/api.js",             # credentials
    "https://www.gstatic.com/images/branding/x.png", "https://fonts.googleapis.com/css",
]


@pytest.mark.parametrize("url", PROVIDER_OK)
def test_provider_widget_resources_recognised(url):
    assert is_provider_resource(url, "GET") and is_provider_resource(url, "HEAD")
    assert provider_for_url(url) is not None


@pytest.mark.parametrize("url", PROVIDER_DENIED)
def test_everything_else_is_not_a_provider_resource(url):
    assert not is_provider_resource(url, "GET")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_provider_policy_is_get_head_only(method):
    assert not is_provider_resource("https://www.google.com/recaptcha/api2/reload?k=x", method)


def _fake_dns(monkeypatch, mapping):
    def fake(host, port, *a, **k):
        ip = mapping[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_guard_allows_provider_script_only_when_policy_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["target.example"])
    _fake_dns(monkeypatch, {"www.google.com": "142.250.80.4", "target.example": "93.184.216.34"})
    url = "https://www.google.com/recaptcha/api.js"
    on = NetworkGuard(provider_resources=True)
    ips, why = asyncio.run(on._validate(url, None, "GET"))
    assert ips == ["142.250.80.4"], why
    assert on.provider_requests == [url]
    off = NetworkGuard(provider_resources=False)
    ips, why = asyncio.run(off._validate(url, None, "GET"))
    assert ips == [] and "allowlist" in why


def test_provider_policy_does_not_open_other_google_paths_or_posts(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["target.example"])
    _fake_dns(monkeypatch, {"www.google.com": "142.250.80.4"})
    g = NetworkGuard(provider_resources=True)
    for url, method in (("https://www.google.com/maps", "GET"), ("https://www.google.com/recaptcha/api2/reload", "POST")):
        ips, why = asyncio.run(g._validate(url, None, method))
        assert ips == [] and "allowlist" in why


def test_provider_host_resolving_to_private_ip_is_still_blocked(monkeypatch):
    """Provider policy waives only the domain allow-list: DNS-rebinding/SSRF checks remain."""
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["target.example"])
    _fake_dns(monkeypatch, {"www.google.com": "10.0.0.7"})
    g = NetworkGuard(provider_resources=True)
    ips, why = asyncio.run(g._validate("https://www.google.com/recaptcha/api.js", None, "GET"))
    assert ips == [] and "prohibited" in why


def test_provider_redirect_to_non_provider_host_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["target.example"])
    _fake_dns(monkeypatch, {"www.google.com": "142.250.80.4", "evil.example": "93.184.216.34"})
    g = NetworkGuard(provider_resources=True)
    ips, why = asyncio.run(g._validate("https://evil.example/x", "https://www.google.com/recaptcha/api.js", "GET"))
    assert ips == []


def test_provider_to_provider_redirect_allowed(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["target.example"])
    _fake_dns(monkeypatch, {"www.google.com": "142.250.80.4", "www.recaptcha.net": "142.250.80.5"})
    g = NetworkGuard(provider_resources=True)
    ips, why = asyncio.run(g._validate("https://www.google.com/recaptcha/api.js", "https://www.recaptcha.net/recaptcha/api.js", "GET"))
    assert ips, why


# ------------------------------------------------------------------ read-only and lockdown (real Chromium)
class _Handler(http.server.BaseHTTPRequestHandler):
    log: list = []

    def log_message(self, *a):
        pass

    def _rec(self, body=b""):
        _Handler.log.append((self.command, self.path, body))

    def do_GET(self):
        self._rec()
        page = (b"<html><head><title>T</title></head><body><form id=f method='get' action='/gsubmit'>"
                b"<input name='email'><button>Go</button></form><form id=p method='post' action='/psubmit'>"
                b"<input name='msg'></form></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._rec(self.rfile.read(n) if n else b"")
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


@pytest.fixture
def local_site():
    _Handler.log = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


async def _page(guard):
    browser = await get_shared_browser()
    ctx = await new_guarded_context(browser, guard)
    return ctx, await ctx.new_page()


@pytest.mark.anyio
async def test_read_only_mode_aborts_post_but_allows_get(local_site):
    guard = NetworkGuard(allow_loopback=True, read_only=True, label="t-readonly")
    ctx, page = await _page(guard)
    try:
        await page.goto(local_site + "/", wait_until="domcontentloaded")
        result = await page.evaluate("""async () => {
            try { const r = await fetch('/psubmit', {method:'POST', body:'secret=1'}); return 'sent'; }
            catch (e) { return 'blocked'; }
        }""")
        await page.wait_for_timeout(300)
        assert result == "blocked"
        assert not any(m == "POST" for m, _, _ in _Handler.log)
        assert any(m == "GET" for m, _, _ in _Handler.log)
        assert any("POST blocked" in b["reason"] for b in guard.summary()["blocked_requests"])
    finally:
        await ctx.close()
        await guard.close()


@pytest.mark.anyio
async def test_lockdown_blocks_every_transmission_vector(local_site):
    """After lock(): Enter-key submit, JS form.submit(), requestSubmit, fetch POST/GET, XHR, sendBeacon, <img>, link nav."""
    guard = NetworkGuard(allow_loopback=True, read_only=True, label="t-lock")
    ctx, page = await _page(guard)
    try:
        await page.goto(local_site + "/", wait_until="domcontentloaded")
        baseline = len(_Handler.log)
        guard.lock()
        await ctx.set_offline(True)
        vectors = [
            "document.getElementById('p').submit()",                    # JavaScript submission (POST form)
            "document.getElementById('f').submit()",                    # JavaScript submission (GET form)
            "document.getElementById('f').requestSubmit()",
            """() => { fetch('/x', {method:'POST', body:'a=1'}).catch(()=>{});
                     fetch('/y?leak=1').catch(()=>{});
                     const x = new XMLHttpRequest(); x.open('POST','/z'); try { x.send('b=2'); } catch(e) {}
                     navigator.sendBeacon('/beacon', 'c=3');
                     const i = new Image(); i.src = '/pixel.gif?leak=2'; }""",
        ]
        for js in vectors:
            try:
                await page.evaluate(js)
            except Exception:
                pass
            await page.wait_for_timeout(250)
        # Enter-key submissions last (they navigate away; navigation is aborted by the lockdown)
        for sel in ("#f input[name=email]", "#p input[name=msg]"):
            try:
                await page.fill(sel, "qa@example.invalid", timeout=2000)
                await page.press(sel, "Enter", timeout=2000)
            except Exception:
                pass
            await page.wait_for_timeout(250)
        await page.wait_for_timeout(800)
        assert _Handler.log[baseline:] == [], f"request(s) reached the server after lockdown: {_Handler.log[baseline:]}"
    finally:
        await ctx.close()
        await guard.close()


@pytest.mark.anyio
async def test_new_guard_defaults_unchanged():
    g = NetworkGuard()
    assert g.provider_resources is False and g.read_only is False and g.locked is False
