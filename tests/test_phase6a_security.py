"""
Phase 6A security remediation tests: H1 (batch scanner SSRF / DNS pinning), H2 (fixture path
traversal), H3 (spoofable rate-limit key), H4 (IP range validation), no hard-coded frontend
credentials, and dependency declarations.
"""
import argparse
import ast
import asyncio
import http.server
import re
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import WebsiteInspection
from app.services import fixture_loader
from app.services.batch_processor import create_batch, run_batch_job
from app.services.browser_scanner import inspect_local_demo, inspect_website
from app.services.client_ip import resolve_client_ip
from app.services.csv_importer import import_websites
from app.services.fixture_loader import FixtureError, load_fixture_html, validate_fixture_name
from app.services.network_guard import NetworkGuard
from app.services.rate_limiter import limiter
from app.services.security_guard import SecurityGuard

ROOT = Path(__file__).resolve().parent.parent


# =====================================================================
# H2 - Fixture path traversal
# =====================================================================

BAD_FIXTURE_NAMES = [
    "../.env",
    "..\\.env",
    "../../.env",
    "..\\..\\.env",
    "%2e%2e/.env",
    "%2e%2e%2f.env",
    "%252e%252e%252f.env",          # double-encoded
    "..%5c..%5c.env",               # encoded backslash
    "/etc/passwd",
    "\\Windows\\win.ini",
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "c:win.ini",
    "google_recaptcha.html\x00.png",  # NUL injection
    "sub/google_recaptcha.html",
    "sub\\google_recaptcha.html",
    "./google_recaptcha.html",
    "..",
    ".",
    ".env",
    "google_recaptcha.txt",
    "google_recaptcha.html ",
    "google_recaptcha.html::$DATA",   # NTFS alternate data stream
    "",
]


@pytest.mark.parametrize("name", BAD_FIXTURE_NAMES)
def test_fixture_name_rejects_traversal(name):
    with pytest.raises(FixtureError):
        validate_fixture_name(name)


# Surrounding whitespace on the whole URL is trimmed by URL normalisation (harmless); every
# other malformed name must still be rejected at load time.
@pytest.mark.parametrize("name", [n for n in BAD_FIXTURE_NAMES if n == n.strip()])
def test_fixture_load_rejects_traversal(name):
    with pytest.raises(FixtureError):
        load_fixture_html(f"fixture://{name}")


def test_valid_fixture_still_loads_in_test_env():
    assert settings.APP_ENV == "test"
    html = load_fixture_html("fixture://google_recaptcha.html")
    assert "recaptcha" in html.lower()


def test_fixtures_disabled_in_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert settings.fixtures_enabled is False
    with pytest.raises(FixtureError):
        load_fixture_html("fixture://google_recaptcha.html")
    # ALLOW_FIXTURES=true must NOT override production
    monkeypatch.setattr(settings, "ALLOW_FIXTURES", True)
    assert settings.fixtures_enabled is False


def test_fixture_symlink_escape_rejected(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.html"
    secret.write_text("<html>SECRET</html>", encoding="utf-8")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    link = fixtures / "linked.html"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted on this system")
    monkeypatch.setattr(fixture_loader, "FIXTURES_DIR", fixtures)
    with pytest.raises(FixtureError):
        load_fixture_html("fixture://linked.html")


def test_csv_import_rejects_traversal_fixture_rows():
    csv_bytes = (
        "company_name,website_url\n"
        "Good,fixture://google_recaptcha.html\n"
        "Evil1,fixture://../../.env\n"
        "Evil2,fixture://..\\..\\.env\n"
        "Evil3,fixture://%2e%2e%2f.env\n"
        "Evil4,fixture:///etc/passwd\n"
    ).encode("utf-8")
    result = import_websites(csv_bytes)
    names = [w["company_name"] for w in result["websites"]]
    assert names == ["Good"]
    assert result["invalid_rows"] == 4


@pytest.mark.anyio
async def test_batch_fixture_traversal_cannot_read_env_file():
    """End-to-end: a traversal reference in a batch is rejected and leaks nothing."""
    assert (ROOT / ".env").exists() or True  # target file need not exist for rejection to hold
    batch_id = create_batch(
        [
            {"company_name": "Traversal", "website_url": "fixture://../../.env"},
            {"company_name": "Traversal2", "website_url": "fixture://..\\..\\.env"},
            {"company_name": "Legit", "website_url": "fixture://normal_contact_form.html"},
        ],
        start_background=False,
    )
    await run_batch_job(batch_id)
    db = SessionLocal()
    try:
        rows = {r.company_name: r for r in db.query(WebsiteInspection).filter_by(batch_id=batch_id)}
    finally:
        db.close()
    for name in ("Traversal", "Traversal2"):
        assert rows[name].scan_status == "failed"
        assert "Fixture rejected" in (rows[name].error_details or "")
        assert rows[name].page_title is None
    assert rows["Legit"].scan_status in ("no_known_captcha_detected", "completed")


@pytest.mark.anyio
async def test_batch_fixtures_blocked_in_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    batch_id = create_batch(
        [{"company_name": "ProdFixture", "website_url": "fixture://normal_contact_form.html"}],
        start_background=False,
    )
    await run_batch_job(batch_id)
    db = SessionLocal()
    try:
        row = db.query(WebsiteInspection).filter_by(batch_id=batch_id).one()
    finally:
        db.close()
    assert row.scan_status == "failed"
    assert "disabled" in (row.error_details or "").lower()


# =====================================================================
# H4 - IP range validation
# =====================================================================

BLOCKED_IPS = [
    # IPv4 private (RFC 1918)
    "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.254", "192.168.1.1",
    # loopback
    "127.0.0.1", "127.255.255.254", "::1",
    # link-local
    "169.254.1.1", "169.254.169.254", "fe80::1", "fe80::abcd",
    # CGNAT 100.64.0.0/10
    "100.64.0.0", "100.64.0.1", "100.100.100.100", "100.127.255.255",
    # reserved / this-network / broadcast / class E
    "0.0.0.0", "0.1.2.3", "240.0.0.1", "255.255.255.255",
    # multicast
    "224.0.0.1", "239.255.255.250", "ff02::1", "ff05::2",
    # IPv6 ULA
    "fc00::1", "fd00::1", "fd12:3456:789a::1",
    # unspecified, documentation, benchmarking, IETF assignments
    "::", "192.0.0.1", "192.0.2.1", "198.51.100.1", "203.0.113.1", "198.18.0.1", "2001:db8::1",
    # IPv6 forms embedding IPv4 / tunnelling
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "::ffff:100.64.0.1",
    "64:ff9b::7f00:1", "64:ff9b::a00:1", "2002:7f00:1::1", "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    # cloud metadata
    "fd00:ec2::254",
]

ALLOWED_IPS = ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111", "2001:4860:4860::8888"]


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_non_public_ips_are_blocked(ip):
    allowed, reason = SecurityGuard.is_ip_allowed(ip)
    assert allowed is False, f"{ip} must be blocked"
    assert reason


@pytest.mark.parametrize("ip", ALLOWED_IPS)
def test_public_ips_are_allowed(ip):
    allowed, _ = SecurityGuard.is_ip_allowed(ip)
    assert allowed is True


def test_cgnat_reason_is_specific():
    allowed, reason = SecurityGuard.is_ip_allowed("100.64.0.1")
    assert not allowed and "CGNAT" in reason


@pytest.mark.parametrize("url", [
    "http://100.64.0.1/", "http://100.127.255.254/", "http://[fd00::1]/", "http://[fe80::1]/",
    "http://[::ffff:127.0.0.1]/", "http://[::ffff:10.0.0.1]/", "http://0.0.0.0/",
    "http://224.0.0.1/", "http://169.254.169.254/latest/meta-data/",
])
def test_validate_target_url_blocks_non_public_literals(url, monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["example.com"])
    allowed, _ = SecurityGuard.validate_target_url(url, enforce_live_scan=False, allow_loopback=True)
    assert allowed is False


def test_hostname_resolving_to_cgnat_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["example.com"])
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.64.0.9", 80))],
    )
    allowed, reason = SecurityGuard.validate_target_url("http://cgnat.example.com/", enforce_live_scan=False)
    assert allowed is False and "100.64.0.9" in reason


def test_one_bad_dns_record_rejects_whole_host(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 80)),
        ],
    )
    ips, reason = SecurityGuard.resolve_public_addresses("mixed.example.com", 80)
    assert ips == [] and "10.0.0.7" in reason


# =====================================================================
# H3 - Rate limiter trusts spoofed X-Forwarded-For
# =====================================================================

def test_client_ip_ignores_forwarding_header_by_default():
    assert resolve_client_ip("203.0.113.50", "1.2.3.4", trusted_proxies=[]) == "203.0.113.50"


def test_client_ip_ignores_header_from_untrusted_peer():
    assert resolve_client_ip("203.0.113.50", "1.2.3.4", trusted_proxies=["10.0.0.0/8"]) == "203.0.113.50"


def test_client_ip_honors_header_from_trusted_proxy_rightmost_untrusted():
    # client-supplied "6.6.6.6" is prepended; the proxy appended the real client address.
    got = resolve_client_ip("10.0.0.2", "6.6.6.6, 198.51.100.7", trusted_proxies=["10.0.0.0/8"])
    assert got == "198.51.100.7"


def test_client_ip_skips_chained_trusted_proxies():
    got = resolve_client_ip("10.0.0.2", "198.51.100.7, 10.0.0.9", trusted_proxies=["10.0.0.0/8"])
    assert got == "198.51.100.7"


def test_client_ip_malformed_chain_falls_back_to_peer():
    assert resolve_client_ip("10.0.0.2", "not-an-ip, 1.2.3.4x", trusted_proxies=["10.0.0.0/8"]) == "10.0.0.2"


def test_client_ip_invalid_trusted_config_trusts_nothing():
    assert resolve_client_ip("10.0.0.2", "1.2.3.4", trusted_proxies=["garbage"]) == "10.0.0.2"


def test_login_rate_limit_cannot_be_bypassed_with_spoofed_xff(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])
    limiter.reset()
    client = TestClient(app)
    client._unauthenticated = True
    limit = settings.RATE_LIMIT_LOGIN_PER_MIN
    statuses = []
    for i in range(limit + 4):
        res = client.post(
            "/api/auth/login",
            json={"username": "nobody_user", "password": "wrong-password"},
            headers={"X-Forwarded-For": f"198.51.100.{i + 1}"},  # rotate spoofed identity
        )
        statuses.append(res.status_code)
    limiter.reset()
    assert statuses[:limit] == [401] * limit
    assert all(code == 429 for code in statuses[limit:]), statuses


def test_forwarded_header_honored_only_from_configured_proxy(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.0/8"])
    limiter.reset()
    client = TestClient(app, client=("10.0.0.2", 50000))
    client._unauthenticated = True
    limit = settings.RATE_LIMIT_LOGIN_PER_MIN
    codes = []
    for i in range(limit + 2):
        # Different real clients behind the trusted proxy get independent buckets.
        res = client.post(
            "/api/auth/login",
            json={"username": "nobody_user", "password": "wrong-password"},
            headers={"X-Forwarded-For": f"198.51.100.{i + 1}"},
        )
        codes.append(res.status_code)
    limiter.reset()
    assert codes == [401] * (limit + 2)


# =====================================================================
# H1 - Batch scanner SSRF: redirects, subresources, DNS pinning, TLS
# =====================================================================

class _Handler(http.server.BaseHTTPRequestHandler):
    hits: list = []

    def log_message(self, *args):
        pass

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        _Handler.hits.append(self.path)
        if self.path == "/":
            self._send(200, b"<html><head><title>Home</title></head><body>ok</body></html>",
                       {"Content-Type": "text/html"})
        elif self.path == "/redir-private":
            self._send(302, b"", {"Location": "http://10.0.0.1/admin"})
        elif self.path == "/redir-metadata":
            self._send(302, b"", {"Location": "http://169.254.169.254/latest/meta-data/"})
        elif self.path == "/redir-cgnat":
            self._send(302, b"", {"Location": "http://100.64.0.1/"})
        elif self.path == "/redir-cross-domain":
            self._send(302, b"", {"Location": "http://example.com/"})
        elif self.path == "/redir-ok":
            self._send(302, b"", {"Location": "/landing"})
        elif self.path == "/landing":
            self._send(200, b"<html><head><title>Landing OK</title></head><body>hi</body></html>",
                       {"Content-Type": "text/html"})
        elif self.path == "/subresources":
            page = (
                b"<html><head><title>Subres</title></head><body>"
                b"<img src='http://10.0.0.5/pixel.png'>"
                b"<script src='http://169.254.169.254/latest/meta-data/x.js'></script>"
                b"<img src='http://100.64.0.1/p.png'>"
                b"<script>fetch('http://192.168.1.1/admin').catch(()=>{});</script>"
                b"<form><input name='email'><textarea name='message'></textarea></form>"
                b"</body></html>"
            )
            self._send(200, page, {"Content-Type": "text/html"})
        else:
            self._send(404, b"nope")


@pytest.fixture
def local_server():
    _Handler.hits = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _blocked_urls(result):
    return [b["url"] for b in result.get("network_guard", {}).get("blocked_requests", [])]


@pytest.mark.anyio
async def test_batch_scan_follows_safe_same_host_redirect(local_server):
    result = await inspect_website(f"{local_server}/redir-ok", allow_loopback=True)
    assert result["success"] is True
    assert result["page_title"] == "Landing OK"


@pytest.mark.anyio
@pytest.mark.parametrize("path,target", [
    ("/redir-private", "10.0.0.1"),
    ("/redir-metadata", "169.254.169.254"),
    ("/redir-cgnat", "100.64.0.1"),
    ("/redir-cross-domain", "example.com"),
])
async def test_batch_scan_blocks_redirects_to_non_public_or_foreign_hosts(local_server, path, target):
    result = await inspect_website(f"{local_server}{path}", allow_loopback=True)
    assert result["success"] is False
    assert any(target in u for u in _blocked_urls(result)), result.get("network_guard")


@pytest.mark.anyio
async def test_batch_scan_blocks_unauthorized_subresources(local_server):
    result = await inspect_website(f"{local_server}/subresources", allow_loopback=True)
    assert result["success"] is True  # page itself is fine
    blocked = _blocked_urls(result)
    for needle in ("10.0.0.5", "169.254.169.254", "100.64.0.1", "192.168.1.1"):
        assert any(needle in u for u in blocked), (needle, blocked)


@pytest.mark.anyio
async def test_batch_scan_rejects_private_target_before_any_network():
    result = await inspect_website("http://10.0.0.1/", allow_loopback=True)
    assert result["success"] is False
    assert "Security restriction" in result["error"]


@pytest.mark.anyio
async def test_inspect_demo_html_cannot_reach_network(local_server):
    """Untrusted demo HTML must never cause outbound requests (even to loopback)."""
    html = (
        f"<html><body><img src='{local_server}/leak.png'>"
        f"<script>fetch('{local_server}/leak-xhr')</script></body></html>"
    )
    result = await inspect_local_demo(html)
    assert result["success"] is True
    assert "/leak.png" not in _Handler.hits
    assert "/leak-xhr" not in _Handler.hits


def test_dns_rebinding_second_lookup_is_validated(monkeypatch):
    """
    Classic rebinding: the first lookup (validation) returns a public IP, the next lookup
    returns loopback. The pinned resolution is validated itself, so the flip is rejected.
    """
    monkeypatch.setattr(settings, "ALLOWED_DOMAINS", ["example.com"])
    answers = iter([
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    ])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: next(answers))
    guard = NetworkGuard()
    ips, reason = asyncio.run(guard._validate("http://rebind.example.com/", None))
    assert ips == []
    assert "127.0.0.1" in reason


def test_fetch_connects_to_pinned_validated_ip_not_hostname(monkeypatch):
    """The HTTP connection targets the validated IP; the hostname is used only for Host/SNI."""
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = SimpleNamespace(multi_items=lambda: [("content-type", "text/html")])

        async def aiter_bytes(self):
            yield b"<html></html>"

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def stream(self, method, target, headers=None, content=None, extensions=None):
            captured.update(method=method, target=target, headers=headers, extensions=extensions)
            return FakeStream()

    class FakeRequest:
        url = "https://pinned.example.com/path?q=1"
        method = "GET"
        post_data_buffer = None

        async def all_headers(self):
            return {"user-agent": "x", "host": "evil.test", "accept-encoding": "br"}

    guard = NetworkGuard()
    monkeypatch.setattr(guard, "_get_client", lambda: FakeClient())
    req = FakeRequest()
    headers_in = asyncio.run(req.all_headers())
    status, _, body = asyncio.run(
        guard._pinned_fetch_once(req.url, req.method, headers_in, None, ["93.184.216.34"])
    )
    assert status == 200 and body == b"<html></html>"
    assert captured["target"] == "https://93.184.216.34:443/path?q=1"
    assert captured["headers"]["Host"] == "pinned.example.com"
    assert captured["extensions"] == {"sni_hostname": "pinned.example.com"}
    assert captured["headers"]["Accept-Encoding"] == "gzip, deflate"


def test_tls_verification_enabled_by_default(monkeypatch):
    import httpx
    seen = {}
    real = httpx.AsyncClient

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", spy)
    assert settings.SCAN_ALLOW_INVALID_CERTS is False
    guard = NetworkGuard()
    asyncio.run(_open_close(guard))
    assert seen["verify"] is True
    assert seen["trust_env"] is False


async def _open_close(guard):
    guard._get_client()
    await guard.close()


def test_invalid_certs_flag_rejected_in_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ALLOW_DEV_LOOPBACK", False)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setattr(settings, "SCAN_ALLOW_INVALID_CERTS", True)
    with pytest.raises(ValueError):
        settings.validate_production_config()


def test_no_ignore_https_errors_in_source():
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "ignore_https_errors=True" not in text, path


# =====================================================================
# Hard-coded credentials / provisioning
# =====================================================================

FORBIDDEN_CRED_PATTERNS = [
    re.compile(r"AdminSecure2026"),
    re.compile(r"OperatorPass123"),
    re.compile(r"AdminPass123"),
    re.compile(r"handleQuickLogin"),
    re.compile(r"Quick Test Credentials", re.I),
]


def _iter_source_files():
    for base, suffixes in (
        (ROOT / "frontend" / "app", (".tsx", ".ts")),
        (ROOT / "frontend" / "components", (".tsx", ".ts")),
        (ROOT / "frontend" / "lib", (".tsx", ".ts")),
        (ROOT / "app", (".py",)),
        (ROOT / "tests", (".py",)),
    ):
        for path in base.rglob("*"):
            if path.suffix in suffixes and "__pycache__" not in path.parts and path.name != "test_phase6a_security.py":
                yield path


def test_no_hardcoded_credentials_in_sources():
    offenders = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_CRED_PATTERNS:
            if pattern.search(text):
                offenders.append((str(path.relative_to(ROOT)), pattern.pattern))
    assert offenders == []


def test_no_hardcoded_credentials_in_built_frontend_bundle():
    static_dir = ROOT / "frontend" / ".next" / "static"
    if not static_dir.exists():
        pytest.skip("Frontend not built; run `npm run build` to enable the bundle check")
    offenders = []
    for path in static_dir.rglob("*.js"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_CRED_PATTERNS:
            if pattern.search(text):
                offenders.append((path.name, pattern.pattern))
    assert offenders == []


def test_cli_password_resolution_never_requires_command_line(monkeypatch):
    from app.cli import obtain_password, MIN_PASSWORD_LENGTH
    pw, generated = obtain_password(argparse.Namespace(generate_password=True, password=None))
    assert generated and len(pw) >= MIN_PASSWORD_LENGTH
    monkeypatch.setenv("ADMIN_PASSWORD", "from-environment-123")
    pw, generated = obtain_password(argparse.Namespace(generate_password=False, password=None))
    assert pw == "from-environment-123" and not generated


# =====================================================================
# Dependency declarations
# =====================================================================

IMPORT_TO_REQUIREMENT = {
    "fastapi": "fastapi", "starlette": "fastapi", "uvicorn": "uvicorn", "pydantic": "pydantic",
    "playwright": "playwright", "pandas": "pandas", "multipart": "python-multipart",
    "dotenv": "python-dotenv", "sqlalchemy": "sqlalchemy", "cv2": "opencv-python",
    "numpy": "numpy", "PIL": "pillow", "pytesseract": "pytesseract", "httpx": "httpx",
    "jwt": "pyjwt", "bcrypt": "bcrypt", "alembic": "alembic", "pytest": "pytest",
}


def _declared_requirements():
    names = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].lower().replace("_", "-")
        names.add(name)
    return names


def test_requirements_declare_every_third_party_import():
    declared = _declared_requirements()
    stdlib = set(sys.stdlib_module_names)
    local = {"app", "tests"}
    missing = set()
    scan_dirs = [ROOT / "app", ROOT / "tests", ROOT / "alembic"]
    files = [p for d in scan_dirs for p in d.rglob("*.py") if "__pycache__" not in p.parts]
    files += [p for p in ROOT.glob("*.py")]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for mod in mods:
                if mod in stdlib or mod in local or mod == "conftest":
                    continue
                req = IMPORT_TO_REQUIREMENT.get(mod)
                if req is None or req not in declared:
                    missing.add((mod, str(path.relative_to(ROOT))))
    assert missing == set(), f"Undeclared third-party imports: {sorted(missing)}"


def test_security_critical_dependencies_are_declared_with_bounds():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for dep in ("pyjwt", "bcrypt", "alembic"):
        assert re.search(rf"^{dep}[<>=]", text, re.M), dep
