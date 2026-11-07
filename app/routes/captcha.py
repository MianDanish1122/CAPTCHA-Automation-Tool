import base64
import json
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    HumanReviewRecord, CaptchaIntelligenceRecord, OcrEvaluationRecord, OcrBenchmarkRun,
    ReviewDecision, User, VerificationRecord,
)
from app.services.captcha_intelligence import (
    classify_captcha,
    execute_handling_strategy,
    validate_client_assertions,
)
from app.services.input_limits import decode_image_b64, max_b64_chars
from app.services.ocr_service import generate_synthetic_captcha, preprocess_captcha_image
from app.ocr.engines import ENGINES, recognize
from app.ocr.metrics import char_accuracy
from app.services.token_verifier import PROVIDERS, SIMULATIONS, verify_token
from app.services.verification_store import record_verification
from app.services.auth_service import require_operator, log_audit_event
from app.services.rate_limiter import rate_limit
from app.services.client_ip import get_client_ip
from app.services.audit import sanitize_request_id

router = APIRouter(
    prefix="/api/captcha",
    tags=["CAPTCHA Intelligence, OCR & Reviews"],
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_DEFAULT_PER_MIN, window_seconds=60, scope="api_default"))],
)

compute_limit = rate_limit(max_requests=settings.RATE_LIMIT_COMPUTE_PER_MIN, window_seconds=60, scope="compute")


# -----------------------------
# Request & Response Models
# -----------------------------

class OCRDemoRequest(BaseModel):
    custom_text: Optional[str] = Field(None, max_length=12, pattern=r"^[A-Za-z0-9]*$", description="Optional custom text for synthetic CAPTCHA")
    noise_level: Optional[str] = Field("medium", pattern=r"^(low|medium|high)$", description="Noise intensity: low, medium, high")
    engine: str = Field("hybrid", pattern=r"^(tesseract_legacy|tesseract_tuned|custom_mlp|hybrid)$")


class OCRBenchmarkRequest(BaseModel):
    samples: int = Field(20, ge=1, le=100, description="Number of labelled dataset samples to evaluate (first N, deterministic)")
    engine: str = Field("hybrid", pattern=r"^(tesseract_legacy|tesseract_tuned|custom_mlp|hybrid)$")
    split: str = Field("dev", pattern=r"^(dev|test)$", description="dataset split to evaluate")


class TokenVerificationRequest(BaseModel):
    provider: str = Field("google_recaptcha", pattern=r"^(google_recaptcha|hcaptcha|cloudflare_turnstile)$")
    expected_hostname: Optional[str] = Field(None, max_length=255, description="Hostname the provider must report (real keys only)")
    token: Optional[str] = Field(None, max_length=4096, description="CAPTCHA response token from client")
    secret_key: Optional[str] = Field(None, max_length=256, description="Optional custom secret key (defaults to official test secret)")
    simulate_status: Optional[str] = Field(None, pattern=r"^(invalid|expired|reused|provider_down|provider_malformed)$", description="Local SIMULATION of a failure scenario (no provider call; can never succeed)")


class CaptchaClassificationRequest(BaseModel):
    html: Optional[str] = Field(None, max_length=settings.MAX_HTML_CHARS, description="HTML snippet to analyze for CAPTCHA markers")
    title: Optional[str] = Field(None, max_length=512, description="Document title to analyze")
    image_base64: Optional[str] = Field(None, max_length=max_b64_chars(), description="Base64-encoded image data for synthetic OCR")
    is_synthetic: Optional[bool] = Field(False, description="REQUEST for synthetic mode; honored only after server-side validation")
    is_official_test: Optional[bool] = Field(False, description="REQUEST for official-test mode; honored only if the page uses published provider test keys")


class EvaluateHandlingRequest(BaseModel):
    html: Optional[str] = Field(None, max_length=settings.MAX_HTML_CHARS, description="HTML markup of the inspected page")
    title: Optional[str] = Field(None, max_length=512, description="Page title")
    page_url: Optional[str] = Field("http://localhost/demo", max_length=2048, description="URL of the page undergoing inspection")
    scan_id: Optional[str] = Field(None, max_length=36, description="Associated scan ID if part of a crawl run")
    response_token: Optional[str] = Field(None, max_length=4096, description="Response token for test verification")
    image_base64: Optional[str] = Field(None, max_length=max_b64_chars(), description="Base64-encoded image data for synthetic OCR")
    is_synthetic: Optional[bool] = Field(False, description="REQUEST for synthetic mode; honored only after server-side validation")
    is_official_test: Optional[bool] = Field(False, description="REQUEST for official-test mode; honored only if the page uses published provider test keys")


class UpdateReviewRequest(BaseModel):
    review_status: str = Field(..., max_length=32, description="Decision: approved, rejected, manually_verified")
    operator_notes: Optional[str] = Field(None, max_length=4000, description="Operator audit notes justifying the decision")


# -----------------------------
# 1. CAPTCHA Classification & Intelligence
# -----------------------------

@router.post("/classify", dependencies=[Depends(compute_limit)])
async def classify_page(
    request: CaptchaClassificationRequest,
    current_user: User = Depends(require_operator)
):
    """
    Classify page HTML/DOM markers into recognized CAPTCHA providers,
    distinguishing active widgets, passive scripts, invisible tokens, and unknown interstitials.
    """
    image_bytes = decode_image_b64(request.image_base64)
    assertions = validate_client_assertions(
        request.html, request.title, image_bytes, bool(request.is_synthetic), bool(request.is_official_test)
    )
    result = classify_captcha(
        html=request.html,
        title=request.title,
        is_synthetic=assertions["is_synthetic"]["accepted"],
        is_official_test=assertions["is_official_test"]["accepted"],
    )
    return {
        "success": True,
        **result,
        "client_assertions": assertions,
    }


@router.post("/evaluate-handling", dependencies=[Depends(compute_limit)])
async def evaluate_page_handling(
    request: EvaluateHandlingRequest,
    req: Request,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Classify discovered CAPTCHA and execute appropriate handling workflow:
      - No CAPTCHA -> mark completed
      - Synthetic text -> run OCR inference and evaluate character accuracy
      - Official test CAPTCHA -> Run server-side token verification
      - Production third-party CAPTCHA -> Record evidence, route to Human Review Queue
    """
    image_bytes = decode_image_b64(request.image_base64)
    assertions = validate_client_assertions(
        request.html, request.title, image_bytes, bool(request.is_synthetic), bool(request.is_official_test)
    )
    classification_result = classify_captcha(
        html=request.html,
        title=request.title,
        is_synthetic=assertions["is_synthetic"]["accepted"],
        is_official_test=assertions["is_official_test"]["accepted"],
    )

    if request.is_synthetic or request.is_official_test:
        log_audit_event(
            db=db,
            action="captcha.mode_assertion",
            actor=current_user,
            ip_address=get_client_ip(req),
            request_id=req.headers.get("X-Request-ID"),
            details={
                "is_synthetic": assertions["is_synthetic"],
                "is_official_test": assertions["is_official_test"],
            },
        )

    handling_result = await execute_handling_strategy(
        classification_result=classification_result,
        page_url=request.page_url,
        scan_id=request.scan_id,
        image_bytes=image_bytes,
        response_token=request.response_token,
        db=db,
    )

    return {
        "success": True,
        **handling_result,
        "handling": handling_result,
        "classification": classification_result,
        "client_assertions": assertions,
    }


# -----------------------------
# 2. CAPTCHA Results Reporting
# -----------------------------

@router.get("/results")
async def get_captcha_results(
    provider: Optional[str] = Query(None),
    challenge_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Retrieve classified CAPTCHA records across scans.
    """
    query = db.query(CaptchaIntelligenceRecord)
    if provider and provider != "all":
        query = query.filter(CaptchaIntelligenceRecord.provider == provider)
    if challenge_only:
        query = query.filter(CaptchaIntelligenceRecord.is_active_challenge == True)

    total = query.count()
    records = query.order_by(CaptchaIntelligenceRecord.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "results": [r.to_dict() for r in records],
    }


# -----------------------------
# 3. Human Review Queue & Decisions
# -----------------------------

@router.get("/reviews")
async def list_reviews(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected, manually_verified"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_operator),
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
async def get_review_detail(
    review_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Retrieve details for a single human review record."""
    review = db.query(HumanReviewRecord).filter(HumanReviewRecord.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail=f"Review record '{review_id}' not found.")

    return {
        "success": True,
        "review": review.to_dict(),
        "history": _decision_history(db, review_id),
    }


def _decision_history(db: Session, review_id: str) -> list[dict]:
    rows = (
        db.query(ReviewDecision)
        .filter(ReviewDecision.review_id == review_id)
        .order_by(ReviewDecision.decided_at.asc())
        .all()
    )
    return [r.to_dict() for r in rows]


@router.get("/reviews/{review_id}/history")
async def get_review_history(
    review_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Full, append-only decision history (who decided what, when, and why)."""
    review = db.query(HumanReviewRecord).filter(HumanReviewRecord.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail=f"Review record '{review_id}' not found.")
    return {"success": True, "review_id": review_id, "history": _decision_history(db, review_id)}


@router.patch(
    "/reviews/{review_id}",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_REVIEWS_PER_MIN, window_seconds=60, scope="review_update"))]
)
async def update_review_status(
    review_id: str,
    request: UpdateReviewRequest,
    req: Request,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Update human review status as an operator decision.
    Valid target statuses: approved, rejected, manually_verified.
    Only authorized operators and administrators may update review records.
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

    previous_status = review.review_status
    client_ip = get_client_ip(req)
    request_id = sanitize_request_id(req.headers.get("X-Request-ID"))

    # Immutable decision record: who changed what, from which state, when and why.
    db.add(ReviewDecision(
        review_id=review.id,
        decided_by_id=current_user.id,
        decided_by_username=current_user.username,
        decided_by_role=current_user.role,
        previous_status=previous_status,
        new_status=request.review_status,
        notes=request.operator_notes,
        ip_address=client_ip,
        request_id=request_id,
    ))
    review.review_status = request.review_status
    if request.operator_notes is not None:
        review.operator_notes = request.operator_notes
    review.resolved_at = datetime.now(timezone.utc)
    review.reviewed_by_id = current_user.id
    review.reviewed_by_username = current_user.username
    review.decision_count = (review.decision_count or 0) + 1
    db.commit()

    log_audit_event(
        db=db,
        action="review.update",
        actor=current_user,
        resource_type="human_review",
        resource_id=review_id,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID"),
        details={
            "previous_status": previous_status,
            "new_status": request.review_status,
            "has_notes": bool(request.operator_notes),
        }
    )

    return {
        "success": True,
        "message": f"Review {review_id} updated to '{request.review_status}'.",
        "review": review.to_dict(),
    }


# -----------------------------
# 4. OCR Demo & Benchmark
# -----------------------------

@router.post("/ocr-demo", dependencies=[Depends(compute_limit)])
async def demonstrate_ocr(
    request: OCRDemoRequest,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Generate an OWNED synthetic CAPTCHA (true label known), recognise it with the selected engine,
    and persist an evaluation record with the REAL label, exact-match flag and edit-distance accuracy.
    """
    img_bytes, ground_truth = generate_synthetic_captcha(text=request.custom_text)
    clean_img, clean_bytes = preprocess_captcha_image(img_bytes)  # visualisation of the legacy cleaner
    res = recognize(img_bytes, request.engine, expected_length=len(ground_truth))

    pred = res["pred"]
    is_exact = (pred == ground_truth)
    char_acc = 100.0 * char_accuracy(pred, ground_truth)

    eval_rec = OcrEvaluationRecord(
        ground_truth=ground_truth,
        predicted_text=pred,
        exact_match=is_exact,
        character_accuracy=char_acc,
        confidence=res["confidence"],
        duration_ms=res["latency_ms"],
        ocr_engine=f"{res['engine']} ({res.get('route', 'single')})",
    )
    db.add(eval_rec)
    db.commit()

    return {
        "success": not res["failed"],
        "evaluation_id": eval_rec.id,
        "engine": res["engine"],
        "route": res.get("route"),
        "fallback_reason": res.get("fallback_reason"),
        "ground_truth": ground_truth,
        "ocr_prediction": pred,
        "exact_match": is_exact,
        "character_accuracy": round(char_acc, 1),
        "confidence": res["confidence"],
        "confidence_meaning": (
            "mean per-glyph softmax probability of the custom model"
            if res["engine"] in ("custom_mlp", "hybrid") and res.get("route") == "custom_mlp"
            else "Tesseract mean word confidence"
        ),
        "execution_time_ms": res["latency_ms"],
        "ocr_engine": eval_rec.ocr_engine,
        "error": res.get("error"),
        "image_base64": base64.b64encode(img_bytes).decode("utf-8"),
        "preprocessed_base64": base64.b64encode(clean_bytes).decode("utf-8"),
        "methodology": {
            "synthesis": "Deterministic-capable Pillow generator: rotated glyphs, noise lines, noise dots",
            "preprocessing": "Dark-ink mask + connected-component noise filter (custom engine); legacy OpenCV cleaner shown above",
            "recognition": "Segmentation + HOG/NumPy-MLP glyph classifier, Tesseract fallback (hybrid)",
        },
    }


@router.post(
    "/ocr-benchmark",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_BENCHMARK_PER_MIN, window_seconds=60, scope="ocr_benchmark"))]
)
async def benchmark_ocr(
    request: OCRBenchmarkRequest,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """
    Evaluate an engine on the committed, hash-verified labelled dataset (`datasets/ocr_synthetic_v1`).
    The same samples are used on every call (deterministic), the run is persisted, and nothing is
    randomly generated. For the full held-out evaluation use `python -m scripts.ocr_benchmark`.
    """
    from app.ocr import dataset as ds
    from app.ocr.metrics import summarize

    dataset_dir = settings.BASE_DIR / "datasets" / "ocr_synthetic_v1"
    try:
        items = ds.load_split(dataset_dir, request.split)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="OCR dataset is not materialised (run scripts.ocr_benchmark build-dataset).")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Dataset integrity check failed: {exc}")
    items = items[:request.samples]

    rows = []
    for idx, item in enumerate(items, 1):
        res = recognize(item["png"], request.engine)
        rows.append({"sample_index": idx, "file": item["file"], "truth": item["label"], "pred": res["pred"],
                     "latency_ms": res["latency_ms"], "failed": res["failed"], "confidence": res["confidence"],
                     "route": res.get("route")})
    summary = summarize(rows)

    run = OcrBenchmarkRun(
        source="api", dataset="ocr_synthetic_v1", split=request.split, engine=request.engine,
        samples=summary["samples"], exact_matches=summary["exact_matches"],
        exact_match_pct=summary["exact_match_pct"], char_accuracy_pct=summary["char_accuracy_pct"],
        latency_ms_mean=summary["latency_ms_mean"], latency_ms_p95=summary["latency_ms_p95"],
        failures=summary["failures"], details=json.dumps({"summary": summary}), user_id=current_user.id,
    )
    db.add(run)
    db.commit()

    return {
        "success": True,
        "run_id": run.id,
        "dataset": "ocr_synthetic_v1",
        "split": request.split,
        "engine": request.engine,
        "total_samples": summary["samples"],
        "exact_matches": summary["exact_matches"],
        "exact_match_rate_percent": summary["exact_match_pct"],
        "mean_character_accuracy": summary["char_accuracy_pct"],
        "mean_execution_time_ms": summary["latency_ms_mean"],
        "latency_ms_p95": summary["latency_ms_p95"],
        "failures": summary["failures"],
        "summary": summary,
        "results": [{
            "sample_index": r["sample_index"], "ground_truth": r["truth"], "predicted_text": r["pred"],
            "exact_match": r["pred"] == r["truth"],
            "character_accuracy": round(100.0 * char_accuracy(r["pred"], r["truth"]), 1),
            "execution_time_ms": r["latency_ms"], "noise_level": "standard",
        } for r in rows],
        "sample_evaluations": [{  # legacy key kept for API compatibility
            "sample_index": r["sample_index"], "ground_truth": r["truth"], "predicted_text": r["pred"],
            "exact_match": r["pred"] == r["truth"], "confidence": r["confidence"], "duration_ms": r["latency_ms"],
        } for r in rows],
        "confusion_matrix_insights": _confusions(rows),
        "limitations_analysis": (
            "Results apply only to this project's own synthetic text CAPTCHAs; production CAPTCHAs are "
            "detected and routed to human review, never solved."
        ),
        "technical_limitations_summary": (
            "Results apply to this project's own synthetic text CAPTCHAs only. Production CAPTCHAs "
            "(reCAPTCHA, hCaptcha, Turnstile) are not text-OCR problems; they are detected and routed to "
            "human review, never solved."
        ),
    }


def _confusions(rows: list[dict]) -> list[str]:
    """Most frequent aligned character confusions among wrong, equal-length predictions."""
    from collections import Counter
    pairs = Counter()
    for r in rows:
        if len(r["pred"]) == len(r["truth"]):
            for a, b in zip(r["truth"], r["pred"]):
                if a != b:
                    pairs[(a, b)] += 1
    return [f"'{a}' read as '{b}' x{n}" for (a, b), n in pairs.most_common(5)]


@router.get("/ocr-benchmark/runs")
async def list_benchmark_runs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Persisted OCR evaluation runs (CLI held-out runs and API runs)."""
    rows = db.query(OcrBenchmarkRun).order_by(OcrBenchmarkRun.created_at.desc()).limit(limit).all()
    return {"success": True, "total": db.query(OcrBenchmarkRun).count(), "runs": [r.to_dict() for r in rows]}


# -----------------------------
# 5. Official Token Verification
# -----------------------------

@router.post("/verify-token", dependencies=[Depends(compute_limit)])
async def verify_token_endpoint(
    request: TokenVerificationRequest,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """
    Server-side verification against the provider's official siteverify endpoint.
    The response states `verification_mode` (provider_live | provider_test_keys | simulated |
    local_validation); `success` is true ONLY if the provider itself confirmed the token.
    The token is never stored or logged; each attempt is recorded for the evaluation dashboard.
    """
    result = await verify_token(
        provider=request.provider,
        response_token=request.token,
        secret_key=request.secret_key,
        simulate_status=request.simulate_status,
        expected_hostname=request.expected_hostname,
    )
    record_verification(db, result, current_user.id)
    return result


@router.get("/verification/providers")
async def list_verification_providers(current_user: User = Depends(require_operator)):
    """Supported providers, their official endpoints and the kinds of scenarios available."""
    return {
        "success": True,
        "providers": [
            {"provider": k, "label": v["label"], "endpoint": v["url"],
             "official_test_secrets": len(v["test_secrets"])}
            for k, v in PROVIDERS.items()
        ],
        "simulation_scenarios": sorted(SIMULATIONS),
    }


@router.get("/verification/records")
async def list_verification_records(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    rows = db.query(VerificationRecord).order_by(VerificationRecord.created_at.desc()).limit(limit).all()
    return {"success": True, "total": db.query(VerificationRecord).count(), "records": [r.to_dict() for r in rows]}
