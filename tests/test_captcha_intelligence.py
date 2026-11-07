import base64
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, init_db
from app.models import (
    HumanReviewRecord,
    CaptchaIntelligenceRecord,
    OcrEvaluationRecord,
)
from app.services.captcha_intelligence import (
    classify_captcha,
    execute_handling_strategy,
)
from app.services.ocr_service import generate_synthetic_captcha

client = TestClient(app)


# ----------------------------------------------------
# 1. Classification Tests
# ----------------------------------------------------

def test_classify_no_captcha():
    html = "<html><body><form><input name='email'><button>Submit</button></form></body></html>"
    result = classify_captcha(html=html, title="Simple Form")
    assert result["classification"] == "no_captcha"
    assert result["provider"] == "none"
    assert result["challenge_type"] == "none"
    assert result["is_active_challenge"] is False
    assert result["handling_strategy"] == "mark_completed"
    assert result["human_review_required"] is False


def test_classify_synthetic_text_captcha():
    img_bytes, _ = generate_synthetic_captcha(length=5)
    result = classify_captcha(image_bytes=img_bytes, is_synthetic=True)
    assert result["classification"] == "synthetic_text_captcha"
    assert result["provider"] == "synthetic_ocr"
    assert result["handling_strategy"] == "ocr_inference"
    assert result["human_review_required"] is False
    assert result["processing_status"] == "ocr_evaluable"


def test_classify_google_recaptcha_active_v2():
    html = """
    <html>
      <head><script src="https://www.google.com/recaptcha/api.js"></script></head>
      <body>
        <div class="g-recaptcha" data-sitekey="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"></div>
      </body>
    </html>
    """
    result = classify_captcha(html=html, title="Contact Form")
    assert result["classification"] == "google_recaptcha"
    assert result["provider"] == "google_recaptcha"
    assert result["challenge_type"] == "v2_checkbox"
    assert result["is_active_challenge"] is True
    assert result["handling_strategy"] == "queue_for_human_review"
    assert result["human_review_required"] is True


def test_classify_google_recaptcha_invisible():
    html = """
    <html>
      <head><script src="https://www.google.com/recaptcha/api.js"></script></head>
      <body>
        <button class="g-recaptcha" data-size="invisible" data-callback="onSubmit">Submit</button>
      </body>
    </html>
    """
    result = classify_captcha(html=html, title="Invisible Protection")
    assert result["classification"] == "google_recaptcha"
    assert result["challenge_type"] == "invisible"
    assert result["is_active_challenge"] is False
    assert result["human_review_required"] is True


def test_classify_google_recaptcha_passive_script():
    html = """
    <html>
      <head><script src="https://www.google.com/recaptcha/api.js"></script></head>
      <body><h1>No widget rendered</h1></body>
    </html>
    """
    result = classify_captcha(html=html, title="Passive Page")
    assert result["classification"] == "google_recaptcha"
    assert result["challenge_type"] == "passive_script"
    assert result["is_active_challenge"] is False


def test_classify_hcaptcha():
    html = """
    <html>
      <head><script src="https://js.hcaptcha.com/1/api.js" async defer></script></head>
      <body>
        <div class="h-captcha" data-sitekey="10000000-ffff-ffff-ffff-000000000001"></div>
      </body>
    </html>
    """
    result = classify_captcha(html=html, title="hCaptcha Protection")
    assert result["classification"] == "hcaptcha"
    assert result["provider"] == "hcaptcha"
    assert result["challenge_type"] == "hcaptcha_checkbox"
    assert result["is_active_challenge"] is True
    assert result["handling_strategy"] == "queue_for_human_review"
    assert result["human_review_required"] is True


def test_classify_cloudflare_turnstile():
    html = """
    <html>
      <head><script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script></head>
      <body>
        <div class="cf-turnstile" data-sitekey="1x00000000000000000000AA"></div>
      </body>
    </html>
    """
    result = classify_captcha(html=html, title="Turnstile Demo")
    assert result["classification"] == "cloudflare_turnstile"
    assert result["provider"] == "cloudflare_turnstile"
    assert result["challenge_type"] == "turnstile_managed"
    assert result["is_active_challenge"] is True
    assert result["handling_strategy"] == "queue_for_human_review"
    assert result["human_review_required"] is True


def test_classify_unknown_anti_bot_challenge():
    html = "<html><head><title>Just a moment...</title></head><body><div id='cf-challenge-running'></div></body></html>"
    result = classify_captcha(html=html, title="Just a moment...")
    assert result["classification"] == "unknown_challenge"
    assert result["provider"] == "unknown_anti_bot"
    assert result["challenge_type"] == "anti_bot_interstitial"
    assert result["is_active_challenge"] is True
    assert result["handling_strategy"] == "manual_investigation"
    assert result["human_review_required"] is True


# ----------------------------------------------------
# 2. Decision Workflow & Handling Strategy Tests
# ----------------------------------------------------

@pytest.mark.anyio
async def test_execute_handling_no_captcha():
    init_db()
    classification = classify_captcha(html="<p>Clean Page</p>", title="Clean")
    handling = await execute_handling_strategy(
        classification_result=classification,
        page_url="https://example.com/clean",
    )
    assert handling["success"] is True
    assert handling["strategy_applied"] == "mark_completed"
    assert handling["human_review_required"] is False
    assert handling["review_id"] is None


@pytest.mark.anyio
async def test_execute_handling_synthetic_ocr():
    init_db()
    img_bytes, ground_truth = generate_synthetic_captcha(length=5)
    classification = classify_captcha(image_bytes=img_bytes, is_synthetic=True)
    handling = await execute_handling_strategy(
        classification_result=classification,
        image_bytes=img_bytes,
        page_url="http://localhost/synthetic-demo",
    )
    assert handling["success"] is True
    assert handling["strategy_applied"] == "ocr_inference"
    assert handling["human_review_required"] is False
    assert "ocr_result" in handling
    assert handling["ocr_result"]["predicted_text"] is not None


@pytest.mark.anyio
async def test_execute_handling_third_party_queues_review():
    init_db()
    html = "<div class='g-recaptcha' data-sitekey='xxx'></div><script src='https://www.google.com/recaptcha/api.js'></script>"
    classification = classify_captcha(html=html)
    handling = await execute_handling_strategy(
        classification_result=classification,
        page_url="https://example.com/contact-form",
        scan_id="test-scan-uuid-1",
    )
    assert handling["success"] is True
    assert handling["strategy_applied"] == "queue_for_human_review"
    assert handling["human_review_required"] is True
    assert handling["review_id"] is not None
    assert handling["review_status"] == "pending"

    # Verify persistent DB record
    db = SessionLocal()
    rec = db.query(HumanReviewRecord).filter(HumanReviewRecord.id == handling["review_id"]).first()
    assert rec is not None
    assert rec.captcha_provider == "google_recaptcha"
    assert rec.review_status == "pending"
    db.close()


@pytest.mark.anyio
async def test_execute_handling_unknown_challenge_queues_investigation():
    init_db()
    html = "<h1>Attention Required! | Cloudflare</h1>"
    classification = classify_captcha(html=html, title="Attention Required! | Cloudflare")
    handling = await execute_handling_strategy(
        classification_result=classification,
        page_url="https://example.com/blocked",
    )
    assert handling["success"] is True
    assert handling["strategy_applied"] == "manual_investigation"
    assert handling["human_review_required"] is True
    assert handling["review_id"] is not None


# ----------------------------------------------------
# 3. API Endpoints: Classification & Handling
# ----------------------------------------------------

def test_api_classify_endpoint():
    payload = {
        "html": "<div class='cf-turnstile'></div><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>",
        "title": "Turnstile Page",
    }
    response = client.post("/api/captcha/classify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["classification"] == "cloudflare_turnstile"
    assert data["handling_strategy"] == "queue_for_human_review"
    assert data["human_review_required"] is True


def test_api_evaluate_handling_endpoint():
    payload = {
        "html": "<div class='h-captcha'></div><script src='https://js.hcaptcha.com/1/api.js'></script>",
        "page_url": "https://example.com/hcaptcha-page",
    }
    response = client.post("/api/captcha/evaluate-handling", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["classification"]["classification"] == "hcaptcha"
    assert data["handling"]["strategy_applied"] == "queue_for_human_review"
    assert data["handling"]["review_id"] is not None


# ----------------------------------------------------
# 4. API Endpoints: Human Review Workflow & Status Transitions
# ----------------------------------------------------

def test_human_review_lifecycle_and_operator_transitions():
    init_db()
    # 1. Enqueue review via evaluate-handling
    payload = {
        "html": "<div class='g-recaptcha'></div><script src='https://google.com/recaptcha'></script>",
        "page_url": "https://example.com/login",
    }
    eval_resp = client.post("/api/captcha/evaluate-handling", json=payload)
    assert eval_resp.status_code == 200
    review_id = eval_resp.json()["handling"]["review_id"]

    # 2. Query review queue
    list_resp = client.get("/api/captcha/reviews?status=pending")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["success"] is True
    assert list_data["summary"]["pending"] >= 1
    assert any(r["id"] == review_id for r in list_data["reviews"])

    # 3. Retrieve review detail
    detail_resp = client.get(f"/api/captcha/reviews/{review_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["review"]
    assert detail_data["id"] == review_id
    assert detail_data["review_status"] == "pending"
    assert detail_data["resolved_at"] is None

    # 4. Operator updates status to manually_verified with notes
    update_payload = {
        "review_status": "manually_verified",
        "operator_notes": "Operator resolved reCAPTCHA checkbox manually in test environment.",
    }
    patch_resp = client.patch(f"/api/captcha/reviews/{review_id}", json=update_payload)
    assert patch_resp.status_code == 200
    updated_data = patch_resp.json()["review"]
    assert updated_data["review_status"] == "manually_verified"
    assert updated_data["operator_notes"] == update_payload["operator_notes"]
    assert updated_data["resolved_at"] is not None

    # 5. Invalid transition rejected
    bad_resp = client.patch(f"/api/captcha/reviews/{review_id}", json={"review_status": "invalid_status"})
    assert bad_resp.status_code == 400


def test_human_review_detail_not_found():
    response = client.get("/api/captcha/reviews/non-existent-review-id-999")
    assert response.status_code == 404


# ----------------------------------------------------
# 5. OCR & Token Verification Tests
# ----------------------------------------------------

def test_api_ocr_demo_persists_evaluation():
    init_db()
    response = client.post("/api/captcha/ocr-demo", json={"custom_text": "TEST9"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "evaluation_id" in data
    assert data["ground_truth"] == "TEST9"

    # Verify DB persistence of evaluation
    db = SessionLocal()
    eval_rec = db.query(OcrEvaluationRecord).filter(OcrEvaluationRecord.id == data["evaluation_id"]).first()
    assert eval_rec is not None
    assert eval_rec.ground_truth == "TEST9"
    db.close()


def test_api_ocr_benchmark_endpoint():
    response = client.post("/api/captcha/ocr-benchmark", json={"samples": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_samples"] == 3
    assert "limitations_analysis" in data
    assert len(data["sample_evaluations"]) == 3


@pytest.mark.anyio
async def test_token_verification_cases():
    # 1. Missing token
    resp_missing = client.post("/api/captcha/verify-token", json={"token": ""})
    assert resp_missing.status_code == 200
    assert resp_missing.json()["verification_status"] == "rejected_missing_token"

    # 2. Invalid token
    resp_invalid = client.post("/api/captcha/verify-token", json={"token": "MOCK_INVALID_TOKEN"})
    assert resp_invalid.status_code == 200
    assert resp_invalid.json()["verification_status"] == "rejected_invalid_token"

    # 3. Reused token
    resp_reused = client.post("/api/captcha/verify-token", json={"token": "MOCK_EXPIRED_OR_REUSED_TOKEN"})
    assert resp_reused.status_code == 200
    assert resp_reused.json()["verification_status"] == "rejected_timeout_or_duplicate"

    # 4. Official test approved token
    resp_valid = client.post("/api/captcha/verify-token", json={"token": "VALID_TEST_RESPONSE"})
    assert resp_valid.status_code == 200
    assert resp_valid.json()["success"] is True
