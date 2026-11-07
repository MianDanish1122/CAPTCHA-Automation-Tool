import io
import json
import threading
import http.server
import socketserver
from pathlib import Path
from urllib.parse import urlparse
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import UrlScan, DiscoveredPage
from app.services.smart_crawler import (
    normalize_url,
    is_same_domain,
    calculate_page_score,
    SmartCrawler,
    inspect_url_pipeline,
)
from app.services.security_guard import SecurityGuard

client = TestClient(app)


# ----------------------------------------------------
# 1. Unit Tests: URL Normalization & Domain Matching
# ----------------------------------------------------

def test_normalize_url_basic():
    assert normalize_url("https://example.com/contact/") == "https://example.com/contact"
    assert normalize_url("https://example.com/path#fragment") == "https://example.com/path"
    assert normalize_url("https://EXAMPLE.COM:443/about") == "https://example.com/about"
    assert normalize_url("http://example.com:80/") == "http://example.com/"


def test_normalize_url_strips_tracking_params():
    url = "https://example.com/contact?utm_source=google&utm_medium=cpc&id=123"
    cleaned = normalize_url(url)
    assert "utm_source" not in cleaned
    assert "utm_medium" not in cleaned
    assert "id=123" in cleaned


def test_normalize_url_relative_resolution():
    base = "https://example.com/pages/index.html"
    assert normalize_url("/contact-us", base_url=base) == "https://example.com/contact-us"
    assert normalize_url("help.html", base_url=base) == "https://example.com/pages/help.html"


def test_normalize_url_invalid_schemes():
    assert normalize_url("javascript:alert(1)") == ""
    assert normalize_url("mailto:info@example.com") == ""
    assert normalize_url("tel:+123456789") == ""
    assert normalize_url("#anchor-only") == ""


def test_is_same_domain():
    assert is_same_domain("https://example.com/contact", "https://example.com") is True
    assert is_same_domain("https://www.example.com/about", "https://example.com") is True
    assert is_same_domain("https://sub.example.com", "https://example.com") is True
    assert is_same_domain("https://anotherdomain.com", "https://example.com") is False


# ----------------------------------------------------
# 2. Unit Tests: Candidate Page Scoring Heuristics
# ----------------------------------------------------

def test_calculate_page_score_contact_page():
    html = """
    <html>
      <head><title>Contact Our Team</title></head>
      <body>
        <h1>Get in Touch</h1>
        <p>Send a message using the form below or email us directly.</p>
        <form action="/submit" method="POST">
          <input type="text" name="name" />
          <input type="email" name="email" />
          <textarea name="message"></textarea>
          <button type="submit">Send Message</button>
        </form>
      </body>
    </html>
    """
    classification, confidence, evidence = calculate_page_score(
        url="https://example.com/contact-us",
        anchor_text="Contact Us",
        page_title="Contact Our Team",
        page_html=html,
        forms_count=1,
        has_inputs=True,
        has_textarea=True,
        depth=1,
    )
    assert classification == "contact_page"
    assert confidence >= 0.70
    assert evidence["contact_score"] >= 0.70
    assert len(evidence["path_signals"]) > 0
    assert len(evidence["anchor_signals"]) > 0
    assert len(evidence["form_signals"]) > 0


def test_calculate_page_score_support_page():
    html = """
    <html>
      <head><title>Help Desk & Customer Support</title></head>
      <body>
        <h1>Frequently Asked Questions</h1>
        <p>Browse our knowledge base or submit a ticket for assistance.</p>
      </body>
    </html>
    """
    classification, confidence, evidence = calculate_page_score(
        url="https://example.com/support",
        anchor_text="Customer Support",
        page_title="Help Desk & Customer Support",
        page_html=html,
        forms_count=0,
        has_inputs=False,
        has_textarea=False,
        depth=1,
    )
    assert classification == "support_page"
    assert confidence >= 0.60
    assert evidence["support_score"] >= 0.60
    assert "support" in evidence["path_signals"][0].lower()


def test_calculate_page_score_general_landing_page():
    html = """
    <html>
      <head><title>Acme Corporation - Welcome</title></head>
      <body>
        <h1>Leading Innovation</h1>
        <p>We build high-performance software for enterprise customers.</p>
      </body>
    </html>
    """
    classification, confidence, evidence = calculate_page_score(
        url="https://example.com/",
        anchor_text="Homepage",
        page_title="Acme Corporation - Welcome",
        page_html=html,
        forms_count=0,
        has_inputs=False,
        has_textarea=False,
        depth=0,
    )
    assert classification == "general_page"
    assert confidence >= 0.80


# ----------------------------------------------------
# 3. Unit Tests: Security Guard Redirect Validation
# ----------------------------------------------------

def test_validate_redirect_url_same_domain():
    allowed, msg = SecurityGuard.validate_redirect_url(
        redirect_url="https://example.com/contact-new",
        original_url="https://example.com/contact",
        enforce_live_scan=False,
    )
    assert allowed is True


def test_validate_redirect_url_blocks_cross_domain():
    allowed, msg = SecurityGuard.validate_redirect_url(
        redirect_url="https://evil-attacker.com/steal",
        original_url="https://example.com/contact",
        enforce_live_scan=False,
        require_same_domain=True,
    )
    assert allowed is False
    assert "Cross-domain" in msg


def test_validate_redirect_url_blocks_cloud_metadata():
    allowed, msg = SecurityGuard.validate_redirect_url(
        redirect_url="http://169.254.169.254/latest/meta-data/",
        original_url="https://example.com/",
        enforce_live_scan=False,
    )
    assert allowed is False
    assert "metadata" in msg.lower() or "prohibited" in msg.lower()


# ----------------------------------------------------
# 4. Integration Test: Live Crawler with Local Server
# ----------------------------------------------------

class MockSiteHandler(http.server.BaseHTTPRequestHandler):
    """Local multi-page HTTP mock server for realistic Playwright crawl testing."""

    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/robots.txt":
            content = "User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        if path == "/" or path == "/index.html":
            content = """
            <!DOCTYPE html>
            <html>
            <head><title>Acme Corp Home</title></head>
            <body>
              <h1>Welcome to Acme</h1>
              <nav>
                <a href="/contact">Contact Us</a>
                <a href="/support">Help & Support</a>
                <a href="/about">About Us</a>
                <a href="https://external-domain.com">External Partner</a>
              </nav>
            </body>
            </html>
            """
        elif path == "/contact":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
              <title>Contact Us - Acme Corp</title>
              <script src="https://www.google.com/recaptcha/api.js" async defer></script>
            </head>
            <body>
              <h1>Get in Touch</h1>
              <form action="/submit-contact" method="POST">
                <label>Name:</label>
                <input type="text" name="name" />
                <label>Email:</label>
                <input type="email" name="email" />
                <label>Message:</label>
                <textarea name="message"></textarea>
                <div class="g-recaptcha" data-sitekey="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"></div>
                <button type="submit">Send</button>
              </form>
            </body>
            </html>
            """
        elif path == "/support":
            content = """
            <!DOCTYPE html>
            <html>
            <head><title>Customer Support & FAQ</title></head>
            <body>
              <h1>Help Center</h1>
              <p>Search our knowledge base or submit a ticket.</p>
              <form action="/ticket">
                <input type="text" name="query" placeholder="Search FAQ" />
                <button type="submit">Search</button>
              </form>
            </body>
            </html>
            """
        elif path == "/about":
            content = """
            <!DOCTYPE html>
            <html>
            <head><title>About Acme Corp</title></head>
            <body>
              <h1>Our Story</h1>
              <p>Founded with a passion for quality software engineering.</p>
            </body>
            </html>
            """
        else:
            self.send_response(404)
            self.end_headers()
            return

        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def mock_web_server():
    """Start in-process local HTTP server for testing."""
    server = socketserver.TCPServer(("127.0.0.1", 0), MockSiteHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.shutdown()
    server.server_close()


@pytest.mark.anyio
async def test_crawler_full_discovery_pipeline(mock_web_server):
    """
    Test real Playwright crawling across mock multi-page website:
    - Homepage navigation & link extraction
    - Discovery and scoring of /contact, /support, and /about
    - Detection of contact form and Google reCAPTCHA
    - Ignored external domain link
    - Database persistence
    - Evidence screenshot creation
    """
    init_db()
    crawler = SmartCrawler(
        target_url=mock_web_server,
        max_pages=5,
        max_depth=2,
        allow_loopback=True,
    )
    from app.models import generate_uuid
    scan_id = generate_uuid()

    result = await crawler.crawl(scan_id=scan_id)

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["pages_crawled"] >= 3
    assert result["contact_pages_found"] >= 1
    assert result["captcha_detected"] is True
    assert "google_recaptcha" in result["captcha_providers"]

    # Verify Discovered Pages
    page_urls = [p["url"] for p in result["results"]]
    assert any("/contact" in u for u in page_urls)
    assert any("/support" in u for u in page_urls)
    # External domain was NOT crawled
    assert not any("external-domain.com" in u for u in page_urls)

    # Check /contact classification and CAPTCHA details
    contact_page = next(p for p in result["results"] if "/contact" in p["url"])
    assert contact_page["classification"] == "contact_page"
    assert contact_page["confidence_score"] >= 0.70
    assert contact_page["contact_form_found"] is True
    assert contact_page["captcha_detected"] is True
    assert "google_recaptcha" in contact_page["captcha_provider"]
    assert contact_page["human_review_required"] is True
    assert contact_page["screenshot_path"] is not None

    # Check evidence screenshot file actually exists on disk
    screenshot_file = settings.BASE_DIR / contact_page["screenshot_path"]
    assert screenshot_file.exists()


@pytest.mark.anyio
async def test_crawler_respects_max_pages_limit(mock_web_server):
    """Verify crawler strictly limits crawling to max_pages."""
    init_db()
    crawler = SmartCrawler(
        target_url=mock_web_server,
        max_pages=2,
        max_depth=2,
        allow_loopback=True,
    )
    from app.models import generate_uuid
    scan_id = generate_uuid()

    result = await crawler.crawl(scan_id=scan_id)
    assert result["success"] is True
    assert result["pages_crawled"] == 2


@pytest.mark.anyio
async def test_crawler_respects_depth_zero(mock_web_server):
    """Verify crawler at max_depth=0 only inspects the root page without following links."""
    init_db()
    crawler = SmartCrawler(
        target_url=mock_web_server,
        max_pages=10,
        max_depth=0,
        allow_loopback=True,
    )
    from app.models import generate_uuid
    scan_id = generate_uuid()

    result = await crawler.crawl(scan_id=scan_id)
    assert result["success"] is True
    assert result["pages_crawled"] == 1


# ----------------------------------------------------
# 5. API Endpoints Tests
# ----------------------------------------------------

def test_api_inspect_url_rejected_security():
    """Verify API rejects live URL scan when live scan is disabled and domain unauthorized."""
    payload = {"url": "https://unauthorized-evil-domain.com"}
    response = client.post("/api/websites/inspect-url", json=payload)
    assert response.status_code == 400
    assert "Security restriction" in response.json()["detail"]


def test_api_inspect_url_and_query_results(mock_web_server):
    """Verify API POST /inspect-url, GET /scans/{id}, and GET /scans/{id}/results."""
    payload = {
        "url": mock_web_server,
        "max_pages": 4,
        "max_depth": 2,
        "allow_loopback": True,
        "background": False,
    }
    post_resp = client.post("/api/websites/inspect-url", json=payload)
    assert post_resp.status_code == 200
    data = post_resp.json()
    assert data["success"] is True
    scan_id = data["scan_id"]
    assert data["captcha_detected"] is True

    # 1. Query Scan Status
    status_resp = client.get(f"/api/websites/scans/{scan_id}")
    assert status_resp.status_code == 200
    scan_info = status_resp.json()["scan"]
    assert scan_info["scan_id"] == scan_id
    assert scan_info["status"] == "completed"
    assert scan_info["pages_crawled"] >= 3

    # 2. Query Scan Results
    results_resp = client.get(f"/api/websites/scans/{scan_id}/results")
    assert results_resp.status_code == 200
    results_data = results_resp.json()
    assert results_data["scan_id"] == scan_id
    assert len(results_data["results"]) >= 3
    assert any(p["classification"] == "contact_page" for p in results_data["results"])


def test_api_scans_not_found():
    response = client.get("/api/websites/scans/non-existent-scan-id-12345")
    assert response.status_code == 404
