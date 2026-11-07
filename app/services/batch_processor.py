import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from app.config import settings, BASE_DIR
from app.database import SessionLocal
from app.models import BatchJob, HumanReviewRecord, WebsiteInspection
from app.services.evaluation import categorise
from app.services.browser_scanner import inspect_website, inspect_local_demo
from app.services.job_manager import job_manager
from app.services.fixture_loader import (
    FixtureError,
    extract_fixture_name,
    is_fixture_reference,
    load_fixture_html,
)

logger = logging.getLogger(__name__)

# ---- per-host politeness: at most one inspection of the same external host per BATCH_MIN_HOST_INTERVAL_S ----
_host_next_allowed: dict[str, float] = {}
_host_lock: Optional[asyncio.Lock] = None
_host_lock_loop = None


def _is_loopback(host: str) -> bool:
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


async def wait_for_host_slot(url: str, interval: Optional[float] = None) -> float:
    """Reserve the next polite slot for this host and sleep until it. Returns seconds waited. Loopback is exempt."""
    global _host_lock, _host_lock_loop
    host = (urlparse(url).hostname or "").lower()
    interval = settings.BATCH_MIN_HOST_INTERVAL_S if interval is None else interval
    if not host or _is_loopback(host) or interval <= 0:
        return 0.0
    loop = asyncio.get_running_loop()
    if _host_lock is None or _host_lock_loop is not loop:
        _host_lock, _host_lock_loop = asyncio.Lock(), loop
    async with _host_lock:
        now = time.monotonic()
        slot = max(now, _host_next_allowed.get(host, 0.0))
        _host_next_allowed[host] = slot + interval
    delay = slot - now
    if delay > 0:
        await asyncio.sleep(delay)
    return max(delay, 0.0)


def _safe_slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)[:60].strip("_") or "site"


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
                # SAME detection engine as the single-site crawler; robots.txt first, CSV contact page first,
                # polite per-host pacing, screenshot evidence.
                waited = await wait_for_host_slot(inspection.expected_contact_page or url)
                result = await inspect_website(
                    url,
                    check_security=True,
                    expected_contact_page=inspection.expected_contact_page,
                    # under scans/<uuid>/ so the existing authenticated evidence endpoint can serve it
                    evidence_dir=settings.SCANS_EVIDENCE_DIR / inspection.batch_id,
                    evidence_name=f"{_safe_slug(inspection.company_name)}_{inspection.id[:8]}",
                    respect_robots=True,
                    probe_forms=settings.BATCH_PROBE_FORMS,
                )

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
                inspection.captcha_subtype = result.get("captcha_subtype")
                inspection.widget_state = result.get("widget_state")
                inspection.widget_loaded = bool(result.get("widget_loaded"))
                inspection.robots_status = result.get("robots_status")
                inspection.screenshot_path = result.get("screenshot_path")
                if result.get("form_probe") is not None:
                    inspection.form_probe = json.dumps(result["form_probe"], ensure_ascii=False)
                ev = dict(result.get("evidence") or {})
                ev["host_pacing_wait_s"] = round(waited, 2)
                inspection.evidence = json.dumps(ev, ensure_ascii=False)[:60000]

            # Expected-vs-detected category (fixtures use their own expectation if the CSV provided one)
            providers = [p.strip() for p in (inspection.captcha_provider or "").split(",") if p.strip()]
            cat = categorise(inspection.expected_captcha, providers, inspection.scan_status,
                             subtype=inspection.captcha_subtype)
            inspection.result_category = cat["category"]

            # Human-review record (same queue the single-site crawler feeds)
            if inspection.human_review_required and (providers or inspection.scan_status == "unsupported_challenge"):
                exists = db.query(HumanReviewRecord.id).filter(HumanReviewRecord.inspection_id == inspection.id).first()
                if not exists:
                    db.add(HumanReviewRecord(
                        inspection_id=inspection.id,
                        page_url=inspection.contact_page_url or inspection.website_url,
                        captcha_provider=", ".join(providers) if providers else "unknown_challenge",
                        challenge_type="interactive_widget" if inspection.widget_loaded else "embedded_or_deferred_widget",
                        reason_for_review=(f"Batch inspection of '{inspection.company_name}': "
                                           f"{', '.join(providers) or 'bot challenge'} "
                                           f"({inspection.captcha_subtype or 'subtype unknown'}, "
                                           f"widget {inspection.widget_state or 'n/a'}). "
                                           "A person must complete or assess it; the system never solves it."),
                        review_status="pending",
                    ))

            # Update batch statistics
            batch = db.query(BatchJob).filter(BatchJob.id == inspection.batch_id).first()
            if batch:
                batch.processed_records += 1
                if inspection.scan_status in ("completed", "captcha_detected", "no_known_captcha_detected", "unsupported_challenge") \
                        and inspection.result_category != "not_accessible":
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
    start_background: bool = True,
    owner_id: str = "system",
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
                source_row=item.get("source_row"),
                expected_captcha_raw=item.get("expected_captcha_raw"),
                expected_captcha=item.get("expected_captcha"),
                expected_contact_page=item.get("expected_contact_page"),
                platform=item.get("platform"),
                city=item.get("city"),
                state=item.get("state"),
                category=item.get("category"),
            )
            db.add(rec)

        db.commit()
        batch_id = batch.id
    finally:
        db.close()

    if start_background and websites_data:
        # Tracked + bounded (see job_manager); callers pre-check capacity with ensure_capacity().
        job_manager.spawn("batch", owner_id, run_batch_job(batch_id))

    return batch_id
