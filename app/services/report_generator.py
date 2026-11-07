import csv
import io
from pathlib import Path
from typing import Any, Sequence

from app.models import WebsiteInspection
from app.config import settings
from app.services.evaluation import categorise, summarise

# A spreadsheet treats a cell that STARTS with one of these as a formula (CSV / formula injection, CWE-1236).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def csv_safe(value: Any) -> Any:
    """
    Neutralise spreadsheet formulas in untrusted text (company names, URLs, page titles, error text come from
    uploaded CSVs and from third-party websites). A leading apostrophe makes Excel/Sheets/LibreOffice treat the cell as
    text; the original characters are all preserved. Non-strings (numbers, None) are returned unchanged.
    """
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" ")  # some spreadsheets ignore leading spaces before the formula character
    if stripped.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def generate_batch_csv_report(
    inspections: Sequence[WebsiteInspection],
    save_to_file: bool = True,
    filename: str = None
) -> tuple[str, Path | None]:
    """
    Generate standard CSV report from website inspection records.
    Returns (csv_string, file_path_if_saved). Every text cell is formula-injection safe.
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
        # real-world QA additions (appended; the original columns above are unchanged)
        "Contact Page URL",
        "Expected CAPTCHA",
        "CAPTCHA Subtype",
        "Widget Loaded",
        "Result Category",
        "Robots Status",
        "Platform",
        "City",
        "State",
        "Category",
        "Screenshot",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for item in inspections:
        writer.writerow({k: csv_safe(v) for k, v in {
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
            "Contact Page URL": item.contact_page_url or "",
            "Expected CAPTCHA": item.expected_captcha_raw or item.expected_captcha or "",
            "CAPTCHA Subtype": item.captcha_subtype or "",
            "Widget Loaded": "Yes" if item.widget_loaded else "No",
            "Result Category": item.result_category or "",
            "Robots Status": item.robots_status or "",
            "Platform": item.platform or "",
            "City": item.city or "",
            "State": item.state or "",
            "Category": item.category or "",
            "Screenshot": item.screenshot_path or "",
        }.items()})

    csv_content = output.getvalue()
    saved_path = None

    if save_to_file:
        batch_id = inspections[0].batch_id if inspections else "empty"
        target_name = filename or f"captcha_audit_report_{batch_id}.csv"
        saved_path = settings.REPORTS_DIR / target_name
        with open(saved_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(csv_content)

    return csv_content, saved_path


# ------------------------------------------------------------------ expected-vs-detected report
RESULT_LABELS = {"match": "Match", "mismatch": "Mismatch", "not_detected": "Not detected",
                 "not_accessible": "Not accessible", "not_verified": "Not verified"}


def build_evaluation(inspections: Sequence[WebsiteInspection]) -> dict[str, Any]:
    """Rows (Website | Expected | Detected | Contact Page | Widget Loaded | Result) plus the eligible-only summary."""
    rows = []
    for i in inspections:
        providers = [p.strip() for p in (i.captcha_provider or "").split(",") if p.strip()]
        cat = categorise(i.expected_captcha, providers, i.scan_status, subtype=i.captcha_subtype)
        # trust a stored category (set when the record was processed) but fall back to a fresh computation
        category = i.result_category or cat["category"]
        rows.append({
            "company": i.company_name,
            "website": i.website_url,
            "expected": i.expected_captcha_raw or i.expected_captcha or None,
            "expected_normalised": i.expected_captcha,
            "detected": (i.captcha_provider or "none") + (f" ({i.captcha_subtype})" if i.captcha_subtype else ""),
            "contact_page": i.contact_page_url or i.expected_contact_page,
            "widget_loaded": bool(i.widget_loaded),
            "result_category": category,
            "result": RESULT_LABELS.get(category, category),
            "reason": cat["reason"] if category == cat["category"] else None,
            "subtype_agreement": cat["subtype_agreement"],
            "scan_status": i.scan_status,
            "error": i.error_details,
        })
    return {"rows": rows, "summary": summarise(rows)}


def evaluation_csv(evaluation: dict[str, Any]) -> str:
    out = io.StringIO()
    cols = ["Website", "Expected", "Detected", "Contact Page", "Widget Loaded", "Result", "Reason"]
    w = csv.writer(out, lineterminator="\n")
    w.writerow(cols)
    for r in evaluation["rows"]:
        w.writerow([csv_safe(x) for x in [
            f'{r["company"]} ({r["website"]})', r["expected"] or "(not provided)", r["detected"],
            r["contact_page"] or "", "Yes" if r["widget_loaded"] else "No", r["result"], r["reason"] or r["error"] or ""]])
    return out.getvalue()


def evaluation_markdown(evaluation: dict[str, Any], title: str = "Expected vs detected CAPTCHA") -> str:
    s = evaluation["summary"]
    c = s["counts"]

    def cell(x: Any) -> str:
        return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")

    lines = [f"# {title}", "",
             f"**Sample:** {s['total_records']} record(s); **eligible for scoring:** {s['eligible_records']} "
             f"(inspected AND with an expected value).", "",
             f"| Match | Mismatch | Not detected | Not accessible | Not verified |", "| ---: | ---: | ---: | ---: | ---: |",
             f"| {c['match']} | {c['mismatch']} | {c['not_detected']} | {c['not_accessible']} | {c['not_verified']} |", "",
             f"Agreement over eligible records: **{s['agreement_pct'] if s['agreement_pct'] is not None else 'n/a'}"
             f"{'%' if s['agreement_pct'] is not None else ''}**. {s['sample_size_note']}", "",
             "`Not accessible` and `Not verified` are excluded from the percentage: they say nothing about detection quality.", "",
             "| Website | Expected | Detected | Contact page | Widget loaded | Result |", "| --- | --- | --- | --- | :-: | --- |"]
    for r in evaluation["rows"]:
        lines.append(f"| {cell(r['company'])} | {cell(r['expected'] or '(not provided)')} | {cell(r['detected'])} | "
                     f"{cell(r['contact_page'] or '')} | {'Yes' if r['widget_loaded'] else 'No'} | {r['result']} |")
    return "\n".join(lines) + "\n"
