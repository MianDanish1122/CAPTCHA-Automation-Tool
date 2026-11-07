import uuid
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
