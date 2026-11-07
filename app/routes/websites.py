import asyncio
import json
from typing import Optional
from urllib.parse import urlparse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    BatchJob,
    WebsiteInspection,
    UrlScan,
    DiscoveredPage,
    HumanReviewRecord,
    CaptchaIntelligenceRecord,
    User,
    UserRole,
    generate_uuid,
)
from app.services.csv_importer import import_websites, normalise_expected_captcha
from app.services.browser_scanner import inspect_local_demo
from app.services.batch_processor import create_batch
from app.services.report_generator import (
    build_evaluation, evaluation_csv, evaluation_markdown, generate_batch_csv_report,
)
from app.services.security_guard import SecurityGuard
from app.services.smart_crawler import SmartCrawler
from app.services.auth_service import require_operator, require_admin, log_audit_event
from app.services.rate_limiter import rate_limit
from app.services.job_manager import job_manager, JobLimitExceeded
from app.services.client_ip import get_client_ip
from app.services.audit import redact_url

router = APIRouter(
    prefix="/api/websites",
    tags=["Website Inspection & Batches"],
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_DEFAULT_PER_MIN, window_seconds=60, scope="api_default"))],
)

compute_limit = rate_limit(max_requests=settings.RATE_LIMIT_COMPUTE_PER_MIN, window_seconds=60, scope="compute")

MAX_FILE_SIZE = settings.MAX_CSV_SIZE_BYTES


def _is_http_url(value: str) -> bool:
    p = urlparse(value)
    return p.scheme in ("http", "https") and bool(p.hostname) and not p.username and not p.password


# -----------------------------
# Request Models
# -----------------------------

class DemoInspectionRequest(BaseModel):
    html: str = Field(min_length=1, max_length=settings.MAX_HTML_CHARS)


class DemoPage(BaseModel):
    company_name: str = Field(min_length=1, max_length=120)
    html: str = Field(min_length=1, max_length=settings.MAX_HTML_CHARS)


class BatchInspectionRequest(BaseModel):
    pages: list[DemoPage] = Field(min_length=1, max_length=20)


class WebsiteScanItem(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    website_url: str = Field(min_length=1, max_length=1024)
    # Optional CSV context (returned by /import and sent back unchanged when the batch is launched manually)
    expected_captcha_raw: Optional[str] = Field(default=None, max_length=128)
    expected_contact_page: Optional[str] = Field(default=None, max_length=1024)
    platform: Optional[str] = Field(default=None, max_length=128)
    city: Optional[str] = Field(default=None, max_length=128)
    state: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = Field(default=None, max_length=128)
    source_row: Optional[str] = Field(default=None, max_length=20000)


class ScanBatchRequest(BaseModel):
    websites: list[WebsiteScanItem] = Field(min_length=1, max_length=300)


class UrlInspectionRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1024, description="Target website URL to inspect and crawl")
    max_pages: Optional[int] = Field(default=10, ge=1, le=20, description="Maximum pages to crawl for the domain")
    max_depth: Optional[int] = Field(default=2, ge=0, le=3, description="Maximum link crawl depth")
    background: Optional[bool] = Field(default=False, description="Run crawler asynchronously in background")
    allow_loopback: Optional[bool] = Field(default=False, description="Server-controlled: Ignored unless ALLOW_DEV_LOOPBACK is enabled on server")


# -----------------------------
# 1. CSV Import Endpoint
# -----------------------------

@router.post(
    "/import",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_BATCH_PER_MIN, window_seconds=60, scope="import_csv"))]
)
async def upload_csv(
    file: UploadFile = File(...),
    auto_scan: bool = Query(False, description="Automatically trigger batch scan for valid records"),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
    req: Request = None,
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file."
        )

    content = await file.read(MAX_FILE_SIZE + 1)

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Maximum CSV size is {MAX_FILE_SIZE // (1024 * 1024)} MB."
        )

    result = import_websites(content)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )

    valid_websites = result.get("websites", [])
    invalid_rows = result.get("invalid_rows", len(result.get("errors", [])))
    total_rows = len(valid_websites) + invalid_rows

    # Enforce maximum row count protection
    if total_rows > settings.MAX_CSV_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"CSV row count ({total_rows}) exceeds maximum permitted limit of {settings.MAX_CSV_ROWS} rows."
        )

    result["valid_count"] = len(valid_websites)
    result["invalid_count"] = invalid_rows
    result["total_rows"] = total_rows
    result["message"] = f"CSV validated successfully ({len(valid_websites)} valid, {invalid_rows} invalid)."

    batch_id = None
    if auto_scan and result.get("websites"):
        try:
            job_manager.ensure_capacity("batch", current_user.id)
        except JobLimitExceeded as exc:
            raise exc.to_http()
        batch_id = create_batch(result["websites"], start_background=True, owner_id=current_user.id)
        result["batch_id"] = batch_id
        result["batch_status"] = "pending"

    # Audit logging
    log_audit_event(
        db=db,
        action="csv.import",
        actor=current_user,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID") if req else None,
        details={"filename": file.filename, "valid": len(valid_websites), "invalid": invalid_rows}
    )

    return result


# -----------------------------
# 2. Single Demo Inspection
# -----------------------------

@router.post("/inspect-demo", dependencies=[Depends(compute_limit)])
async def inspect_demo(
    request: DemoInspectionRequest,
    current_user: User = Depends(require_operator),
):
    result = await inspect_local_demo(request.html)
    return result


# -----------------------------
# 3. Batch Demo Inspection
# -----------------------------

@router.post("/inspect-demo-batch", dependencies=[Depends(compute_limit)])
async def inspect_demo_batch(
    request: BatchInspectionRequest,
    current_user: User = Depends(require_operator),
):
    results = []

    for page_data in request.pages:
        try:
            result = await inspect_local_demo(page_data.html)
            results.append({
                "company_name": page_data.company_name,
                **result
            })
        except Exception:
            results.append({
                "company_name": page_data.company_name,
                "success": False,
                "status": "inspection_failed",
                "detected_providers": [],
                "error": "Unable to inspect this demo page."
            })

    total = len(results)
    captcha_detected = sum(
        1 for item in results
        if item.get("status") in ("captcha_detected", "unsupported_challenge")
    )
    no_captcha = sum(
        1 for item in results
        if item.get("status") == "no_known_captcha_detected"
    )
    failed = sum(
        1 for item in results
        if not item.get("success", False)
    )

    return {
        "success": True,
        "summary": {
            "total_pages": total,
            "captcha_detected": captcha_detected,
            "no_captcha_detected": no_captcha,
            "inspection_failed": failed
        },
        "results": results
    }


# -----------------------------
# 4. Batch Scanning Endpoints
# -----------------------------

@router.post(
    "/scan-batch",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_BATCH_PER_MIN, window_seconds=60, scope="scan_batch"))]
)
async def scan_batch(
    request: ScanBatchRequest,
    background: bool = Query(True, description="Process batch in background"),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
    req: Request = None,
):
    """
    Initiate an asynchronous batch scan for up to 300 website records.
    Controlled concurrency and SSRF security policies are applied.
    """
    if len(request.websites) > settings.MAX_CSV_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds maximum limit of {settings.MAX_CSV_ROWS} websites."
        )

    items = []
    for item in request.websites:
        page = (item.expected_contact_page or "").strip() or None
        if page and not _is_http_url(page):
            page = None  # ignored; page discovery is used instead
        src = None
        if item.source_row:
            try:
                parsed_src = json.loads(item.source_row)
                src = item.source_row if isinstance(parsed_src, dict) else None
            except ValueError:
                src = None
        items.append({
            "company_name": item.company_name,
            "website_url": item.website_url,
            "expected_captcha_raw": item.expected_captcha_raw,
            # always normalised server-side; a client-supplied label is never trusted
            "expected_captcha": normalise_expected_captcha(item.expected_captcha_raw),
            "expected_contact_page": page,
            "platform": item.platform, "city": item.city, "state": item.state, "category": item.category,
            "source_row": src,
        })
    if background:
        try:
            job_manager.ensure_capacity("batch", current_user.id)
        except JobLimitExceeded as exc:
            raise exc.to_http()
    batch_id = create_batch(items, start_background=background, owner_id=current_user.id)

    log_audit_event(
        db=db,
        action="batch.create",
        actor=current_user,
        resource_type="website_batch",
        resource_id=batch_id,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID") if req else None,
        details={"total_records": len(items)}
    )

    return {
        "success": True,
        "batch_id": batch_id,
        "total_records": len(items),
        "status": "pending",
        "message": f"Batch scan job {batch_id} queued successfully."
    }


@router.get("/batches/{batch_id}")
async def get_batch_status(
    batch_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Retrieve execution status and summary counters for a batch job."""
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    return {
        "success": True,
        "batch": batch.to_dict()
    }


@router.get("/batches/{batch_id}/results")
async def get_batch_results(
    batch_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Retrieve itemized website inspection results for a batch job."""
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    inspections = db.query(WebsiteInspection).filter(WebsiteInspection.batch_id == batch_id).all()

    return {
        "success": True,
        "batch_id": batch_id,
        "status": batch.status,
        "total_records": batch.total_records,
        "processed_records": batch.processed_records,
        "results": [item.to_dict() for item in inspections]
    }


@router.get("/batches/{batch_id}/report")
async def download_batch_report(
    batch_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Generate and download a CSV compliance report for the specified batch."""
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    inspections = db.query(WebsiteInspection).filter(WebsiteInspection.batch_id == batch_id).all()
    if not inspections:
        raise HTTPException(status_code=400, detail="Batch contains no inspection records to report.")

    filename = f"captcha_audit_report_{batch_id[:8]}.csv"
    _, report_path = generate_batch_csv_report(inspections, save_to_file=True, filename=filename)

    return FileResponse(
        path=str(report_path),
        filename=filename,
        media_type="text/csv"
    )


def _batch_inspections(db: Session, batch_id: str):
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")
    return batch, db.query(WebsiteInspection).filter(WebsiteInspection.batch_id == batch_id).all()


@router.get("/batches/{batch_id}/evaluation")
async def get_batch_evaluation(
    batch_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Expected-vs-detected CAPTCHA evaluation: per-site rows and eligible-only summary metrics."""
    batch, inspections = _batch_inspections(db, batch_id)
    ev = build_evaluation(inspections)
    return {"success": True, "batch_id": batch_id, "status": batch.status,
            "processed_records": batch.processed_records, "total_records": batch.total_records, **ev}


@router.get("/batches/{batch_id}/evaluation.{fmt}")
async def download_batch_evaluation(
    batch_id: str,
    fmt: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Download the expected-vs-detected report as CSV (formula-safe) or Markdown."""
    if fmt not in ("csv", "md"):
        raise HTTPException(status_code=404, detail="Supported formats: csv, md.")
    _, inspections = _batch_inspections(db, batch_id)
    ev = build_evaluation(inspections)
    if fmt == "csv":
        body, media = evaluation_csv(ev), "text/csv"
    else:
        body, media = evaluation_markdown(ev), "text/markdown"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="expected_vs_detected_{batch_id[:8]}.{fmt}"'})


# -----------------------------
# 5. Smart Website Crawler Endpoints
# -----------------------------

@router.post(
    "/inspect-url",
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_INSPECT_PER_MIN, window_seconds=60, scope="inspect_url"))]
)
async def inspect_url(
    request: UrlInspectionRequest,
    req: Request,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """
    Inspect an authorized website URL using Playwright.
    Discovers contact & support pages, detects CAPTCHAs and forms,
    enforces SSRF and redirect security policies, and captures evidence.
    """
    # Enforce that client cannot enable loopback unless server explicitly permits dev/test loopback
    if request.allow_loopback and not settings.can_allow_loopback:
        raise HTTPException(
            status_code=400,
            detail="Security restriction: Client-controlled loopback authorization is prohibited."
        )

    effective_loopback = bool(request.allow_loopback and settings.can_allow_loopback)

    allowed, reason = SecurityGuard.validate_target_url(
        request.url,
        enforce_live_scan=True,
        allow_loopback=effective_loopback,
    )
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Security restriction: {reason}"
        )

    try:
        job_manager.ensure_capacity("crawl", current_user.id)
    except JobLimitExceeded as exc:
        raise exc.to_http()

    scan_id = generate_uuid()
    crawler = SmartCrawler(
        target_url=request.url,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        allow_loopback=effective_loopback,
    )

    log_audit_event(
        db=db,
        action="scan.create",
        actor=current_user,
        resource_type="url_scan",
        resource_id=scan_id,
        ip_address=get_client_ip(req),
        request_id=req.headers.get("X-Request-ID"),
        details={"url": redact_url(request.url), "max_pages": request.max_pages, "background": request.background}
    )

    if request.background:
        scan = UrlScan(
            id=scan_id,
            submitted_url=request.url,
            domain=crawler.base_domain,
            status="crawling",
        )
        db.add(scan)
        db.commit()

        job_manager.spawn("crawl", current_user.id, crawler.crawl(scan_id=scan_id))

        return {
            "success": True,
            "scan_id": scan_id,
            "status": "crawling",
            "message": f"Website crawl job {scan_id} initiated in background."
        }
    else:
        try:
            async with job_manager.slot("crawl", current_user.id):
                return await crawler.crawl(scan_id=scan_id)
        except JobLimitExceeded as exc:
            raise exc.to_http()


@router.get("/scans/{scan_id}")
async def get_scan_status(
    scan_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Retrieve status and summary information for a website crawl scan."""
    scan = db.query(UrlScan).filter(UrlScan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")

    return {
        "success": True,
        "scan": scan.to_dict(),
    }


@router.get("/scans/{scan_id}/results")
async def get_scan_results(
    scan_id: str,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Retrieve detailed discovered pages, classifications, evidence, and CAPTCHA results."""
    scan = db.query(UrlScan).filter(UrlScan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")

    pages = db.query(DiscoveredPage).filter(DiscoveredPage.scan_id == scan_id).order_by(DiscoveredPage.depth, DiscoveredPage.created_at).all()

    return {
        "success": True,
        "scan_id": scan_id,
        "status": scan.status,
        "submitted_url": scan.submitted_url,
        "domain": scan.domain,
        "pages_crawled": scan.pages_crawled,
        "contact_pages_found": scan.contact_pages_found,
        "captcha_detected": scan.captcha_detected,
        "captcha_providers": scan.to_dict()["captcha_providers"],
        "crawl_duration_ms": round(scan.crawl_duration_ms, 2) if scan.crawl_duration_ms else 0.0,
        "results": [page.to_dict() for page in pages],
    }


@router.get("/overview-stats")
async def get_overview_stats(
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Summary metrics and provider distribution for the overview dashboard."""
    total_scans = db.query(UrlScan).count()
    total_pages = db.query(DiscoveredPage).count()
    total_captchas = db.query(DiscoveredPage).filter(DiscoveredPage.captcha_detected == True).count()
    pending_reviews = db.query(HumanReviewRecord).filter(HumanReviewRecord.review_status == "pending").count()
    total_batches = db.query(BatchJob).count()
    
    # Provider breakdown across discovered pages
    provider_counts = (
        db.query(DiscoveredPage.captcha_provider, func.count(DiscoveredPage.id))
        .filter(DiscoveredPage.captcha_detected == True)
        .group_by(DiscoveredPage.captcha_provider)
        .all()
    )
    provider_breakdown = {p or "unknown": count for p, count in provider_counts}

    # Recent scans preview
    recent_scans = db.query(UrlScan).order_by(UrlScan.created_at.desc()).limit(5).all()

    return {
        "success": True,
        "total_scans": total_scans,
        "total_pages": total_pages,
        "total_captchas": total_captchas,
        "pending_reviews": pending_reviews,
        "total_batches": total_batches,
        "provider_breakdown": provider_breakdown,
        "recent_scans": [s.to_dict() for s in recent_scans],
    }


@router.get("/scans")
async def list_scans(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """List URL crawl scans with optional status filter and pagination."""
    query = db.query(UrlScan)
    if status:
        query = query.filter(UrlScan.status == status)
    total = query.count()
    scans = query.order_by(UrlScan.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "scans": [s.to_dict() for s in scans]
    }


@router.get("/batches")
async def list_batches(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """List batch jobs with optional status filter and pagination."""
    query = db.query(BatchJob)
    if status:
        query = query.filter(BatchJob.status == status)
    total = query.count()
    batches = query.order_by(BatchJob.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "batches": [b.to_dict() for b in batches]
    }


@router.get("/pages")
async def list_discovered_pages(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    captcha_only: bool = Query(False),
    provider: Optional[str] = Query(None),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """List discovered pages across scans with CAPTCHA and provider filters."""
    query = db.query(DiscoveredPage)
    if captcha_only:
        query = query.filter(DiscoveredPage.captcha_detected == True)
    if provider and provider != "all":
        query = query.filter(DiscoveredPage.captcha_provider == provider)
    total = query.count()
    pages = query.order_by(DiscoveredPage.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "pages": [p.to_dict() for p in pages]
    }


@router.get("/settings")
async def get_system_settings(current_user: User = Depends(require_operator)):
    """Diagnostic system settings and environment configuration."""
    import os
    tesseract_exists = os.path.exists(settings.TESSERACT_CMD)
    return {
        "success": True,
        "app_name": settings.APP_NAME,
        "app_env": settings.APP_ENV,
        "debug": settings.DEBUG,
        "host": settings.HOST,
        "port": settings.PORT,
        "enable_live_scan": settings.ENABLE_LIVE_SCAN,
        "allow_dev_loopback": settings.can_allow_loopback,
        "allowed_domains": settings.ALLOWED_DOMAINS,
        "request_timeout_ms": settings.REQUEST_TIMEOUT_MS,
        "max_concurrent_pages": settings.MAX_CONCURRENT_PAGES,
        "crawler_max_pages": settings.CRAWLER_MAX_PAGES,
        "crawler_max_depth": settings.CRAWLER_MAX_DEPTH,
        "crawler_page_timeout_ms": settings.CRAWLER_PAGE_TIMEOUT_MS,
        "crawler_total_timeout_sec": settings.CRAWLER_TOTAL_TIMEOUT_SEC,
        # Privacy: never expose local absolute paths (they contain the OS user profile name). The real
        # configured values (settings.TESSERACT_CMD / REPORTS_DIR / EVIDENCE_DIR) are used internally unchanged.
        "tesseract_cmd": "tesseract",
        "tesseract_installed": tesseract_exists,
        "reports_dir": "reports/",
        "evidence_dir": "evidence/",
        "current_user_role": current_user.role,
    }
