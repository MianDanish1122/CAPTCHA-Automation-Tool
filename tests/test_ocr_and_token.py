import pytest
from app.services.ocr_service import (
    generate_synthetic_captcha,
    preprocess_captcha_image,
    run_ocr,
    benchmark_synthetic_ocr,
)
from app.services.token_verifier import verify_recaptcha_token


def test_synthetic_captcha_generation():
    img_bytes, text = generate_synthetic_captcha(text="TEST89", length=6)
    assert len(img_bytes) > 500
    assert text == "TEST89"


def test_opencv_preprocessing():
    img_bytes, text = generate_synthetic_captcha(text="ABC12")
    clean_img, clean_bytes = preprocess_captcha_image(img_bytes)
    assert clean_img is not None
    assert len(clean_bytes) > 200
    # Clean image should have shape matching height/width
    assert len(clean_img.shape) == 2  # Grayscale single-channel


def test_ocr_single_run():
    img_bytes, text = generate_synthetic_captcha(text="A1B2C")
    clean_img, _ = preprocess_captcha_image(img_bytes)
    ocr_res = run_ocr(clean_img)
    assert ocr_res["success"] is True
    assert "ocr_duration_ms" in ocr_res
    assert ocr_res["ocr_duration_ms"] > 0


def test_ocr_benchmark_dataset():
    benchmark = benchmark_synthetic_ocr(samples=2)
    assert benchmark["total_samples"] == 2
    assert "exact_match_rate_pct" in benchmark
    assert "character_accuracy_pct" in benchmark
    assert "average_duration_ms" in benchmark
    assert len(benchmark["sample_evaluations"]) == 2
    assert "limitations_analysis" in benchmark


@pytest.mark.anyio
async def test_token_verification_missing_token():
    res = await verify_recaptcha_token(response_token="")
    assert res["success"] is False
    assert "missing-input-response" in res["error_codes"]
    assert res["verification_status"] == "rejected_missing_token"


@pytest.mark.anyio
async def test_token_verification_invalid_token():
    res = await verify_recaptcha_token(response_token="MOCK_INVALID_TOKEN")
    assert res["success"] is False
    assert "invalid-input-response" in res["error_codes"]
    assert res["verification_status"] == "rejected_invalid_token"


@pytest.mark.anyio
async def test_token_verification_reused_token():
    res = await verify_recaptcha_token(
        response_token="ANY_TOKEN",
        simulate_status="reused"
    )
    assert res["success"] is False
    assert "timeout-or-duplicate" in res["error_codes"]
    assert res["verification_status"] == "rejected_timeout_or_duplicate"


@pytest.mark.anyio
async def test_token_verification_official_test_approved():
    res = await verify_recaptcha_token(response_token="VALID_TEST_RESPONSE")
    assert res["success"] is True
    assert "verified" in res["verification_status"]
