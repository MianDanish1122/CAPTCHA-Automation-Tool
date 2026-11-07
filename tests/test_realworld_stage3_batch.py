"""Stage 3 (real-world QA): CSV importer, expected-vs-detected logic, robots policy, shared batch pipeline."""
import asyncio
import http.server
import json
import threading
import time
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.config import settings
from app.database import SessionLocal
from app.models import HumanReviewRecord, WebsiteInspection
from app.services import batch_processor
from app.services.csv_importer import import_websites, normalise_expected_captcha, normalise_header
from app.services.evaluation import categorise, summarise
from app.services.robots_check import evaluate_robots

ROOT = Path(__file__).resolve().parent.parent
EMPLOYER_CSV = ROOT / "USA_Ecommerce_Platforms_200_Contact_Pages.csv"


# ------------------------------------------------------------------ importer
@pytest.mark.skipif(not EMPLOYER_CSV.exists(), reason="employer CSV not present in this checkout")
def test_employer_csv_imports_every_row_and_preserves_every_column():
    r = import_websites(EMPLOYER_CSV.read_bytes())
    assert r["success"] and r["invalid_rows"] == 0 and len(r["websites"]) == 200
    assert r["columns"] == ["Company", "Website", "City", "State", "Category", "Platform", "Captcha", "Contact Page"]
    assert r["unmapped_columns"] == []
    first = r["websites"][0]
    src = json.loads(first["source_row"])
    assert list(src.keys()) == r["columns"]                      # original headers, original order, nothing dropped
    assert src["Company"] == first["company_name"] and src["Contact Page"] == first["expected_contact_page"]
    assert first["platform"] and first["city"] and first["state"] and first["category"]
    assert all(w["expected_contact_page"] and w["expected_captcha"] for w in r["websites"])
    assert not r["warnings"]


def test_header_variants_and_unmapped_columns_are_kept():
    csv = ("Company Name,WEBSITE,Contact-Page,Captcha,Notes\n"
           "Acme,https://acme.example,https://acme.example/contact,invisible reCAPTCHA,keep me\n").encode()
    r = import_websites(csv)
    row = r["websites"][0]
    assert row["expected_captcha"] == "recaptcha_invisible" and row["expected_contact_page"] == "https://acme.example/contact"
    assert r["unmapped_columns"] == ["Notes"]
    assert json.loads(row["source_row"])["Notes"] == "keep me"


def test_invalid_rows_are_reported_with_row_numbers_and_valid_rows_continue():
    csv = ("Company,Website,Captcha,Contact Page\n"
           "A,https://a.example,none,https://a.example/c\n"
           ",https://b.example,none,\n"
           "C,not-a-url,none,\n"
           "D,https://user:pw@d.example,none,\n"
           "E,https://e.example,weird thing,javascript:alert(1)\n").encode()
    r = import_websites(csv)
    assert [e["row"] for e in r["errors"]] == [3, 4, 5]
    assert len(r["websites"]) == 2
    e = r["websites"][1]
    assert e["expected_contact_page"] is None and e["expected_captcha"] == "unrecognised"
    reasons = " ".join(w["reason"] for w in r["warnings"])
    assert "Contact Page" in reasons and "not recognised" in reasons


def test_missing_required_columns_and_encoding_errors_still_rejected():
    assert not import_websites(b"Foo,Bar\n1,2\n")["success"]
    assert not import_websites("Company,Website\nA,https://a.example\n".encode("utf-16"))["success"]


def test_overflow_cells_are_preserved_not_dropped():
    r = import_websites(b"Company,Website\nA,https://a.example,extra1,extra2\n")
    assert json.loads(r["websites"][0]["source_row"])["_extra"] == ["extra1", "extra2"]


@pytest.mark.parametrize("raw,expected", [
    ("reCAPTCHA", "recaptcha"), ("invisible reCAPTCHA", "recaptcha_invisible"), ("reCAPTCHA v2", "recaptcha_v2"),
    ("reCAPTCHA v3", "recaptcha_v3"), ("hCaptcha", "hcaptcha"), ("Cloudflare Turnstile", "turnstile"),
    ("none", "none"), ("None", "none"), ("N/A", "none"), ("", None), ("  ", None), ("some novel thing", "unrecognised"),
])
def test_expected_captcha_normalisation(raw, expected):
    assert normalise_expected_captcha(raw) == expected


def test_normalise_header():
    assert normalise_header(" Contact Page ") == "contact_page" and normalise_header("Contact-Page") == "contact_page"


# ------------------------------------------------------------------ evaluation logic
@pytest.mark.parametrize("expected,providers,status,cat", [
    ("recaptcha", ["google_recaptcha"], "captcha_detected", "match"),
    ("recaptcha_invisible", ["google_recaptcha"], "captcha_detected", "match"),
    ("hcaptcha", ["hcaptcha"], "captcha_detected", "match"),
    ("turnstile", ["cloudflare_turnstile"], "captcha_detected", "match"),
    ("none", [], "no_known_captcha_detected", "match"),
    ("none", ["google_recaptcha"], "captcha_detected", "mismatch"),
    ("recaptcha", ["hcaptcha"], "captcha_detected", "mismatch"),
    ("recaptcha", [], "no_known_captcha_detected", "not_detected"),
    ("hcaptcha", [], "completed", "not_detected"),
    ("recaptcha", [], "failed", "not_accessible"),
    ("recaptcha", [], "blocked_by_robots", "not_accessible"),
    ("recaptcha", [], "blocked_by_challenge", "not_accessible"),
    ("recaptcha", [], "unsupported_challenge", "not_accessible"),
    (None, ["google_recaptcha"], "captcha_detected", "not_verified"),
    ("unrecognised", [], "no_known_captcha_detected", "not_verified"),
])
def test_categorise(expected, providers, status, cat):
    assert categorise(expected, providers, status)["category"] == cat


def test_subtype_agreement_is_informational_only():
    a = categorise("recaptcha_invisible", ["google_recaptcha"], "captcha_detected", subtype="invisible")
    b = categorise("recaptcha_invisible", ["google_recaptcha"], "captcha_detected", subtype="v2_checkbox")
    assert a["category"] == b["category"] == "match"
    assert a["subtype_agreement"] == "agree" and b["subtype_agreement"] == "differs"


def test_accessible_false_forces_not_accessible():
    assert categorise("none", [], "completed", accessible=False)["category"] == "not_accessible"


def test_summary_counts_only_eligible_records_and_states_sample_size():
    rows = [{"result_category": c} for c in
            ["match", "match", "mismatch", "not_detected", "not_accessible", "not_accessible", "not_verified"]]
    s = summarise(rows)
    assert s["eligible_records"] == 4 and s["counts"]["not_accessible"] == 2
    assert s["agreement_pct"] == 50.0                               # 2 / 4, NOT 2 / 7
    assert "4 eligible" in s["sample_size_note"] and "too small" in s["sample_size_note"]
    assert summarise([])["agreement_pct"] is None


# ------------------------------------------------------------------ robots policy
UA = "CaptchaInspector/1.0"


@pytest.mark.parametrize("status,body,headers,proceed,label", [
    (200, "User-agent: *\nDisallow:\n", {}, True, "allowed"),
    (200, "", {}, True, "allowed"),                                    # empty file = no restriction
    (200, "User-agent: *\nDisallow: /contact", {}, False, "disallowed"),
    (200, "User-agent: *\nDisallow: /private\n", {}, True, "allowed"),
    (404, "", {}, True, "unavailable"),
    (410, "", {}, True, "unavailable"),
    (403, "<title>Just a moment...</title>", {"cf-mitigated": "challenge"}, False, "blocked_by_challenge"),
    (403, "Forbidden", {}, False, "access_restricted"),
    (401, "", {}, False, "access_restricted"),
    (429, "", {}, False, "access_restricted"),
    (500, "", {}, False, "error"),
    (503, "", {}, False, "error"),
    (None, "", {}, False, "error"),
])
def test_robots_policy(status, body, headers, proceed, label):
    r = evaluate_robots(status, body, headers, UA, "https://site.example/contact-us/")
    assert r["proceed"] is proceed and r["robots_status"] == label


def test_robots_agent_specific_rule():
    body = "User-agent: CaptchaInspector\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
    assert not evaluate_robots(200, body, {}, UA, "https://s.example/x")["proceed"]
    assert evaluate_robots(200, body, {}, "OtherBot/1", "https://s.example/x")["proceed"]


# ------------------------------------------------------------------ per-host pacing
@pytest.mark.anyio
async def test_host_pacing_spaces_requests_to_the_same_external_host_only():
    batch_processor._host_next_allowed.clear()
    t0 = time.monotonic()
    w1 = await batch_processor.wait_for_host_slot("https://pace.example/a", interval=0.4)
    w2 = await batch_processor.wait_for_host_slot("https://pace.example/b", interval=0.4)
    w3 = await batch_processor.wait_for_host_slot("https://other.example/", interval=0.4)
    assert w1 == 0 and w3 == 0 and 0.3 <= w2 <= 0.6
    assert time.monotonic() - t0 >= 0.35
    assert await batch_processor.wait_for_host_slot("http://127.0.0.1:9/", interval=5) == 0   # loopback exempt


# ------------------------------------------------------------------ migration
def test_migration_is_additive_idempotent_and_matches_model():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "m8", ROOT / "alembic" / "versions" / "8a01realworldqa_realworld_inspection_columns.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "7a01phase7evaluation"

    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE website_inspections (id VARCHAR(36) PRIMARY KEY, company_name TEXT)"))
        conn.execute(sa.text("CREATE TABLE human_reviews (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO website_inspections VALUES ('x','keep me')"))
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
            mod.upgrade()                                               # idempotent
        cols = {c["name"] for c in sa.inspect(conn).get_columns("website_inspections")}
        assert {n for n, _ in mod.INSPECTION_COLUMNS} <= cols
        assert "inspection_id" in {c["name"] for c in sa.inspect(conn).get_columns("human_reviews")}
        assert conn.execute(sa.text("SELECT company_name FROM website_inspections")).scalar() == "keep me"

    model_cols = set(WebsiteInspection.__table__.columns.keys())
    assert {n for n, _ in mod.INSPECTION_COLUMNS} <= model_cols


def test_downgrade_is_guarded(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m8b", ROOT / "alembic" / "versions" / "8a01realworldqa_realworld_inspection_columns.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError):
        mod.downgrade()


# ------------------------------------------------------------------ batch pipeline against a local site
CONTACT_RC = b"""<html><head><title>Contact us</title></head><body><form method=post action=/x>
<input name=email><textarea name=msg></textarea><div id=slot></div></form>
<script>setTimeout(function(){var d=document.createElement('div');d.className='g-recaptcha';
d.setAttribute('data-sitekey','K');document.getElementById('slot').appendChild(d);
var s=document.createElement('script');s.src='https://www.google.com/recaptcha/api.js';document.head.appendChild(s);},800);</script>
</body></html>"""
CONTACT_PLAIN = b"""<html><head><title>Write to us</title></head><body><form method=post action=/x>
<input name=email><textarea name=msg></textarea></form></body></html>"""
LANDING = b"<html><head><title>Home</title></head><body><a href='/contact'>Contact</a></body></html>"


class _Site(http.server.BaseHTTPRequestHandler):
    robots = ""
    hits: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        _Site.hits.append(path)
        pages = {"/": LANDING, "/contact": CONTACT_PLAIN, "/contact-us": CONTACT_RC, "/rc/contact": CONTACT_RC,
                 "/plain/contact": CONTACT_PLAIN}
        if path == "/robots.txt":
            body, code = _Site.robots.encode(), (200 if _Site.robots else 404)
        elif path in pages:
            body, code = pages[path], 200
        else:
            body, code = b"nope", 404
        self.send_response(code)
        self.send_header("Content-Type", "text/plain" if path == "/robots.txt" else "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def site():
    _Site.robots, _Site.hits = "", []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _run_rows(monkeypatch, rows, tmp_path):
    """Create a batch from importer-shaped rows and process every record through the real pipeline."""
    real = batch_processor.inspect_website

    async def loopback_ok(url, **kw):                                   # tests only: allow the local server
        kw.setdefault("allow_loopback", True)
        return await real(url, **kw)

    monkeypatch.setattr(batch_processor, "inspect_website", loopback_ok)
    monkeypatch.setattr(settings, "EVIDENCE_DIR", tmp_path / "evidence")   # keep test screenshots out of the repo
    monkeypatch.setattr(settings, "SCANS_EVIDENCE_DIR", tmp_path / "evidence" / "scans")
    monkeypatch.setattr(settings, "DETECTION_SETTLE_MS", 1500)
    monkeypatch.setattr(settings, "DETECTION_EVIDENCE_WAIT_MS", 3500)
    batch_id = batch_processor.create_batch(rows, start_background=False)
    db = SessionLocal()
    try:
        ids = [i.id for i in db.query(WebsiteInspection).filter_by(batch_id=batch_id)
               .order_by(WebsiteInspection.created_at, WebsiteInspection.company_name).all()]
    finally:
        db.close()

    async def go():
        sem = asyncio.Semaphore(1)
        for i in ids:
            await batch_processor.process_single_website(i, sem)

    asyncio.run(go())
    db = SessionLocal()
    try:
        recs = {r.company_name: r for r in db.query(WebsiteInspection).filter_by(batch_id=batch_id).all()}
        reviews = db.query(HumanReviewRecord).filter(HumanReviewRecord.inspection_id.in_(ids)).all()
        for r in recs.values():
            db.expunge(r)
        for r in reviews:
            db.expunge(r)
    finally:
        db.close()
    return batch_id, recs, reviews


def _row(name, url, **kw):
    return {"company_name": name, "website_url": url, "status": "pending",
            "source_row": json.dumps({"Company": name, "Website": url}), **kw}


def test_batch_pipeline_end_to_end_with_shared_engine(site, monkeypatch, tmp_path):
    rows = [
        _row("RC Shop", site + "/", expected_captcha="recaptcha", expected_captcha_raw="reCAPTCHA",
             expected_contact_page=site + "/contact-us", platform="BigCommerce", city="Austin", state="TX"),
        _row("Plain Shop", site + "/", expected_captcha="none", expected_captcha_raw="none",
             expected_contact_page=site + "/plain/contact"),
        _row("Wrong Expectation", site + "/", expected_captcha="hcaptcha", expected_contact_page=site + "/contact-us"),
        _row("Missed Shop", site + "/", expected_captcha="recaptcha", expected_contact_page=site + "/plain/contact"),
        _row("No Expectation", site + "/", expected_contact_page=site + "/contact-us"),
        _row("Dead Contact Falls Back", site + "/", expected_captcha="none", expected_contact_page=site + "/gone"),
    ]
    batch_id, recs, reviews = _run_rows(monkeypatch, rows, tmp_path)

    rc = recs["RC Shop"]
    assert rc.result_category == "match" and "google_recaptcha" in rc.captcha_provider
    assert rc.contact_page_url.endswith("/contact-us")                  # the CSV contact page was used
    assert json.loads(rc.evidence)["contact_source"] == "csv"
    assert rc.platform == "BigCommerce" and rc.city == "Austin" and json.loads(rc.source_row)["Company"] == "RC Shop"
    assert rc.robots_status == "unavailable"                             # local server has no robots.txt
    assert rc.captcha_subtype and rc.widget_state
    shot = tmp_path / rc.screenshot_path
    assert shot.exists() and shot.stat().st_size > 1000                  # genuine screenshot evidence on disk

    assert recs["Plain Shop"].result_category == "match" and not recs["Plain Shop"].captcha_detected
    assert recs["Wrong Expectation"].result_category == "mismatch"
    assert recs["Missed Shop"].result_category == "not_detected"
    assert recs["No Expectation"].result_category == "not_verified"
    dead = recs["Dead Contact Falls Back"]                               # /gone is a 404 -> landing + discovery
    assert dead.result_category == "match" and json.loads(dead.evidence)["contact_source"] == "discovered"
    assert json.loads(dead.evidence)["csv_contact_page_http_status"] == 404

    # human-review records exist for every inspected CAPTCHA site, and only for those
    by_url = {r.page_url for r in reviews}
    assert len(reviews) == 3 and all(r.review_status == "pending" for r in reviews)
    assert all(r.page_url.endswith("/contact-us") for r in reviews)

    db = SessionLocal()
    try:
        from app.models import BatchJob
        b = db.query(BatchJob).filter_by(id=batch_id).one()
        assert b.processed_records == 6 and b.successful_records + b.failed_records == 6
    finally:
        db.close()


def test_robots_disallow_stops_inspection_and_is_reported_not_accessible(site, monkeypatch, tmp_path):
    _Site.robots = "User-agent: *\nDisallow: /contact-us\n"
    rows = [_row("Blocked Shop", site + "/", expected_captcha="recaptcha", expected_contact_page=site + "/contact-us")]
    _, recs, reviews = _run_rows(monkeypatch, rows, tmp_path)
    r = recs["Blocked Shop"]
    assert r.scan_status == "blocked_by_robots" and r.robots_status == "disallowed"
    assert r.result_category == "not_accessible" and "robots.txt" in r.error_details
    assert "/contact-us" not in _Site.hits                               # the disallowed page was NEVER requested
    assert reviews == []


def test_one_failure_does_not_stop_the_batch(site, monkeypatch, tmp_path):
    rows = [_row("Unreachable", "http://127.0.0.1:9/", expected_captcha="none"),
            _row("Fine", site + "/", expected_captcha="none", expected_contact_page=site + "/plain/contact")]
    _, recs, _ = _run_rows(monkeypatch, rows, tmp_path)
    assert recs["Unreachable"].result_category == "not_accessible" and recs["Unreachable"].error_details
    assert recs["Fine"].result_category == "match"
