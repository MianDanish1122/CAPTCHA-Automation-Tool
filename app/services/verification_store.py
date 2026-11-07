"""Persist verification attempts (never the token) so dashboards report real, countable outcomes."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import VerificationRecord


def record_verification(db: Session, result: dict, user_id: Optional[str] = None) -> VerificationRecord:
    row = VerificationRecord(
        provider=result["provider"],
        verification_mode=result["verification_mode"],
        scenario=result.get("scenario"),
        outcome=result["outcome"],
        success=bool(result["success"]),
        provider_called=bool(result["provider_called"]),
        provider_verified=bool(result["provider_verified"]),
        http_status=result.get("http_status"),
        error_codes=",".join(result.get("error_codes") or [])[:255] or None,
        duration_ms=result.get("duration_ms") or 0.0,
        token_source=result.get("token_source"),
        user_id=user_id,
    )
    db.add(row)
    db.commit()
    return row
