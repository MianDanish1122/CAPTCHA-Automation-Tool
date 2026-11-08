"""Defects found while hand-testing the screens: an unreadable page must be a FAILED scan (not 'Completed, no CAPTCHA'),
and the Human Review / Results screens must receive the field names they read."""
import http.server
import threading
import time
import uuid

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import DiscoveredPage, HumanReviewRecord, UrlScan
from app.services.smart_crawler import SmartCrawler


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/slow"):
            time.sleep(5)
        body = (b"<html><head><title>Home</title></head><body><a href='/slow'>Contact us</a>"
                b"<form><input name=a><textarea name=b></textarea></form></body></html>")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass


@pytest.fixture
def site():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.mark.anyio
async def test_page_that_times_out_makes_the_scan_failed_not_completed(site, monkeypatch):
    monkeypatch.setattr(settings, "CRAWLER_PAGE_TIMEOUT_MS", 1000)
    scan_id = str(uuid.uuid4())
    res = await SmartCrawler(site + "/slow", max_pages=1, max_depth=0, allow_loopback=True).crawl(scan_id=scan_id)
    assert res["success"] is False and res["status"] == "failed" and res["pages_crawled"] == 0
    assert "timed out" in res["error"] and "NOT evidence" in res["error"]
    assert res["page_errors"][0]["reason"] == "timed out"
    db = SessionLocal()
    try:
        scan = db.query(UrlScan).filter_by(id=scan_id).one()
        assert scan.status == "failed" and "timed out" in scan.error_message and scan.pages_crawled == 0
        assert db.query(DiscoveredPage).filter_by(scan_id=scan_id).count() == 0
    finally:
        db.close()


@pytest.mark.anyio
async def test_partial_failure_still_completes_but_records_the_unreadable_page(site, monkeypatch):
    monkeypatch.setattr(settings, "CRAWLER_PAGE_TIMEOUT_MS", 1500)
    scan_id = str(uuid.uuid4())
    res = await SmartCrawler(site + "/", max_pages=3, max_depth=1, allow_loopback=True).crawl(scan_id=scan_id)
    assert res["success"] is True and res["status"] == "completed" and len(res["results"]) >= 1
    assert any(e["reason"] == "timed out" for e in res["page_errors"])
    db = SessionLocal()
    try:
        scan = db.query(UrlScan).filter_by(id=scan_id).one()
        assert scan.status == "completed" and "could not be read" in (scan.error_message or "")
    finally:
        db.close()


def test_review_record_exposes_the_field_names_the_screen_reads():
    r = HumanReviewRecord(page_url="https://x.example/contact", captcha_provider="google_recaptcha",
                          challenge_type="v2_checkbox", reason_for_review="needs a person", review_status="pending",
                          operator_notes="n")
    d = r.to_dict()
    assert d["target_url"] == "https://x.example/contact" and d["provider"] == "google_recaptcha"
    assert d["handling_strategy"] == "human_review" and d["reviewer_notes"] == "n"
    assert d["confidence_score"] is None          # honest "unknown", the screen prints "-" (never NaN%)
    assert d["captcha_provider"] == "google_recaptcha" and d["page_url"]   # original keys unchanged


def test_discovered_page_exposes_the_field_names_the_screens_read():
    p = DiscoveredPage(scan_id="s", url="https://x.example/support/contact?x=1", depth=0, classification="contact_page",
                       confidence_score=0.8, forms_count=2, captcha_detected=True, human_review_required=True,
                       http_status=200, page_title="Contact")
    d = p.to_dict()
    assert d["path"] == "/support/contact" and d["title"] == "Contact" and d["status_code"] == 200
    assert d["forms_found_count"] == 2 and d["is_contact_page"] is True and d["contact_confidence"] == 0.8
    assert d["handling_strategy"] == "human_review" and d["captcha_confidence"] is None
    assert d["forms_count"] == 2 and d["url"]                               # original keys unchanged
    clean = DiscoveredPage(scan_id="s", url="https://x.example/", depth=0, classification="other", captcha_detected=False)
    assert clean.to_dict()["handling_strategy"] == "no_challenge" and clean.to_dict()["path"] == "/"


def test_reviews_api_returns_the_aliases():
    db = SessionLocal()
    rec = HumanReviewRecord(page_url="https://alias.example/c", captcha_provider="hcaptcha", challenge_type="checkbox",
                            reason_for_review="r", review_status="pending")
    db.add(rec)
    db.commit()
    rid = rec.id
    db.close()
    c = TestClient(app)
    items = c.get("/api/captcha/reviews?limit=100").json()["reviews"]
    mine = next(i for i in items if i["id"] == rid)
    assert mine["provider"] == "hcaptcha" and mine["target_url"] == "https://alias.example/c"
