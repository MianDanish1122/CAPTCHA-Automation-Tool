# Technology Brainz — CAPTCHA Inspector
## Phase 3: Implementation & Engineering Report
### CAPTCHA Intelligence & Handling Engine

## 1. Executive Summary

Phase 3 implements an end-to-end **CAPTCHA Decision & Handling Workflow** integrated with the existing Smart Website Crawler.

Every discovered CAPTCHA is classified across all standard categories, evaluated against a clear handling strategy matrix, and managed through an auditable **Human Review Workflow**. Local synthetic OCR capabilities and official Google test-token verifications are fully operational and persisted to SQLite.

---

## 2. Files Modified & Created

| Component | File Path | Type | Key Enhancements |
| :--- | :--- | :--- | :--- |
| **Intelligence Engine** | [`app/services/captcha_intelligence.py`](file:///C:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/services/captcha_intelligence.py) | **New** | Provider classification, active vs passive detection, decision matrix, and strategy execution. |
| **Data Models** | [`app/models.py`](file:///C:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/models.py) | Modified | Added `HumanReviewRecord`, `CaptchaIntelligenceRecord`, and `OcrEvaluationRecord` models with serialization. |
| **API Endpoints** | [`app/routes/captcha.py`](file:///C:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/routes/captcha.py) | Modified | Added `/classify`, `/evaluate-handling`, `/reviews`, `/reviews/{id}`, and `PATCH /reviews/{id}`. Enhanced `/ocr-demo` with DB persistence. |
| **Smart Crawler** | [`app/services/smart_crawler.py`](file:///C:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/services/smart_crawler.py) | Modified | Automatically enqueues `HumanReviewRecord` entries during live crawling when third-party challenges are detected. |
| **Test Suite** | [`tests/test_captcha_intelligence.py`](file:///C:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/tests/test_captcha_intelligence.py) | **New** | 19 automated unit & integration tests for classification, handling workflow, reviews, and OCR. |

---

## 3. Implemented Capabilities & Decision Workflow

### 3.1 Classification Engine (`classify_captcha`)
Evaluates DOM markup, page title, or synthetic image bytes:
- `no_captcha`: Clean page without challenge indicators.
- `synthetic_text_captcha`: Owned or locally generated image for OCR evaluation.
- `google_recaptcha`: Distinguishes `v2_checkbox` (active container), `invisible` (`data-size="invisible"`), or `passive_script`.
- `hcaptcha`: Distinguishes `hcaptcha_checkbox` (active container), `invisible`, or `passive_script`.
- `cloudflare_turnstile`: Distinguishes `turnstile_managed` (active container) or `turnstile_invisible`.
- `unknown_challenge`: Interstitial challenge screens (Cloudflare "Just a moment...", Datadome, PerimeterX/HUMAN).

### 3.2 Handling Strategy Matrix (`execute_handling_strategy`)
- **Strategy A (`mark_completed`)**: Clean pages require no action.
- **Strategy B (`ocr_inference`)**: Run OpenCV preprocessing + Tesseract LSTM OCR. Persists `OcrEvaluationRecord`.
- **Strategy C (`official_token_verify`)**: Validates test tokens against Google's official server-side siteverify endpoint.
- **Strategy D (`queue_for_human_review`)**: Discovered third-party CAPTCHAs mandate `human_review_required=True`. A persistent `HumanReviewRecord` is created in SQLite with status `pending`. Automated solving or bypass is strictly forbidden.
- **Strategy E (`manual_investigation`)**: Unknown anti-bot interstitial screens are marked for manual operator investigation.

### 3.3 Human Review Queue & Status Transitions
- Enqueued records include `scan_id`, `page_url`, `captcha_provider`, `challenge_type`, `reason_for_review`, `review_status`, and `created_at`.
- Operators view the queue via `GET /api/captcha/reviews?status=pending`.
- Operators record their audit decision via `PATCH /api/captcha/reviews/{review_id}`:
  - Allowed target statuses: `approved`, `rejected`, `manually_verified`.
  - Records `operator_notes` and sets `resolved_at` UTC timestamp.
  - Manual verification is explicitly audited as an operator action, not an automated bypass.

---

## 4. API Request & Response Contracts

### 4.1 `POST /api/captcha/classify`
Inspects HTML markup, title, or synthetic image and classifies CAPTCHA presence.

**Request:**
```json
{
  "html": "<div class=\"g-recaptcha\" data-sitekey=\"6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI\"></div><script src=\"https://www.google.com/recaptcha/api.js\"></script>",
  "title": "Contact Us"
}
```

**Response:**
```json
{
  "success": true,
  "classification": "google_recaptcha",
  "provider": "google_recaptcha",
  "challenge_type": "v2_checkbox",
  "is_active_challenge": true,
  "detection_confidence": 0.98,
  "detection_evidence": {
    "script_markers": ["google_recaptcha_script"],
    "dom_elements": ["g-recaptcha container element"],
    "interstitial_signals": [],
    "heuristics": []
  },
  "handling_strategy": "queue_for_human_review",
  "human_review_required": true,
  "processing_status": "pending_human_review",
  "explanation": "Google reCAPTCHA (v2_checkbox) detected. Interactive challenges mandate operator review."
}
```

---

### 4.2 `POST /api/captcha/evaluate-handling`
Executes the handling decision workflow, creating persistent database records as required.

**Request:**
```json
{
  "html": "<div class=\"cf-turnstile\" data-sitekey=\"1x00000000000000000000AA\"></div>",
  "page_url": "https://example.com/checkout",
  "scan_id": "0d65be6e-5b82-41b0-9b8d-f2ccc0d544e8"
}
```

**Response:**
```json
{
  "success": true,
  "classification": {
    "classification": "cloudflare_turnstile",
    "provider": "cloudflare_turnstile",
    "challenge_type": "turnstile_managed",
    "is_active_challenge": true,
    "handling_strategy": "queue_for_human_review"
  },
  "handling": {
    "success": true,
    "strategy_applied": "queue_for_human_review",
    "classification": "cloudflare_turnstile",
    "human_review_required": true,
    "review_id": "f8a1c92d-45e3-4901-b541-698f12a3cd5e",
    "review_status": "pending",
    "status": "queued_for_review",
    "message": "Third-party challenge (cloudflare_turnstile) detected. Persistent review record created (f8a1c92d...). Automated solving is not permitted."
  }
}
```

---

### 4.3 `GET /api/captcha/reviews`
Retrieves human review queue with status breakdown.

**Response:**
```json
{
  "success": true,
  "total_records": 12,
  "summary": {
    "pending": 8,
    "approved": 2,
    "rejected": 1,
    "manually_verified": 1
  },
  "reviews": [
    {
      "id": "f8a1c92d-45e3-4901-b541-698f12a3cd5e",
      "scan_id": "0d65be6e-5b82-41b0-9b8d-f2ccc0d544e8",
      "page_url": "https://example.com/checkout",
      "captcha_provider": "cloudflare_turnstile",
      "challenge_type": "turnstile_managed",
      "reason_for_review": "Active cloudflare_turnstile (turnstile_managed) detected. Third-party CAPTCHA puzzles cannot be automatically solved or bypassed; requires human review.",
      "review_status": "pending",
      "operator_notes": null,
      "created_at": "2026-11-07T13:30:00Z",
      "resolved_at": null
    }
  ]
}
```

---

### 4.4 `PATCH /api/captcha/reviews/{review_id}`
Updates human review record with an operator audit decision.

**Request:**
```json
{
  "review_status": "manually_verified",
  "operator_notes": "Operator resolved Cloudflare Turnstile managed challenge manually in staging environment."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Review f8a1c92d-45e3-4901-b541-698f12a3cd5e updated to 'manually_verified'.",
  "review": {
    "id": "f8a1c92d-45e3-4901-b541-698f12a3cd5e",
    "review_status": "manually_verified",
    "operator_notes": "Operator resolved Cloudflare Turnstile managed challenge manually in staging environment.",
    "resolved_at": "2026-11-07T13:35:12Z"
  }
}
```
