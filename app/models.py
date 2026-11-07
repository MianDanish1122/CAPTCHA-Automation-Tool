import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _loads(value):
    """Parse a stored JSON text column; None / invalid text -> None (never raises into an API response)."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    status = Column(String(32), default="pending", index=True)
    # Statuses: pending, scanning, completed, failed

    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    successful_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    inspections = relationship(
        "WebsiteInspection",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="WebsiteInspection.created_at"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,          # the frontend (batch + reports pages) reads `id`; `batch_id` kept for API clients
            "batch_id": self.id,
            "status": self.status,
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "successful_records": self.successful_records,
            "failed_records": self.failed_records,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": (self.updated_at.isoformat() if self.updated_at else None)
                            if self.status in ("completed", "failed") else None,
        }


class WebsiteInspection(Base):
    __tablename__ = "website_inspections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    batch_id = Column(String(36), ForeignKey("batch_jobs.id"), nullable=False, index=True)

    company_name = Column(String(255), nullable=False)
    website_url = Column(String(1024), nullable=False)

    scan_status = Column(String(64), default="pending", index=True)
    # Statuses: pending, scanning, completed, failed, human_review_required, unsupported_challenge

    page_title = Column(String(512), nullable=True)
    contact_page_url = Column(String(1024), nullable=True)
    contact_form_found = Column(Boolean, default=False)

    captcha_detected = Column(Boolean, default=False)
    captcha_provider = Column(String(128), nullable=True)
    detection_method = Column(String(128), nullable=True)
    is_active_challenge = Column(Boolean, default=False)
    human_review_required = Column(Boolean, default=False)

    error_details = Column(Text, nullable=True)
    inspection_duration_ms = Column(Float, default=0.0)

    # ---- real-world QA additions (all nullable / defaulted; see migration 8a01realworldqa) ----
    source_row = Column(Text, nullable=True)            # JSON: the ORIGINAL CSV row, every column preserved
    expected_captcha_raw = Column(String(128), nullable=True)   # the CSV "Captcha" cell as written
    expected_captcha = Column(String(40), nullable=True)        # normalised label (recaptcha_v2, none, ...)
    expected_contact_page = Column(String(1024), nullable=True) # CSV "Contact Page" URL
    platform = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    state = Column(String(64), nullable=True)
    category = Column(String(128), nullable=True)
    captcha_subtype = Column(String(40), nullable=True)
    widget_state = Column(String(24), nullable=True)
    widget_loaded = Column(Boolean, default=False)
    result_category = Column(String(24), nullable=True, index=True)  # match|mismatch|not_detected|not_accessible|not_verified
    robots_status = Column(String(24), nullable=True)           # allowed|disallowed|unavailable|blocked_by_challenge
    form_probe = Column(Text, nullable=True)            # JSON: field inventory (no values, no tokens)
    evidence = Column(Text, nullable=True)              # JSON: blocked resources, provider requests, settle timing
    screenshot_path = Column(String(512), nullable=True)

    created_at = Column(DateTime, default=utc_now)

    batch = relationship("BatchJob", back_populates="inspections")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "company_name": self.company_name,
            "website_url": self.website_url,
            "scan_status": self.scan_status,
            "page_title": self.page_title,
            "contact_page_url": self.contact_page_url,
            "contact_form_found": self.contact_form_found,
            "captcha_detected": self.captcha_detected,
            "captcha_provider": self.captcha_provider,
            "detection_method": self.detection_method,
            "is_active_challenge": self.is_active_challenge,
            "human_review_required": self.human_review_required,
            "error_details": self.error_details,
            "inspection_duration_ms": round(self.inspection_duration_ms, 2),
            "expected_captcha": self.expected_captcha,
            "expected_captcha_raw": self.expected_captcha_raw,
            "expected_contact_page": self.expected_contact_page,
            "platform": self.platform,
            "city": self.city,
            "state": self.state,
            "category": self.category,
            "captcha_subtype": self.captcha_subtype,
            "widget_state": self.widget_state,
            "widget_loaded": bool(self.widget_loaded),
            "result_category": self.result_category,
            "robots_status": self.robots_status,
            "screenshot_path": self.screenshot_path,
            "evidence": _loads(self.evidence),
            "form_probe": _loads(self.form_probe),
            "source_row": _loads(self.source_row),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UrlScan(Base):
    __tablename__ = "url_scans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    submitted_url = Column(String(1024), nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    status = Column(String(32), default="pending", index=True)
    # Statuses: pending, crawling, completed, failed

    pages_crawled = Column(Integer, default=0)
    contact_pages_found = Column(Integer, default=0)
    captcha_detected = Column(Boolean, default=False)
    captcha_providers = Column(String(255), nullable=True)

    error_message = Column(Text, nullable=True)
    crawl_duration_ms = Column(Float, default=0.0)

    created_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    pages = relationship(
        "DiscoveredPage",
        back_populates="scan",
        cascade="all, delete-orphan",
        order_by="DiscoveredPage.created_at"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scan_id": self.id,
            "submitted_url": self.submitted_url,
            "domain": self.domain,
            "status": self.status,
            "pages_crawled": self.pages_crawled,
            "contact_pages_found": self.contact_pages_found,
            "captcha_detected": self.captcha_detected,
            "captcha_providers": [p.strip() for p in self.captcha_providers.split(",") if p.strip()] if self.captcha_providers else [],
            "error_message": self.error_message,
            "crawl_duration_ms": round(self.crawl_duration_ms, 2) if self.crawl_duration_ms else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DiscoveredPage(Base):
    __tablename__ = "discovered_pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scan_id = Column(String(36), ForeignKey("url_scans.id"), nullable=False, index=True)

    url = Column(String(1024), nullable=False)
    depth = Column(Integer, default=0)
    page_title = Column(String(512), nullable=True)
    canonical_url = Column(String(1024), nullable=True)

    classification = Column(String(32), default="unknown", index=True)
    # Classifications: contact_page, support_page, general_page, unknown
    confidence_score = Column(Float, default=0.0)
    evidence = Column(Text, nullable=True)  # JSON-encoded evidence dictionary

    contact_form_found = Column(Boolean, default=False)
    forms_count = Column(Integer, default=0)
    has_inputs = Column(Boolean, default=False)
    has_textarea = Column(Boolean, default=False)

    captcha_detected = Column(Boolean, default=False)
    captcha_provider = Column(String(128), nullable=True)
    is_active_challenge = Column(Boolean, default=False)
    human_review_required = Column(Boolean, default=False)
    detection_method = Column(String(128), nullable=True)

    screenshot_path = Column(String(512), nullable=True)
    http_status = Column(Integer, default=200)
    crawl_duration_ms = Column(Float, default=0.0)

    created_at = Column(DateTime, default=utc_now)

    scan = relationship("UrlScan", back_populates="pages")

    def to_dict(self) -> dict:
        parsed_evidence = None
        if self.evidence:
            try:
                parsed_evidence = json.loads(self.evidence)
            except Exception:
                parsed_evidence = self.evidence

        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "url": self.url,
            "depth": self.depth,
            "page_title": self.page_title,
            "canonical_url": self.canonical_url,
            "classification": self.classification,
            "confidence_score": round(self.confidence_score, 2) if self.confidence_score else 0.0,
            "evidence": parsed_evidence,
            "contact_form_found": self.contact_form_found,
            "forms_count": self.forms_count,
            "has_inputs": self.has_inputs,
            "has_textarea": self.has_textarea,
            "captcha_detected": self.captcha_detected,
            "captcha_provider": self.captcha_provider,
            "is_active_challenge": self.is_active_challenge,
            "human_review_required": self.human_review_required,
            "detection_method": self.detection_method,
            "screenshot_path": self.screenshot_path,
            "http_status": self.http_status,
            "crawl_duration_ms": round(self.crawl_duration_ms, 2) if self.crawl_duration_ms else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HumanReviewRecord(Base):
    __tablename__ = "human_reviews"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scan_id = Column(String(36), nullable=True, index=True)
    page_url = Column(String(1024), nullable=False)
    captcha_provider = Column(String(128), nullable=False)
    challenge_type = Column(String(64), default="interactive_widget")
    reason_for_review = Column(Text, nullable=False)
    review_status = Column(String(32), default="pending", index=True)
    # Statuses: pending, approved, rejected, manually_verified

    operator_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    resolved_at = Column(DateTime, nullable=True)
    # Identity of the most recent decision-maker (full history in ReviewDecision)
    reviewed_by_id = Column(String(36), nullable=True)
    reviewed_by_username = Column(String(64), nullable=True)
    decision_count = Column(Integer, default=0, nullable=False, server_default="0")
    # batch workflow link (the single-site crawler uses scan_id)
    inspection_id = Column(String(36), nullable=True, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "inspection_id": self.inspection_id,
            "page_url": self.page_url,
            "captcha_provider": self.captcha_provider,
            "challenge_type": self.challenge_type,
            "reason_for_review": self.reason_for_review,
            "review_status": self.review_status,
            "operator_notes": self.operator_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "reviewed_by": self.reviewed_by_username,
            "decision_count": self.decision_count or 0,
        }


class ReviewDecision(Base):
    """Append-only history of every decision made on a human review record."""
    __tablename__ = "review_decisions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    review_id = Column(String(36), ForeignKey("human_reviews.id"), nullable=False, index=True)
    decided_at = Column(DateTime, default=utc_now, nullable=False)
    decided_by_id = Column(String(36), nullable=False)
    decided_by_username = Column(String(64), nullable=False)
    decided_by_role = Column(String(32), nullable=True)
    previous_status = Column(String(32), nullable=False)
    new_status = Column(String(32), nullable=False)
    notes = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    request_id = Column(String(64), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "review_id": self.review_id,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by_username,
            "decided_by_id": self.decided_by_id,
            "decided_by_role": self.decided_by_role,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "notes": self.notes,
            "request_id": self.request_id,
        }


class CaptchaIntelligenceRecord(Base):
    __tablename__ = "captcha_intelligence"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scan_id = Column(String(36), nullable=True, index=True)
    page_url = Column(String(1024), nullable=True)
    classification = Column(String(64), nullable=False, index=True)
    # Classifications: no_captcha, synthetic_text_captcha, google_recaptcha, hcaptcha, cloudflare_turnstile, unknown_challenge

    provider = Column(String(64), nullable=False)
    challenge_type = Column(String(64), nullable=True)
    is_active_challenge = Column(Boolean, default=False)
    detection_confidence = Column(Float, default=0.0)
    detection_evidence = Column(Text, nullable=True)  # JSON-encoded signals
    handling_strategy = Column(String(64), nullable=False)
    # Strategies: mark_completed, ocr_inference, official_token_verify, queue_for_human_review, manual_investigation

    human_review_required = Column(Boolean, default=False)
    processing_status = Column(String(64), default="completed")
    created_at = Column(DateTime, default=utc_now)

    def to_dict(self) -> dict:
        parsed_evidence = None
        if self.detection_evidence:
            try:
                parsed_evidence = json.loads(self.detection_evidence)
            except Exception:
                parsed_evidence = self.detection_evidence

        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "page_url": self.page_url,
            "classification": self.classification,
            "provider": self.provider,
            "challenge_type": self.challenge_type,
            "is_active_challenge": self.is_active_challenge,
            "detection_confidence": round(self.detection_confidence, 2) if self.detection_confidence else 0.0,
            "detection_evidence": parsed_evidence,
            "handling_strategy": self.handling_strategy,
            "human_review_required": self.human_review_required,
            "processing_status": self.processing_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OcrEvaluationRecord(Base):
    __tablename__ = "ocr_evaluations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ground_truth = Column(String(128), nullable=False)
    predicted_text = Column(String(128), nullable=False)
    exact_match = Column(Boolean, default=False)
    character_accuracy = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    duration_ms = Column(Float, default=0.0)
    ocr_engine = Column(String(128), default="Tesseract OCR v5.5.0")
    created_at = Column(DateTime, default=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ground_truth": self.ground_truth,
            "predicted_text": self.predicted_text,
            "exact_match": self.exact_match,
            "character_accuracy": round(self.character_accuracy, 1) if self.character_accuracy else 0.0,
            "confidence": round(self.confidence, 1) if self.confidence else 0.0,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms else 0.0,
            "ocr_engine": self.ocr_engine,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VerificationRecord(Base):
    """One CAPTCHA token verification attempt. The token itself is NEVER stored."""
    __tablename__ = "verification_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=utc_now, index=True)
    provider = Column(String(32), nullable=False, index=True)
    # provider_live | provider_test_keys | simulated | local_validation
    verification_mode = Column(String(24), nullable=False, index=True)
    scenario = Column(String(32), nullable=True)
    outcome = Column(String(40), nullable=False, index=True)
    success = Column(Boolean, default=False, nullable=False)
    provider_called = Column(Boolean, default=False, nullable=False)
    provider_verified = Column(Boolean, default=False, nullable=False)
    http_status = Column(Integer, nullable=True)
    error_codes = Column(String(255), nullable=True)
    duration_ms = Column(Float, default=0.0)
    token_source = Column(String(24), nullable=True)
    user_id = Column(String(36), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "provider": self.provider,
            "verification_mode": self.verification_mode,
            "scenario": self.scenario,
            "outcome": self.outcome,
            "success": self.success,
            "provider_called": self.provider_called,
            "provider_verified": self.provider_verified,
            "http_status": self.http_status,
            "error_codes": (self.error_codes or "").split(",") if self.error_codes else [],
            "duration_ms": round(self.duration_ms or 0.0, 2),
        }


class OcrBenchmarkRun(Base):
    """A measured OCR evaluation run over a labelled dataset split (CLI or API)."""
    __tablename__ = "ocr_benchmark_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=utc_now, index=True)
    source = Column(String(24), nullable=False)  # cli_heldout | cli_dev | api
    dataset = Column(String(64), nullable=False)
    split = Column(String(16), nullable=False, index=True)
    engine = Column(String(32), nullable=False, index=True)
    samples = Column(Integer, nullable=False)
    exact_matches = Column(Integer, nullable=False)
    exact_match_pct = Column(Float, nullable=False)
    char_accuracy_pct = Column(Float, nullable=False)
    latency_ms_mean = Column(Float, default=0.0)
    latency_ms_p95 = Column(Float, default=0.0)
    failures = Column(Integer, default=0, nullable=False)
    details = Column(Text, nullable=True)  # JSON: config, CI, environment
    user_id = Column(String(36), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "source": self.source, "dataset": self.dataset, "split": self.split, "engine": self.engine,
            "samples": self.samples, "exact_matches": self.exact_matches,
            "exact_match_pct": self.exact_match_pct, "char_accuracy_pct": self.char_accuracy_pct,
            "latency_ms_mean": self.latency_ms_mean, "latency_ms_p95": self.latency_ms_p95,
            "failures": self.failures,
            "details": json.loads(self.details) if self.details else None,
        }


class UserRole:
    ADMIN = "admin"
    OPERATOR = "operator"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), default=UserRole.OPERATOR, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Incremented to invalidate every token previously issued to this user.
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RevokedToken(Base):
    """Denylist of individually revoked JWTs (by jti) until their natural expiry."""
    __tablename__ = "revoked_tokens"

    jti = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    revoked_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    reason = Column(String(64), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    # Tamper-evidence: strictly increasing sequence + HMAC hash chain (see app/services/audit.py)
    seq = Column(Integer, nullable=True, index=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)
    key_id = Column(String(16), nullable=True)  # which HMAC key sealed this entry (supports rotation)
    timestamp = Column(DateTime, default=utc_now, index=True)
    actor_id = Column(String(36), nullable=True, index=True)
    actor_username = Column(String(64), nullable=True)
    actor_role = Column(String(32), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    ip_address = Column(String(64), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    details = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        parsed_details = None
        if self.details:
            try:
                parsed_details = json.loads(self.details)
            except Exception:
                parsed_details = self.details

        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor_id": self.actor_id,
            "actor_username": self.actor_username,
            "actor_role": self.actor_role,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "request_id": self.request_id,
            "details": parsed_details,
            "seq": self.seq,
            "entry_hash": self.entry_hash,
        }
