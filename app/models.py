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
            "batch_id": self.id,
            "status": self.status,
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "successful_records": self.successful_records,
            "failed_records": self.failed_records,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
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
