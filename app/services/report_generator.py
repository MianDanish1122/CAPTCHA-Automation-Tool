import csv
import io
from pathlib import Path
from typing import Sequence
from app.models import WebsiteInspection
from app.config import settings


def generate_batch_csv_report(
    inspections: Sequence[WebsiteInspection],
    save_to_file: bool = True,
    filename: str = None
) -> tuple[str, Path | None]:
    """
    Generate standard CSV report from website inspection records.
    Returns (csv_string, file_path_if_saved).
    """
    fieldnames = [
        "Company Name",
        "Website URL",
        "Website Status",
        "Contact Page Found",
        "CAPTCHA Detected",
        "CAPTCHA Provider",
        "Inspection Status",
        "Human Review Required",
        "Error Details",
        "Scan Timestamp",
        "Processing Duration (ms)",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for item in inspections:
        writer.writerow({
            "Company Name": item.company_name,
            "Website URL": item.website_url,
            "Website Status": item.scan_status,
            "Contact Page Found": "Yes" if item.contact_page_url or item.contact_form_found else "No",
            "CAPTCHA Detected": "Yes" if item.captcha_detected else "No",
            "CAPTCHA Provider": item.captcha_provider or "None",
            "Inspection Status": item.scan_status,
            "Human Review Required": "Yes" if item.human_review_required else "No",
            "Error Details": item.error_details or "",
            "Scan Timestamp": item.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if item.created_at else "",
            "Processing Duration (ms)": f"{item.inspection_duration_ms:.2f}",
        })

    csv_content = output.getvalue()
    saved_path = None

    if save_to_file:
        batch_id = inspections[0].batch_id if inspections else "empty"
        target_name = filename or f"captcha_audit_report_{batch_id}.csv"
        saved_path = settings.REPORTS_DIR / target_name
        with open(saved_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(csv_content)

    return csv_content, saved_path
