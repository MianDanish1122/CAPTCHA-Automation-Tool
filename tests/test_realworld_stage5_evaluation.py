"""Stage 5 (real-world QA): CSV formula-injection protection, evaluation report/API."""
import csv
import io
import json
import uuid

import pytest
from starlette.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import BatchJob, WebsiteInspection
from app.services.report_generator import (
    build_evaluation, csv_safe, evaluation_csv, evaluation_markdown, generate_batch_csv_report,
)

EVIL = ["=1+1", "+SUM(A1:A2)", "-2+3", "@SUM(1)", "=HYPERLINK(\"http://evil.example\",\"x\")",
        "\t=cmd|' /C calc'!A0", "\r=1", "  =1+1", "=cmd|' /C calc'!A0"]


@pytest.mark.parametrize("value", EVIL)
def test_formula_prefixes_are_neutralised_and_content_preserved(value):
    out = csv_safe(value)
    assert out == "'" + value and out.endswith(value)


@pytest.mark.parametrize("value", ["Acme Inc", "https://a.example", "0.50", "", None, 12, "a=b", "x-y", "O'Brien"])
def test_ordinary_values_are_unchanged(value):
    assert csv_safe(value) == value


def _insp(**kw):
    base = dict(batch_id="b", company_name="Co", website_url="https://co.example", scan_status="captcha_detected",
                contact_form_found=True, captcha_detected=True, captcha_provider="google_recaptcha",
                human_review_required=True, inspection_duration_ms=12.0)
    base.update(kw)
    return WebsiteInspection(**base)


def test_batch_csv_report_has_no_live_formula_cells():
    items = [_insp(company_name=v, website_url="https://x.example/?q=" + v, error_details=v, page_title=v,
                   contact_page_url=v, platform=v, city=v, state=v, category=v) for v in EVIL]
    text, _ = generate_batch_csv_report(items, save_to_file=False)
    for row in csv.reader(io.StringIO(text)):
        for cell in row:
            assert not cell.lstrip(" ").startswith(("=", "+", "-", "@", "\t", "\r")), cell
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["Company Name"] == "'=1+1"                               # visible, inert, not lost
    assert rows[1]["Error Details"] == "'+SUM(A1:A2)"


def test_existing_report_columns_are_unchanged_and_new_ones_appended():
    text, _ = generate_batch_csv_report([_insp()], save_to_file=False)
    header = next(csv.reader(io.StringIO(text)))
    assert header[:11] == ["Company Name", "Website URL", "Website Status", "Contact Page Found", "CAPTCHA Detected",
                           "CAPTCHA Provider", "Inspection Status", "Human Review Required", "Error Details",
                           "Scan Timestamp", "Processing Duration (ms)"]
    assert {"Expected CAPTCHA", "Result Category", "Widget Loaded", "Contact Page URL"} <= set(header)


def test_evaluation_rows_and_eligible_only_metrics():
    items = [
        _insp(company_name="A", expected_captcha="recaptcha", expected_captcha_raw="reCAPTCHA", result_category="match",
              widget_loaded=True, contact_page_url="https://a.example/c"),
        _insp(company_name="B", expected_captcha="none", captcha_provider=None, captcha_detected=False,
              scan_status="no_known_captcha_detected", result_category="match"),
        _insp(company_name="C", expected_captcha="hcaptcha", result_category="mismatch"),
        _insp(company_name="D", expected_captcha="recaptcha", captcha_provider=None, scan_status="failed",
              result_category="not_accessible", error_details="HTTP 403"),
        _insp(company_name="E", expected_captcha=None, result_category="not_verified"),
    ]
    ev = build_evaluation(items)
    s = ev["summary"]
    assert s["total_records"] == 5 and s["eligible_records"] == 3 and s["agreement_pct"] == 66.7
    assert s["counts"]["not_accessible"] == 1 and s["counts"]["not_verified"] == 1
    assert "3 eligible" in s["sample_size_note"]
    first = ev["rows"][0]
    assert set(["website", "expected", "detected", "contact_page", "widget_loaded", "result"]) <= set(first)
    assert first["result"] == "Match" and first["expected"] == "reCAPTCHA" and first["widget_loaded"] is True

    md = evaluation_markdown(ev)
    assert "| Website | Expected | Detected | Contact page | Widget loaded | Result |" in md
    assert "Not accessible" in md and "excluded from the percentage" in md
    assert csv.reader(io.StringIO(evaluation_csv(ev))).__next__()[:6] == [
        "Website", "Expected", "Detected", "Contact Page", "Widget Loaded", "Result"]


def test_evaluation_csv_is_formula_safe():
    ev = build_evaluation([_insp(company_name="=cmd|' /C calc'!A0", expected_captcha="none", result_category="mismatch")])
    for row in csv.reader(io.StringIO(evaluation_csv(ev))):
        assert not row[0].startswith("=")
    ev2 = build_evaluation([_insp(company_name="x", website_url="y", contact_page_url="=1+1", error_details="@x")])
    assert "'=1+1" in evaluation_csv(ev2)


# ------------------------------------------------------------------ API
@pytest.fixture
def batch():
    db = SessionLocal()
    b = BatchJob(total_records=2, processed_records=2, successful_records=2, status="completed")
    db.add(b)
    db.flush()
    db.add(WebsiteInspection(batch_id=b.id, company_name="=EVIL()", website_url="https://one.example", scan_status="captcha_detected",
                             captcha_detected=True, captcha_provider="google_recaptcha", expected_captcha="recaptcha",
                             expected_captcha_raw="reCAPTCHA", result_category="match", widget_loaded=True))
    db.add(WebsiteInspection(batch_id=b.id, company_name="Two", website_url="https://two.example", scan_status="failed",
                             expected_captcha="none", result_category="not_accessible", error_details="HTTP 403"))
    db.commit()
    bid = b.id
    db.close()
    return bid


def test_evaluation_endpoint_and_downloads(batch):
    c = TestClient(app)
    r = c.get(f"/api/websites/batches/{batch}/evaluation")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["eligible_records"] == 1 and body["summary"]["counts"]["not_accessible"] == 1
    assert {x["result"] for x in body["rows"]} == {"Match", "Not accessible"}

    csv_r = c.get(f"/api/websites/batches/{batch}/evaluation.csv")
    assert csv_r.status_code == 200 and csv_r.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_r.headers["content-disposition"]
    assert "=EVIL()" not in [row[0] for row in csv.reader(io.StringIO(csv_r.text))]
    md_r = c.get(f"/api/websites/batches/{batch}/evaluation.md")
    assert md_r.status_code == 200 and "Expected vs detected" in md_r.text
    assert c.get(f"/api/websites/batches/{batch}/evaluation.exe").status_code == 404


def test_evaluation_endpoint_unknown_batch_and_auth(batch):
    c = TestClient(app)
    assert c.get(f"/api/websites/batches/{uuid.uuid4()}/evaluation").status_code == 404
    anon = TestClient(app)
    anon._unauthenticated = True
    assert anon.get(f"/api/websites/batches/{batch}/evaluation").status_code in (401, 403)


def test_manual_batch_launch_keeps_csv_context_and_normalises_server_side():
    c = TestClient(app)
    payload = {"websites": [{
        "company_name": "Ctx Co", "website_url": "https://ctx.example", "expected_captcha_raw": "invisible reCAPTCHA",
        "expected_captcha": "hcaptcha",                                       # client-supplied label must be ignored
        "expected_contact_page": "https://ctx.example/contact", "platform": "Shopify", "city": "Reno", "state": "NV",
        "category": "Home", "source_row": json.dumps({"Company": "Ctx Co", "Extra": "kept"})},
        {"company_name": "Bad Ctx", "website_url": "https://bad.example", "expected_contact_page": "javascript:alert(1)",
         "source_row": "not json"}]}
    r = c.post("/api/websites/scan-batch?background=false", json=payload)
    assert r.status_code == 200, r.text
    bid = r.json()["batch_id"]
    db = SessionLocal()
    try:
        rows = {i.company_name: i for i in db.query(WebsiteInspection).filter_by(batch_id=bid).all()}
        ctx, bad = rows["Ctx Co"], rows["Bad Ctx"]
        assert ctx.expected_captcha == "recaptcha_invisible" and ctx.expected_contact_page == "https://ctx.example/contact"
        assert ctx.platform == "Shopify" and json.loads(ctx.source_row)["Extra"] == "kept"
        assert bad.expected_contact_page is None and bad.source_row is None
    finally:
        db.close()


def test_batch_results_api_exposes_new_fields_without_local_paths(batch):
    c = TestClient(app)
    res = c.get(f"/api/websites/batches/{batch}/results").json()["results"][0]
    assert {"expected_captcha", "result_category", "widget_loaded", "robots_status"} <= set(res)
    assert ":\\" not in json.dumps(res) and "/Users/" not in json.dumps(res)
