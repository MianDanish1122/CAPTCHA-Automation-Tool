import csv
import io
from typing import Any
from urllib.parse import urlparse

ALIASES = {
    "company_name": ["company_name", "company", "name"],
    "website_url": ["website_url", "website", "url"],
}


def import_websites(file_content: bytes) -> dict[str, Any]:
    """Parse and validate an uploaded website CSV."""

    try:
        content = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {
            "success": False,
            "message": "CSV must use UTF-8 encoding.",
            "websites": [],
        }

    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        return {
            "success": False,
            "message": "CSV is empty or has no headers.",
            "websites": [],
        }

    column_map = {
        column.strip().lower(): column
        for column in reader.fieldnames
        if column
    }

    selected_columns = {}

    for required, alternatives in ALIASES.items():
        for alternative in alternatives:
            if alternative in column_map:
                selected_columns[required] = column_map[alternative]
                break

    missing = [
        column for column in ALIASES
        if column not in selected_columns
    ]

    if missing:
        return {
            "success": False,
            "message": f"Missing required columns: {missing}",
            "websites": [],
        }

    websites = []
    errors = []

    for row_number, row in enumerate(reader, start=2):
        company = (
            row.get(selected_columns["company_name"]) or ""
        ).strip()

        website_url = (
            row.get(selected_columns["website_url"]) or ""
        ).strip()

        if not company or not website_url:
            errors.append({
                "row": row_number,
                "reason": "Company name or website URL is missing."
            })
            continue

        parsed = urlparse(website_url)

        is_fixture = parsed.scheme == "fixture" and bool(parsed.netloc or parsed.path)
        is_web = parsed.scheme in ("http", "https") and bool(parsed.hostname)

        if (
            (not is_web and not is_fixture)
            or parsed.username
            or parsed.password
        ):
            errors.append({
                "row": row_number,
                "reason": "Invalid website URL."
            })
            continue

        websites.append({
            "company_name": company,
            "website_url": website_url,
            "status": "pending",
        })

    return {
        "success": True,
        "total_websites": len(websites),
        "invalid_rows": len(errors),
        "websites": websites,
        "errors": errors,
    }
