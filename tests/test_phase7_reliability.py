"""
Phase 7 reliability / error-handling tests (each row of docs/PHASE_7_RELIABILITY_REPORT.md).
All failures must be REPORTED (structured result or safe HTTP error), never crash a worker,
leak internals, or leave a scan stuck in "crawling".
"""
import asyncio
import http.server
import socket
import threading
import time
import uuid

import pytest
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient

from app.config import settings
from app.database import SessionLocal, get_db
from app.main import app
from app.models import UrlScan, UserRole
from app.services import browser_scanner
from app.services.auth_service import create_access_token
from app.services.browser_scanner import inspect_local_demo, inspect_website
from app.services.job_manager import JobManager
from app.services.smart_crawler import SmartCrawler


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Slow(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        time.sleep(4)
        try:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception:
            pass


@pytest.fixture
def slow_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


async def _boom():
    raise RuntimeError("Executable doesn't exist at C:\\fake\\chromium.exe")


# ------------------------------------------------------------------ R1 browser launch failure
@pytest.mark.anyio
async def test_browser_launch_failure_reported_by_single_page_scan(monkeypatch):
    monkeypatch.setattr(browser_scanner, "get_shared_browser", _boom)
    r = await inspect_website(f"http://127.0.0.1:{_closed_port()}/", allow_loopback=True)
    assert r["success"] is False and r["detection_method"] == "browser_unavailable"
    assert "RuntimeError" in r["error"] and "chromium.exe" not in r["error"]  # type only, no path leak


@pytest.mark.anyio
async def test_browser_launch_failure_reported_by_demo_inspection(monkeypatch):
    monkeypatch.setattr(browser_scanner, "get_shared_browser", _boom)
    r = await inspect_local_demo("<form></form>")
    assert r["success"] is False and r["status"] == "inspection_failed"


@pytest.mark.anyio
async def test_browser_launch_failure_marks_crawl_failed_not_stuck(monkeypatch):
    import app.services.smart_crawler as sc
    monkeypatch.setattr(sc, "get_shared_browser", _boom)
    scan_id = str(uuid.uuid4())
    res = await SmartCrawler(f"http://127.0.0.1:{_closed_port()}/", allow_loopback=True).crawl(scan_id=scan_id)
    assert res["success"] is False and "Browser could not be started" in res["error"]
    db = SessionLocal()
    try:
        scan = db.query(UrlScan).filter_by(id=scan_id).one()
        assert scan.status == "failed" and scan.completed_at is not None
    finally:
        db.close()


def test_api_returns_failure_not_500_when_browser_cannot_start(monkeypatch):
    import app.services.smart_crawler as sc
    monkeypatch.setattr(sc, "get_shared_browser", _boom)
    c = TestClient(app, raise_server_exceptions=False)
    c.headers["Authorization"] = "Bearer " + create_access_token("test-operator-id", "test_operator", UserRole.OPERATOR)
    res = c.post("/api/websites/inspect-url", json={"url": f"http://127.0.0.1:{_closed_port()}/", "allow_loopback": True})
    assert res.status_code == 200 and res.json()["success"] is False


# ------------------------------------------------------------------ R2 navigation timeout, R3 unreachable
@pytest.mark.anyio
async def test_navigation_timeout_is_reported(slow_server, monkeypatch):
    await inspect_local_demo("<p>warm-up: start the shared browser before timing</p>")
    monkeypatch.setattr(settings, "REQUEST_TIMEOUT_MS", 800)
    t0 = time.perf_counter()
    r = await inspect_website(slow_server + "/", allow_loopback=True)
    assert r["success"] is False and time.perf_counter() - t0 < 3.9
    assert "Navigation error" in r["error"]


@pytest.mark.anyio
async def test_unreachable_host_is_reported():
    r = await inspect_website(f"http://127.0.0.1:{_closed_port()}/", allow_loopback=True)
    assert r["success"] is False and r["scan_status"] == "failed"


@pytest.mark.anyio
async def test_crawler_on_unreachable_host_completes_with_a_terminal_status():
    scan_id = str(uuid.uuid4())
    res = await SmartCrawler(f"http://127.0.0.1:{_closed_port()}/", max_pages=1, allow_loopback=True).crawl(scan_id=scan_id)
    db = SessionLocal()
    try:
        status = db.query(UrlScan).filter_by(id=scan_id).one().status
    finally:
        db.close()
    assert status in ("completed", "failed") and status != "crawling"
    assert res["pages_crawled"] == 0 or not res["success"] or res["status"] == "completed"


# ------------------------------------------------------------------ R4 policy violations (covered in depth by 6A tests)
@pytest.mark.anyio
@pytest.mark.parametrize("url", ["http://10.0.0.1/", "http://169.254.169.254/latest/", "http://100.64.0.1/",
                                 "ftp://example.com/", "http://example.com:22/"])
async def test_policy_violations_rejected_before_any_network_use(url):
    r = await inspect_website(url)
    assert r["success"] is False and "Security restriction" in r["error"]


# ------------------------------------------------------------------ R5 unsupported CAPTCHA types
def test_unsupported_challenges_are_routed_to_human_review_not_solved():
    c = TestClient(app)
    html = "<title>Just a moment...</title><div id='cf-challenge-running'></div>"
    body = c.post("/api/captcha/classify", json={"html": html}).json()
    assert body["classification"] == "unknown_challenge" and body["human_review_required"] is True
    assert body["handling_strategy"] == "manual_investigation"


def test_unknown_markup_without_provider_is_no_captcha_not_a_guess():
    body = TestClient(app).post("/api/captcha/classify", json={"html": "<div class='weird-widget'></div>"}).json()
    assert body["classification"] == "no_captcha" and body["human_review_required"] is False


# ------------------------------------------------------------------ R7 job limits and cancellation
@pytest.mark.anyio
async def test_cancelled_crawl_does_not_leave_scan_in_crawling_state(slow_server, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS", 2)
    jm = JobManager()
    scan_id = str(uuid.uuid4())
    crawler = SmartCrawler(slow_server + "/", max_pages=1, allow_loopback=True)
    task = jm.spawn("crawl", "cancel-user", crawler.crawl(scan_id=scan_id))
    await asyncio.sleep(1.5)  # crawl is now waiting on the slow server
    await jm.shutdown()
    assert task.cancelled() or task.done()
    assert jm.active("crawl") == 0
    db = SessionLocal()
    try:
        scan = db.query(UrlScan).filter_by(id=scan_id).first()
        assert scan is None or scan.status != "crawling"
    finally:
        db.close()


# ------------------------------------------------------------------ R8 database errors
def test_database_failure_returns_503_without_leaking_internals():
    class BrokenSession:
        def __getattr__(self, name):
            def boom(*a, **k):
                raise OperationalError("SELECT secret FROM users", {}, Exception("database is locked at C:\\data\\x.db"))
            return boom

        def close(self):
            pass

    def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    try:
        c = TestClient(app, raise_server_exceptions=False)
        c.headers["Authorization"] = "Bearer " + create_access_token("test-operator-id", "test_operator", UserRole.OPERATOR)
        res = c.get("/api/websites/scans")
        assert res.status_code == 503
        text = res.text
        assert "SELECT" not in text and "C:\\" not in text and "locked" not in text
        assert res.headers.get("retry-after")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_unhandled_exception_returns_generic_500(monkeypatch):
    import app.routes.websites as w

    async def explode(*a, **k):
        raise ZeroDivisionError("internal detail /secret/path")

    monkeypatch.setattr(w, "inspect_local_demo", explode)
    c = TestClient(app, raise_server_exceptions=False)
    c.headers["Authorization"] = "Bearer " + create_access_token("test-operator-id", "test_operator", UserRole.OPERATOR)
    res = c.post("/api/websites/inspect-demo", json={"html": "<p>x</p>"})
    assert res.status_code == 500 and res.json() == {"detail": "Internal server error."}


# ------------------------------------------------------------------ R9 authentication / authorization failures
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"},
                                     {"Authorization": "Bearer "}])
def test_protected_endpoints_reject_bad_credentials(headers):
    c = TestClient(app)
    c._unauthenticated = True
    for method, url in (("get", "/api/stats/summary"), ("get", "/api/captcha/reviews"),
                        ("post", "/api/captcha/verify-token"), ("get", "/api/stats/report")):
        res = getattr(c, method)(url, headers=headers)
        assert res.status_code in (401, 403, 422), (url, res.status_code)
        if res.status_code != 422:
            assert res.status_code == 401


def test_operator_cannot_reach_admin_endpoints():
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + create_access_token("test-operator-id", "test_operator", UserRole.OPERATOR)
    assert c.get("/api/auth/audit-logs").status_code == 403


# ------------------------------------------------------------------ stats endpoint honesty
def test_stats_summary_structure_denominators_and_no_placeholders():
    c = TestClient(app)
    body = c.get("/api/stats/summary").json()
    for section in ("inspections", "pages", "captcha_types", "ocr", "verification", "failures", "human_review"):
        assert "denominator" in body[section], section
    assert body["time_range"]["all_time"] is True
    ranged = c.get("/api/stats/summary?days=7").json()
    assert ranged["time_range"]["days"] == 7 and ranged["time_range"]["all_time"] is False
    assert c.get("/api/stats/summary?days=0").status_code == 422


def test_stats_counts_match_database_rows():
    from app.models import DiscoveredPage, HumanReviewRecord, OcrEvaluationRecord, VerificationRecord
    c = TestClient(app)
    body = c.get("/api/stats/summary").json()
    db = SessionLocal()
    try:
        assert body["pages"]["pages_inspected"] == db.query(DiscoveredPage).count()
        assert body["inspections"]["url_scans_total"] == db.query(UrlScan).count()
        legacy = db.query(OcrEvaluationRecord).filter_by(ground_truth="SYNTHETIC").count()
        assert body["ocr"]["evaluations"] == db.query(OcrEvaluationRecord).count() - legacy
        assert body["ocr"]["excluded_legacy_unlabelled_records"] == legacy
        assert body["verification"]["attempts"] == db.query(VerificationRecord).count()
        assert body["human_review"]["cases"] == db.query(HumanReviewRecord).count()
    finally:
        db.close()


def test_stats_with_empty_database_yields_zeros_not_mock_values(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.routes.stats import build_summary
    eng = create_engine(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    try:
        s = build_summary(db)
    finally:
        db.close()
    assert s["has_data"] is False
    assert s["pages"]["pages_inspected"] == 0 and s["pages"]["pages_with_captcha_pct"] is None
    assert s["ocr"]["exact_match_pct"] is None and s["ocr"]["heldout_benchmarks"]["by_engine"] == {}
    assert s["verification"]["attempts"] == 0 and s["captcha_types"]["by_provider"] == {}


def test_report_download_is_markdown_attachment_with_denominators():
    c = TestClient(app)
    res = c.get("/api/stats/report")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/markdown")
    assert "attachment" in res.headers["content-disposition"]
    assert "Denominator" in res.text and "# CAPTCHA Inspector - Evaluation Report" in res.text
