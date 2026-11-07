import base64
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import HumanReviewRecord, CaptchaIntelligenceRecord, OcrEvaluationRecord
from app.services.captcha_intelligence import classify_captcha, execute_handling_strategy
from app.services.ocr_service import (
    generate_synthetic_captcha,
    preprocess_captcha_image,
    run_ocr,
    benchmark_synthetic_ocr,
)
from app.services.token_verifier import verify_recaptcha_token

router = APIRouter(
    prefix="/api/captcha",
    tags=["CAPTCHA Intelligence, OCR & Reviews"]
)


# -----------------------------
# Request & Response Models
# -----------------------------

class OCRDemoRequest(BaseModel):
    custom_text: Optional[str] = Field(None, max_length=12, description="Optional custom text for synthetic CAPTCHA")
    noise_level: Optional[str] = Field("medium", description="Noise intensity: low, medium, high")


class OCRBenchmarkRequest(BaseModel):
    samples: int = Field(5, ge=1, le=20, description="Number of synthetic samples to benchmark")


class TokenVerificationRequest(BaseModel):
    token: Optional[str] = Field(None, description="CAPTCHA response token from client")
    secret_key: Optional[str] = Field(None, description="Optional custom secret key (defaults to official test secret)")
    simulate_status: Optional[str] = Field(None, description="Simulation mode: valid, invalid, reused")


class CaptchaClassificationRequest(BaseModel):
    html: Optional[str] = Field(None, description="HTML snippet to analyze for CAPTCHA markers")
    title: Optional[str] = Field(None, description="Document title to analyze")
    image_base64: Optional[str] = Field(None, description="Base64-encoded image data for synthetic OCR")
    is_synthetic: Optional[bool] = Field(False, description="Flag indicating synthetic/owned CAPTCHA image")
    is_official_test: Optional[bool] = Field(False, description="Flag indicating official test environment")


class EvaluateHandlingRequest(BaseModel):
    html: Optional[str] = Field(None, description="HTML markup of the inspected page")
    title: Optional[str] = Field(None, description="Page title")
    page_url: Optional[str] = Field("http://localhost/demo", description="URL of the page undergoing inspection")
    scan_id: Optional[str] = Field(None, description="Associated scan ID if part of a crawl run")
    response_token: Optional[str] = Field(None, description="Response token for test verification")
    image_base64: Optional[str] = Field(None, description="Base64-encoded image data for synthetic OCR")
    is_synthetic: Optional[bool] = Field(False, description="Flag indicating synthetic/owned CAPTCHA")
    is_official_test: Optional[bool] = Field(False, description="Flag indicating official test environment")


class UpdateReviewRequest(BaseModel):
    review_status: str = Field(..., description="Target status: approved, rejected, manually_verified")
    operator_notes: Optional[str] = Field(None, description="Auditable operator decision notes")


# -----------------------------
# 1. CAPTCHA Classification
# -----------------------------

@router.post("/classify")
async def classify_captcha_endpoint(request: CaptchaClassificationRequest):
    """
    Classify CAPTCHA presence and determine provider, challenge type, confidence,
    and recommended handling strategy.
    """
    image_bytes = None
    if request.image_base64:
        try:
            image_bytes = base64.b64decode(request.image_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64-encoded image data.")

    result = classify_captcha(
        html=request.html,
        title=request.title,
        image_bytes=image_bytes,
        is_synthetic=request.is_synthetic,
        is_official_test=request.is_official_test,
    )
    return {
        "success": True,
        **result
    }


# -----------------------------
# 2. Decision & Handling Workflow
# -----------------------------

@router.post("/evaluate-handling")
async def evaluate_handling_endpoint(
    request: EvaluateHandlingRequest,
    db: Session = Depends(get_db)
):
    """
    Execute decision and handling workflow based on CAPTCHA classification:
      - No CAPTCHA -> Mark completed
      - Synthetic CAPTCHA -> Run OCR service on owned image
      - Official test CAPTCHA -> Run server-side token verification
      - Third-party CAPTCHA -> Queue for human review (no automated bypass)
      - Unknown challenge -> Queue for manual investigation
    """
    image_bytes = None
    if request.image_base64:
        try:
            image_bytes = base64.b64decode(request.image_base64)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64-encoded image data.")

    classification = classify_captcha(
        html=request.html,
        title=request.title,
        image_bytes=image_bytes,
        is_synthetic=request.is_synthetic,
        is_official_test=request.is_official_test,
    )

    handling_result = await execute_handling_strategy(
        classification_result=classification,
        page_url=request.page_url or "http://localhost/demo",
        scan_id=request.scan_id,
        image_bytes=image_bytes,
        response_token=request.response_token,
        db=db,
    )

    return {
        "success": True,
        "classification": classification,
        "handling": handling_result,
    }


# -----------------------------
# 3. Human Review Workflow
# -----------------------------

@router.get("/reviews")
async def list_reviews(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, manually_verified"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Retrieve queue of human review records with status counters.
    """
    query = db.query(HumanReviewRecord)
    if status:
        query = query.filter(HumanReviewRecord.review_status == status)

    total = query.count()
    records = query.order_by(HumanReviewRecord.created_at.desc()).offset(offset).limit(limit).all()

    # Aggregate status counts
    pending_count = db.query(HumanReviewRecord).filter(HumanReviewRecord.review_status == "pending").count()
    approved_count = db.query(HumanReviewRecord).filter(HumanReviewRecord.review_status == "approved").count()
    rejected_count = db.query(HumanReviewRecord).filter(HumanReviewRecord.review_status == "rejected").count()
    verified_count = db.query(HumanReviewRecord).filter(HumanReviewRecord.review_status == "manually_verified").count()

    return {
        "success": True,
        "total_records": total,
        "summary": {
            "pending": pending_count,
            "approved": approved_count,
            "rejected": rejected_count,
            "manually_verified": verified_count,
        },
        "reviews": [r.to_dict() for r in records],
    }


@router.get("/reviews/{review_id}")
async def get_review_detail(review_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single human review record."""
    review = db.query(HumanReviewRecord).filter(HumanReviewRecord.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail=f"Review record '{review_id}' not found.")

    return {
        "success": True,
        "review": review.to_dict(),
    }


@router.patch("/reviews/{review_id}")
async def update_review_status(
    review_id: str,
    request: UpdateReviewRequest,
    db: Session = Depends(get_db)
):
    """
    Update human review status as an operator decision.
    Valid target statuses: approved, rejected, manually_verified.
    """
    valid_statuses = ("approved", "rejected", "manually_verified")
    if request.review_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review status '{request.review_status}'. Permitted: {', '.join(valid_statuses)}"
        )

    review = db.query(HumanReviewRecord).filter(HumanReviewRecord.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail=f"Review record '{review_id}' not found.")

    review.review_status = request.review_status
    if request.operator_notes:
        review.operator_notes = request.operator_notes
    review.resolved_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "message": f"Review {review_id} updated to '{request.review_status}'.",
        "review": review.to_dict(),
    }


# -----------------------------
# 4. OCR Demo & Benchmark
# -----------------------------

@router.post("/ocr-demo")
async def demonstrate_ocr(request: OCRDemoRequest, db: Session = Depends(get_db)):
    """
    Generate a synthetic distorted CAPTCHA, apply OpenCV preprocessing,
    evaluate Tesseract OCR extraction, and persist the evaluation record.
    """
    img_bytes, ground_truth = generate_synthetic_captcha(text=request.custom_text)
    clean_img, clean_bytes = preprocess_captcha_image(img_bytes)
    result = run_ocr(clean_img)

    pred = result.get("predicted_text", "")
    is_exact = (pred == ground_truth)
    min_len = min(len(pred), len(ground_truth))
    correct_chars = sum(1 for c1, c2 in zip(pred[:min_len], ground_truth[:min_len]) if c1 == c2)
    char_acc = (correct_chars / max(len(pred), len(ground_truth)) * 100) if ground_truth else 0.0

    # Persist evaluation record
    eval_rec = OcrEvaluationRecord(
        ground_truth=ground_truth,
        predicted_text=pred,
        exact_match=is_exact,
        character_accuracy=char_acc,
        confidence=result.get("confidence", 0.0),
        duration_ms=result.get("ocr_duration_ms", 0.0),
        ocr_engine=result.get("ocr_engine", "Tesseract OCR v5.5.0"),
    )
    db.add(eval_rec)
    db.commit()

    return {
        "success": True,
        "evaluation_id": eval_rec.id,
        "ground_truth": ground_truth,
        "ocr_prediction": pred,
        "exact_match": is_exact,
        "character_accuracy": round(char_acc, 1),
        "confidence": result.get("confidence", 0.0),
        "execution_time_ms": result.get("ocr_duration_ms", 0.0),
        "ocr_engine": result.get("ocr_engine"),
        "image_base64": base64.b64encode(img_bytes).decode("utf-8"),
        "preprocessed_base64": base64.b64encode(clean_bytes).decode("utf-8"),
        "methodology": {
            "synthesis": "Pillow noise lines + character rotation + salt-pepper artifacts",
            "preprocessing": "OpenCV Bilateral filter + Otsu thresholding + Morphological opening",
            "recognition": "Tesseract PSM 7 LSTM inference",
        },
    }


@router.post("/ocr-benchmark")
async def benchmark_ocr(request: OCRBenchmarkRequest):
    """
    Evaluate OCR accuracy against a controlled synthetic dataset,
    and output architectural limitation analysis.
    """
    results = benchmark_synthetic_ocr(samples=request.samples)
    total_samples = results.get("total_samples", request.samples)
    exact_pct = results.get("exact_match_rate_pct", 0.0)
    exact_count = round(total_samples * (exact_pct / 100.0))
    sample_evals = results.get("sample_evaluations", [])

    # Format items for both schemas
    results_list = []
    for item in sample_evals:
        results_list.append({
            "sample_index": item.get("sample_index"),
            "ground_truth": item.get("ground_truth"),
            "predicted_text": item.get("predicted_text"),
            "exact_match": item.get("exact_match"),
            "character_accuracy": item.get("confidence", 0.0) if item.get("character_accuracy") is None else item.get("character_accuracy"),
            "execution_time_ms": item.get("duration_ms", 0.0),
            "noise_level": "standard",
        })

    return {
        "success": True,
        **results,
        "exact_matches": exact_count,
        "exact_match_rate_percent": exact_pct,
        "mean_character_accuracy": results.get("character_accuracy_pct", 0.0),
        "mean_execution_time_ms": results.get("average_duration_ms", 0.0),
        "results": results_list,
        "technical_limitations_summary": results.get("limitations_analysis", ""),
    }


# -----------------------------
# 5. Official Token Verification
# -----------------------------

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
