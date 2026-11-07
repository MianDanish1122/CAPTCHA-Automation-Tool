import io
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "CAPTCHA Automation Tool" in data["app"]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_api_import_valid_csv():
    csv_content = b"company_name,website_url\nAcme Corp,https://acme.org\nBeta Co,https://beta.org\n"
    response = client.post(
        "/api/websites/import",
        files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_websites"] == 2
    assert data["invalid_rows"] == 0


def test_api_import_invalid_file_extension():
    response = client.post(
        "/api/websites/import",
        files={"file": ("test.txt", io.BytesIO(b"random text"), "text/plain")}
    )
    assert response.status_code == 400
    assert "CSV" in response.json()["detail"]


def test_api_inspect_demo():
    payload = {
        "html": "<html><head><title>Demo Form</title></head><body><form><input name='email'></form></body></html>"
    }
    response = client.post("/api/websites/inspect-demo", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "no_known_captcha_detected"


def test_api_inspect_demo_batch():
    payload = {
        "pages": [
            {
                "company_name": "Test Co 1",
                "html": "<html><head><title>Form 1</title></head><body><form><input name='email'></form></body></html>"
            },
            {
                "company_name": "Test Co 2",
                "html": "<html><head><title>Form 2</title></head><body><div class='g-recaptcha' data-src='google.com/recaptcha'></div></body></html>"
            }
        ]
    }
    response = client.post("/api/websites/inspect-demo-batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["summary"]["total_pages"] == 2
    assert data["summary"]["captcha_detected"] == 1
    assert data["summary"]["no_captcha_detected"] == 1


def test_api_scan_batch_and_report_lifecycle():
    # 1. Create a batch
    payload = {
        "websites": [
            {"company_name": "Fixture Co 1", "website_url": "fixture://normal_contact_form.html"},
            {"company_name": "Fixture Co 2", "website_url": "fixture://google_recaptcha.html"}
        ]
    }
    create_resp = client.post("/api/websites/scan-batch?background=false", json=payload)
    assert create_resp.status_code == 200
    batch_data = create_resp.json()
    assert batch_data["success"] is True
    batch_id = batch_data["batch_id"]

    # 2. Query batch status
    status_resp = client.get(f"/api/websites/batches/{batch_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["batch"]["batch_id"] == batch_id

    # 3. Query results
    results_resp = client.get(f"/api/websites/batches/{batch_id}/results")
    assert results_resp.status_code == 200
    assert len(results_resp.json()["results"]) == 2

    # 4. Download report
    report_resp = client.get(f"/api/websites/batches/{batch_id}/report")
    assert report_resp.status_code == 200
    assert "text/csv" in report_resp.headers["content-type"]
    assert "Company Name" in report_resp.text
    assert "Fixture Co 1" in report_resp.text


def test_api_ocr_demo():
    payload = {"custom_text": "HELO9"}
    resp = client.post("/api/captcha/ocr-demo", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["ground_truth"] == "HELO9"
    assert "ocr_prediction" in data
    assert "execution_time_ms" in data


def test_api_token_verification():
    # Test missing token
    resp = client.post("/api/captcha/verify-token", json={"token": ""})
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "rejected_missing_token"

    # Test reused token
    resp_reused = client.post("/api/captcha/verify-token", json={"token": "test", "simulate_status": "reused"})
    assert resp_reused.status_code == 200
    assert resp_reused.json()["verification_status"] == "rejected_timeout_or_duplicate"
