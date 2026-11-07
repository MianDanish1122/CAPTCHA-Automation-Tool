from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.ocr_service import (
    generate_synthetic_captcha,
    preprocess_captcha_image,
    run_ocr,
    benchmark_synthetic_ocr,
)
from app.services.token_verifier import verify_recaptcha_token

router = APIRouter(
    prefix="/api/captcha",
    tags=["CAPTCHA OCR & Token Verification"]
)


class OCRDemoRequest(BaseModel):
    custom_text: Optional[str] = Field(None, max_length=12, description="Optional custom text for synthetic CAPTCHA")
    noise_level: Optional[str] = Field("medium", description="Noise intensity: low, medium, high")


class OCRBenchmarkRequest(BaseModel):
    samples: int = Field(5, ge=1, le=20, description="Number of synthetic samples to benchmark")


class TokenVerificationRequest(BaseModel):
    token: Optional[str] = Field(None, description="CAPTCHA response token from client")
    secret_key: Optional[str] = Field(None, description="Optional custom secret key (defaults to official test secret)")
    simulate_status: Optional[str] = Field(None, description="Simulation mode: valid, invalid, reused")


@router.post("/ocr-demo")
async def demonstrate_ocr(request: OCRDemoRequest):
    """
    Generate a synthetic distorted CAPTCHA, apply OpenCV preprocessing,
    and evaluate Tesseract OCR extraction.
    """
    img_bytes, ground_truth = generate_synthetic_captcha(text=request.custom_text)
    clean_img, _ = preprocess_captcha_image(img_bytes)
    result = run_ocr(clean_img)

    return {
        "success": True,
        "ground_truth": ground_truth,
        "ocr_prediction": result.get("predicted_text", ""),
        "exact_match": ground_truth == result.get("predicted_text", ""),
        "confidence": result.get("confidence", 0.0),
        "execution_time_ms": result.get("ocr_duration_ms", 0.0),
        "ocr_engine": result.get("ocr_engine"),
        "methodology": {
            "synthesis": "Pillow noise lines + character rotation + salt-pepper artifacts",
            "preprocessing": "OpenCV Bilateral filter + Otsu thresholding + Morphological opening",
            "recognition": "Tesseract PSM 8 alphanumeric whitelist",
        },
    }


@router.post("/ocr-benchmark")
async def benchmark_ocr(request: OCRBenchmarkRequest):
    """
    Evaluate OCR accuracy against a controlled synthetic dataset,
    and output architectural limitation analysis.
    """
    results = benchmark_synthetic_ocr(samples=request.samples)
    return {
        "success": True,
        **results
    }


@router.post("/verify-token")
async def verify_token(request: TokenVerificationRequest):
    """
    Verify a CAPTCHA response token using official Google reCAPTCHA test credentials.
    Tests valid tokens, missing tokens, invalid tokens, and expired/reused tokens.
    """
    result = await verify_recaptcha_token(
        response_token=request.token,
        secret_key=request.secret_key,
        simulate_status=request.simulate_status
    )
    return result
