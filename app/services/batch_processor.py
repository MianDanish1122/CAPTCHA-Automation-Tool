import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings, BASE_DIR
from app.database import SessionLocal
from app.models import BatchJob, WebsiteInspection
from app.services.browser_scanner import inspect_website, inspect_local_demo
from app.services.fixture_loader import (
    FixtureError,
    extract_fixture_name,
    is_fixture_reference,
    load_fixture_html,
)

logger = logging.getLogger(__name__)


async def process_single_website(
    inspection_id: str,
    semaphore: asyncio.Semaphore,
) -> None:
    """Inspect an individual website record with concurrency bounding and DB persistence."""
    async with semaphore:
        db = SessionLocal()
        try:
            inspection = db.query(WebsiteInspection).filter(WebsiteInspection.id == inspection_id).first()
            if not inspection:
                return

            inspection.scan_status = "scanning"
            db.commit()

            url = inspection.website_url.strip()

            # Check if this is a local test fixture reference
            if is_fixture_reference(url):
                fixture_name = extract_fixture_name(url)
                try:
                    html_content = load_fixture_html(url)
                except FixtureError as fx_err:
                    logger.warning("Rejected fixture reference %r: %s", fixture_name[:80], fx_err)
                    html_content = None
                    fixture_error = str(fx_err)
                if html_content is not None:
                    result = await inspect_local_demo(html_content)
                    
                    provider_str = ", ".join(result.get("detected_providers", [])) or None
                    captcha_detected = bool(result.get("detected_providers")) or result.get("status") == "unsupported_challenge"

                    inspection.scan_status = result.get("status", "completed")
                    inspection.page_title = result.get("page_title")
                    inspection.contact_form_found = result.get("contact_form_found", False)
                    inspection.captcha_detected = captcha_detected
                    inspection.captcha_provider = provider_str
                    inspection.detection_method = result.get("detection_method", "local_fixture_inspection")
                    inspection.is_active_challenge = result.get("is_active_challenge", False)
                    inspection.human_review_required = result.get("human_review_required", False)
                    inspection.inspection_duration_ms = result.get("inspection_duration_ms", 0.0)
                    inspection.error_details = result.get("error")
                else:
                    inspection.scan_status = "failed"
                    inspection.error_details = f"Fixture rejected: {fixture_error}"
            else:
                # Live or external website inspection
                result = await inspect_website(url, check_security=True)
                
                inspection.scan_status = result.get("scan_status", "completed")
                inspection.page_title = result.get("page_title")
                inspection.contact_page_url = result.get("contact_page_url")
                inspection.contact_form_found = result.get("contact_form_found", False)
                inspection.captcha_detected = result.get("captcha_detected", False)
                inspection.captcha_provider = result.get("captcha_provider")
                inspection.detection_method = result.get("detection_method")
                inspection.is_active_challenge = result.get("is_active_challenge", False)
                inspection.human_review_required = result.get("human_review_required", False)
                inspection.error_details = result.get("error_details") or result.get("error")
                inspection.inspection_duration_ms = result.get("inspection_duration_ms", 0.0)

            # Update batch statistics
            batch = db.query(BatchJob).filter(BatchJob.id == inspection.batch_id).first()
            if batch:
                batch.processed_records += 1
                if inspection.scan_status in ("completed", "captcha_detected", "no_known_captcha_detected", "unsupported_challenge"):
                    batch.successful_records += 1
                else:
                    batch.failed_records += 1
                batch.updated_at = datetime.now(timezone.utc)

            db.commit()

        except Exception as e:
            db.rollback()
            try:
                inspection = db.query(WebsiteInspection).filter(WebsiteInspection.id == inspection_id).first()
                if inspection:
                    inspection.scan_status = "failed"
                    inspection.error_details = f"Unexpected processing error: {str(e)}"
                    batch = db.query(BatchJob).filter(BatchJob.id == inspection.batch_id).first()
                    if batch:
                        batch.processed_records += 1
                        batch.failed_records += 1
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()


async def run_batch_job(batch_id: str) -> None:
    """Orchestrate parallel processing of a batch job under concurrency limits."""
    db = SessionLocal()
    try:
        batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
        if not batch:
            return

        batch.status = "scanning"
        batch.updated_at = datetime.now(timezone.utc)
        db.commit()

        inspection_ids = [
            item.id for item in
            db.query(WebsiteInspection.id).filter(WebsiteInspection.batch_id == batch_id).all()
        ]
    finally:
        db.close()

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_PAGES)
    tasks = [process_single_website(iid, semaphore) for iid in inspection_ids]

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    db = SessionLocal()
    try:
        batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
        if batch:
            batch.status = "completed"
            batch.updated_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def create_batch(
    websites_data: list[dict],
    start_background: bool = True
) -> str:
    """
    Initialize a BatchJob and related WebsiteInspection records in SQLite.
    Optionally schedules execution asynchronously.
    """
    db = SessionLocal()
    try:
        batch = BatchJob(
            total_records=len(websites_data),
            status="pending",
        )
        db.add(batch)
        db.flush()

        for item in websites_data:
            rec = WebsiteInspection(
                batch_id=batch.id,
                company_name=item.get("company_name", "Unknown"),
                website_url=item.get("website_url", ""),
                scan_status="pending",
            )
            db.add(rec)

        db.commit()
        batch_id = batch.id
    finally:
        db.close()

    if start_background and websites_data:
        asyncio.create_task(run_batch_job(batch_id))

    return batch_id
