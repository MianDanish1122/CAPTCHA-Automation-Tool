import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Any
from urllib.parse import urlparse

from app.database import SessionLocal
from app.models import (
    HumanReviewRecord,
    CaptchaIntelligenceRecord,
    OcrEvaluationRecord,
    generate_uuid,
)
from app.services.browser_scanner import (
    PROVIDER_PATTERNS,
    UNKNOWN_CHALLENGE_PATTERNS,
    detect_captcha_in_html,
)
from app.services.ocr_service import (
    preprocess_captcha_image,
    run_ocr,
)
from app.services.token_verifier import verify_recaptcha_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server-side validation of client-asserted modes
# ---------------------------------------------------------------------------
# Published provider TEST site keys. Only a page whose every site key is one of these can be
# treated as an "official test" integration; the client flag alone is never trusted.
OFFICIAL_TEST_SITEKEYS: dict[str, set[str]] = {
    "google_recaptcha": {"6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"},
    "hcaptcha": {
        "10000000-ffff-ffff-ffff-000000000001",
        "20000000-ffff-ffff-ffff-000000000002",
        "30000000-ffff-ffff-ffff-000000000003",
    },
    "cloudflare_turnstile": {
        "1x00000000000000000000AA",
        "2x00000000000000000000AB",
        "1x00000000000000000000BB",
        "2x00000000000000000000BB",
        "3x00000000000000000000FF",
    },
}
_SITEKEY_PATTERNS = [
    re.compile(r"data-sitekey\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE),
    re.compile(r"sitekey\s*:\s*[\"']([^\"']+)[\"']", re.IGNORECASE),
    re.compile(r"recaptcha/(?:api|enterprise)\.js\?[^\"'\s>]*render=([A-Za-z0-9_\-]{20,})", re.IGNORECASE),
]
_PROVIDER_CLASSES = {"google_recaptcha", "hcaptcha", "cloudflare_turnstile", "unknown_challenge"}


def extract_sitekeys(html: Optional[str]) -> list[str]:
    keys: list[str] = []
    for pattern in _SITEKEY_PATTERNS:
        for match in pattern.findall(html or ""):
            if match not in keys:
                keys.append(match)
    return keys


def validate_client_assertions(
    html: Optional[str],
    title: Optional[str],
    image_bytes: Optional[bytes],
    is_synthetic: bool,
    is_official_test: bool,
) -> dict[str, Any]:
    """
    Decide which client-supplied mode flags the SERVER will honor, based on content.

      * is_synthetic      -> requires a valid, size-bounded image AND a page that carries no
                             real provider / interstitial markers (so the flag cannot be used to
                             hide a genuine third-party CAPTCHA from the human-review queue).
      * is_official_test  -> requires a detected provider whose site keys are ALL published
                             provider test keys (the flag cannot downgrade review of a real,
                             production-keyed widget).
    Returns the effective booleans plus a human-readable decision record for the response.
    """
    result = {
        "is_synthetic": {"requested": bool(is_synthetic), "accepted": False, "reason": None},
        "is_official_test": {"requested": bool(is_official_test), "accepted": False, "reason": None},
    }
    detected = classify_captcha(html=html, title=title)  # flags deliberately NOT passed

    if is_synthetic:
        if not image_bytes:
            result["is_synthetic"]["reason"] = "No valid image supplied; flag ignored."
        elif detected["classification"] in _PROVIDER_CLASSES:
            result["is_synthetic"]["reason"] = (
                f"Page contains {detected['classification']} markers; synthetic mode refused so the "
                "page is handled as a real third-party challenge."
            )
        else:
            result["is_synthetic"]["accepted"] = True
            result["is_synthetic"]["reason"] = "Valid image and no third-party provider markers."

    if is_official_test:
        provider = detected["classification"]
        official = OFFICIAL_TEST_SITEKEYS.get(provider)
        keys = extract_sitekeys(html)
        if not official:
            result["is_official_test"]["reason"] = "No supported provider detected; flag ignored."
        elif not keys:
            result["is_official_test"]["reason"] = "No site key found in the page; cannot confirm test mode."
        elif all(k in official for k in keys):
            result["is_official_test"]["accepted"] = True
            result["is_official_test"]["reason"] = f"All site keys are published {provider} test keys."
        else:
            result["is_official_test"]["reason"] = (
                "Page uses a non-test site key; official test mode refused, routed to human review."
            )

    return result


def classify_captcha(
    html: Optional[str] = None,
    title: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    is_synthetic: bool = False,
    is_official_test: bool = False,
) -> dict[str, Any]:
    """
    Examine DOM HTML, document title, or image input to classify CAPTCHA presence,
    distinguishing active widgets, passive scripts, invisible tokens, and unknown interstitials.

    Supported classifications:
      - no_captcha
      - synthetic_text_captcha
      - google_recaptcha
      - hcaptcha
      - cloudflare_turnstile
      - unknown_challenge
    """
    html_str = html or ""
    title_str = title or ""
    html_lower = html_str.lower()
    title_lower = title_str.lower()

    evidence: dict[str, Any] = {
        "script_markers": [],
        "dom_elements": [],
        "interstitial_signals": [],
        "heuristics": [],
    }

    # 1. Synthetic Text CAPTCHA Check (Owned / Local OCR)
    if is_synthetic or (image_bytes and not html_str):
        evidence["heuristics"].append("Synthetic distorted text CAPTCHA image provided for local OCR analysis")
        return {
            "classification": "synthetic_text_captcha",
            "provider": "synthetic_ocr",
            "challenge_type": "synthetic_distortion_image",
            "is_active_challenge": True,
            "detection_confidence": 0.95,
            "detection_evidence": evidence,
            "handling_strategy": "ocr_inference",
            "human_review_required": False,
            "processing_status": "ocr_evaluable",
            "explanation": "Owned or locally synthesized text CAPTCHA suitable for OCR preprocessing.",
        }

    # 2. Check for Anti-bot Interstitial Challenge Screens (Cloudflare, Datadome, PerimeterX)
    has_unknown = any(
        pattern in html_lower or pattern in title_lower
        for pattern in UNKNOWN_CHALLENGE_PATTERNS
    )
    if has_unknown:
        matched = [p for p in UNKNOWN_CHALLENGE_PATTERNS if p in html_lower or p in title_lower]
        evidence["interstitial_signals"].extend(matched)
        return {
            "classification": "unknown_challenge",
            "provider": "unknown_anti_bot",
            "challenge_type": "anti_bot_interstitial",
            "is_active_challenge": True,
            "detection_confidence": 0.90,
            "detection_evidence": evidence,
            "handling_strategy": "manual_investigation",
            "human_review_required": True,
            "processing_status": "manual_investigation_required",
            "explanation": "Anti-bot challenge interstitial detected. Automated bypass prohibited; flagged for operator review.",
        }

    # 3. Google reCAPTCHA
    has_recaptcha_script = any(p in html_lower for p in PROVIDER_PATTERNS["google_recaptcha"])
    if has_recaptcha_script:
        evidence["script_markers"].append("google_recaptcha_script")
        has_widget = "g-recaptcha" in html_lower
        is_invisible = ('data-size="invisible"' in html_lower or "data-size='invisible'" in html_lower
                        or "grecaptcha.execute" in html_lower)

        if is_invisible:
            evidence["heuristics"].append("invisible reCAPTCHA token execution (data-size=invisible or grecaptcha.execute)")
            challenge_type = "invisible"
            is_active = False
            confidence = 0.95
        elif has_widget:
            evidence["dom_elements"].append("g-recaptcha container element")
            challenge_type = "v2_checkbox"
            is_active = True
            confidence = 0.98
        else:
            evidence["heuristics"].append("Passive vendor script without active DOM container")
            challenge_type = "passive_script"
            is_active = False
            confidence = 0.80

        strategy = "official_token_verify" if is_official_test else "queue_for_human_review"
        human_review = not is_official_test

        return {
            "classification": "google_recaptcha",
            "provider": "google_recaptcha",
            "challenge_type": challenge_type,
            "is_active_challenge": is_active,
            "detection_confidence": confidence,
            "detection_evidence": evidence,
            "handling_strategy": strategy,
            "human_review_required": human_review,
            "processing_status": "pending_human_review" if human_review else "official_test_ready",
            "explanation": f"Google reCAPTCHA ({challenge_type}) detected. Interactive challenges mandate operator review.",
        }

    # 4. hCaptcha
    has_hcaptcha_script = any(p in html_lower for p in PROVIDER_PATTERNS["hcaptcha"])
    if has_hcaptcha_script:
        evidence["script_markers"].append("hcaptcha_script")
        has_widget = "h-captcha" in html_lower
        is_invisible = 'data-size="invisible"' in html_lower or "data-size='invisible'" in html_lower

        if is_invisible:
            evidence["heuristics"].append("invisible hCaptcha token execution")
            challenge_type = "invisible"
            is_active = False
            confidence = 0.95
        elif has_widget:
            evidence["dom_elements"].append("h-captcha container element")
            challenge_type = "hcaptcha_checkbox"
            is_active = True
            confidence = 0.98
        else:
            challenge_type = "passive_script"
            is_active = False
            confidence = 0.80

        return {
            "classification": "hcaptcha",
            "provider": "hcaptcha",
            "challenge_type": challenge_type,
            "is_active_challenge": is_active,
            "detection_confidence": confidence,
            "detection_evidence": evidence,
            "handling_strategy": "queue_for_human_review",
            "human_review_required": True,
            "processing_status": "pending_human_review",
            "explanation": f"hCaptcha ({challenge_type}) detected. Third-party solving prohibited; requires human operator verification.",
        }

    # 5. Cloudflare Turnstile
    has_turnstile_script = any(p in html_lower for p in PROVIDER_PATTERNS["cloudflare_turnstile"])
    has_turnstile_dom = "cf-turnstile" in html_lower
    if has_turnstile_script or has_turnstile_dom:
        if has_turnstile_script:
            evidence["script_markers"].append("cloudflare_turnstile_script")
        if has_turnstile_dom:
            evidence["dom_elements"].append("cf-turnstile container element")

        is_active = has_turnstile_dom
        challenge_type = "turnstile_managed" if is_active else "turnstile_invisible"
        confidence = 0.95 if is_active else 0.85

        return {
            "classification": "cloudflare_turnstile",
            "provider": "cloudflare_turnstile",
            "challenge_type": challenge_type,
            "is_active_challenge": is_active,
            "detection_confidence": confidence,
            "detection_evidence": evidence,
            "handling_strategy": "queue_for_human_review",
            "human_review_required": True,
            "processing_status": "pending_human_review",
            "explanation": f"Cloudflare Turnstile ({challenge_type}) detected. Automated bypass prohibited; queued for human review.",
        }

    # 6. No CAPTCHA Detected
    return {
        "classification": "no_captcha",
        "provider": "none",
        "challenge_type": "none",
        "is_active_challenge": False,
        "detection_confidence": 0.95,
        "detection_evidence": evidence,
        "handling_strategy": "mark_completed",
        "human_review_required": False,
        "processing_status": "completed",
        "explanation": "No known CAPTCHA provider markers, widgets, or anti-bot interstitials detected on this page.",
    }


async def execute_handling_strategy(
    classification_result: dict[str, Any],
    page_url: str = "http://localhost/demo",
    scan_id: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    response_token: Optional[str] = None,
    db = None,
) -> dict[str, Any]:
    """
    Execute handling workflow based on CAPTCHA classification:
      A. No CAPTCHA -> Mark inspection completed
      B. Synthetic text CAPTCHA -> Run OCR service on owned/synthetic image
      C. Official test CAPTCHA -> Run token verification service
      D. Third-party CAPTCHA -> Create persistent HumanReviewRecord (human_review_required=True)
      E. Unknown challenge -> Create persistent HumanReviewRecord (manual_investigation)
    """
    close_db_when_done = False
    if db is None:
        db = SessionLocal()
        close_db_when_done = True

    try:
        strategy = classification_result.get("handling_strategy")
        classification = classification_result.get("classification")
        provider = classification_result.get("provider", "unknown")
        challenge_type = classification_result.get("challenge_type", "unknown")

        # Persist intelligence record
        intel_rec = CaptchaIntelligenceRecord(
            scan_id=scan_id,
            page_url=page_url,
            classification=classification,
            provider=provider,
            challenge_type=challenge_type,
            is_active_challenge=classification_result.get("is_active_challenge", False),
            detection_confidence=classification_result.get("detection_confidence", 0.0),
            detection_evidence=json.dumps(classification_result.get("detection_evidence", {})),
            handling_strategy=strategy,
            human_review_required=classification_result.get("human_review_required", False),
            processing_status=classification_result.get("processing_status", "completed"),
        )
        db.add(intel_rec)
        db.commit()

        # Workflow Decision A: No CAPTCHA
        if strategy == "mark_completed":
            return {
                "success": True,
                "strategy_applied": "mark_completed",
                "classification": classification,
                "human_review_required": False,
                "review_id": None,
                "status": "completed",
                "message": "Inspection marked completed. No CAPTCHA challenge present.",
            }

        # Workflow Decision B: Synthetic Text CAPTCHA (OCR)
        elif strategy == "ocr_inference":
            if not image_bytes:
                from app.services.ocr_service import generate_synthetic_captcha
                image_bytes, _ = generate_synthetic_captcha(length=5)

            clean_img, _ = preprocess_captcha_image(image_bytes)
            ocr_res = run_ocr(clean_img)

            ocr_eval = OcrEvaluationRecord(
                ground_truth="SYNTHETIC",
                predicted_text=ocr_res.get("predicted_text", ""),
                exact_match=False,
                character_accuracy=0.0,
                confidence=ocr_res.get("confidence", 0.0),
                duration_ms=ocr_res.get("ocr_duration_ms", 0.0),
                ocr_engine=ocr_res.get("ocr_engine", "Tesseract OCR v5.5.0"),
            )
            db.add(ocr_eval)
            db.commit()

            return {
                "success": True,
                "strategy_applied": "ocr_inference",
                "classification": classification,
                "human_review_required": False,
                "ocr_result": ocr_res,
                "status": "ocr_completed",
                "message": "Synthetic text CAPTCHA evaluated via computer vision and OCR.",
            }

        # Workflow Decision C: Official Token Verification
        elif strategy == "official_token_verify":
            token_res = await verify_recaptcha_token(response_token or "VALID_TEST_RESPONSE")
            return {
                "success": True,
                "strategy_applied": "official_token_verify",
                "classification": classification,
                "human_review_required": False,
                "token_verification": token_res,
                "status": "token_verified" if token_res.get("success") else "verification_failed",
                "message": "Verified against official provider test endpoint.",
            }

        # Workflow Decision D: Third-Party CAPTCHA (Queue for Human Review)
        elif strategy == "queue_for_human_review":
            review = HumanReviewRecord(
                scan_id=scan_id,
                page_url=page_url,
                captcha_provider=provider,
                challenge_type=challenge_type,
                reason_for_review=(
                    f"Active {provider} ({challenge_type}) detected. Third-party CAPTCHA puzzles "
                    f"cannot be automatically solved or bypassed; requires human review."
                ),
                review_status="pending",
            )
            db.add(review)
            db.commit()

            return {
                "success": True,
                "strategy_applied": "queue_for_human_review",
                "classification": classification,
                "human_review_required": True,
                "review_id": review.id,
                "review_status": "pending",
                "status": "queued_for_review",
                "message": (
                    f"Third-party challenge ({provider}) detected. Persistent review record "
                    f"created ({review.id}). Automated solving is not permitted."
                ),
            }

        # Workflow Decision E: Unknown Challenge (Manual Investigation)
        elif strategy == "manual_investigation":
            review = HumanReviewRecord(
                scan_id=scan_id,
                page_url=page_url,
                captcha_provider=provider,
                challenge_type=challenge_type,
                reason_for_review="Anti-bot interstitial or unknown challenge screen detected. Manual investigation required.",
                review_status="pending",
            )
            db.add(review)
            db.commit()

            return {
                "success": True,
                "strategy_applied": "manual_investigation",
                "classification": classification,
                "human_review_required": True,
                "review_id": review.id,
                "review_status": "pending",
                "status": "queued_for_manual_investigation",
                "message": f"Unknown challenge detected. Persistent review record created ({review.id}).",
            }

        else:
            return {
                "success": False,
                "strategy_applied": "unknown",
                "classification": classification,
                "human_review_required": True,
                "status": "unhandled_strategy",
                "message": f"Strategy '{strategy}' is not recognized.",
            }

    finally:
        if close_db_when_done:
            db.close()
