from typing import Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BatchJob, WebsiteInspection
from app.services.csv_importer import import_websites
from app.services.browser_scanner import inspect_local_demo
from app.services.batch_processor import create_batch
from app.services.report_generator import generate_batch_csv_report

router = APIRouter(
    prefix="/api/websites",
    tags=["Website Inspection & Batches"]
)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


# -----------------------------
# Request Models
# -----------------------------

class DemoInspectionRequest(BaseModel):
    html: str = Field(min_length=1, max_length=100000)


class DemoPage(BaseModel):
    company_name: str = Field(min_length=1, max_length=120)
    html: str = Field(min_length=1, max_length=100000)


class BatchInspectionRequest(BaseModel):
    pages: list[DemoPage] = Field(min_length=1, max_length=20)


class WebsiteScanItem(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    website_url: str = Field(min_length=1, max_length=1024)


class ScanBatchRequest(BaseModel):
    websites: list[WebsiteScanItem] = Field(min_length=1, max_length=300)


# -----------------------------
# 1. CSV Import Endpoint
# -----------------------------

@router.post("/import")
async def upload_csv(
    file: UploadFile = File(...),
    auto_scan: bool = Query(False, description="Automatically trigger batch scan for valid records")
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
            detail="Maximum CSV size is 5 MB."
        )

    result = import_websites(content)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )

    batch_id = None
    if auto_scan and result.get("websites"):
        batch_id = create_batch(result["websites"], start_background=True)
        result["batch_id"] = batch_id
        result["batch_status"] = "pending"

    return result


# -----------------------------
# 2. Single Demo Inspection
# -----------------------------

@router.post("/inspect-demo")
async def inspect_demo(request: DemoInspectionRequest):
    result = await inspect_local_demo(request.html)
    return result


# -----------------------------
# 3. Batch Demo Inspection
# -----------------------------

@router.post("/inspect-demo-batch")
async def inspect_demo_batch(request: BatchInspectionRequest):
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

@router.post("/scan-batch")
async def scan_batch(
    request: ScanBatchRequest,
    background: bool = Query(True, description="Process batch in background")
):
    """
    Initiate an asynchronous batch scan for up to 300 website records.
    Controlled concurrency and SSRF security policies are applied.
    """
    items = [{"company_name": item.company_name, "website_url": item.website_url} for item in request.websites]
    batch_id = create_batch(items, start_background=background)

    return {
        "success": True,
        "batch_id": batch_id,
        "total_records": len(items),
        "status": "pending",
        "message": f"Batch scan job {batch_id} queued successfully."
    }


@router.get("/batches/{batch_id}")
async def get_batch_status(batch_id: str, db: Session = Depends(get_db)):
    """Retrieve execution status and summary counters for a batch job."""
    batch = db.query(BatchJob).filter(BatchJob.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

    return {
        "success": True,
        "batch": batch.to_dict()
    }


@router.get("/batches/{batch_id}/results")
async def get_batch_results(batch_id: str, db: Session = Depends(get_db)):
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
async def download_batch_report(batch_id: str, db: Session = Depends(get_db)):
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
