import csv
import io
import json
import re
from typing import Any, Optional
from urllib.parse import urlparse

from app.config import settings
from app.services.fixture_loader import (
    FixtureError,
    extract_fixture_name,
    is_fixture_reference,
    validate_fixture_name,
)

# Required columns (unchanged behaviour) and the optional columns the employer CSV carries.
ALIASES = {
    "company_name": ["company_name", "company", "name"],
    "website_url": ["website_url", "website", "url"],
}
OPTIONAL_ALIASES = {
    "expected_captcha": ["expected_captcha", "captcha", "expected_captcha_type", "captcha_type"],
    "expected_contact_page": ["expected_contact_page", "contact_page", "contact_page_url", "contact_url", "contact"],
    "platform": ["platform", "ecommerce_platform"],
    "city": ["city"],
    "state": ["state", "region"],
    "category": ["category", "industry"],
}

MAX_CELL_LEN = 2048   # a single cell longer than this is truncated in the preserved copy


def normalise_header(name: str) -> str:
    """'Contact Page ' -> 'contact_page'. Used for matching only; original headers are preserved separately."""
    return re.sub(r"[\s\-]+", "_", (name or "").strip().lower())


def normalise_expected_captcha(raw: Optional[str]) -> Optional[str]:
    """
    Map the free-text 'Captcha' column to a stable label. Returns None for an empty cell and 'unrecognised' for
    text this function does not understand (kept visible; never silently coerced).
      recaptcha_v2 | recaptcha_invisible | recaptcha_v3 | recaptcha | hcaptcha | turnstile | none | unrecognised
    """
    text = (raw or "").strip().lower()
    if not text:
        return None
    if text in ("none", "no", "n/a", "na", "-", "no captcha", "no_captcha", "nil"):
        return "none"
    if "turnstile" in text or "cloudflare" in text:
        return "turnstile"
    if "hcaptcha" in text or "h-captcha" in text or "h captcha" in text:
        return "hcaptcha"
    if "recaptcha" in text or "re-captcha" in text or "google" in text:
        if "invisible" in text:
            return "recaptcha_invisible"
        if "v3" in text:
            return "recaptcha_v3"
        if "v2" in text or "checkbox" in text:
            return "recaptcha_v2"
        return "recaptcha"
    return "unrecognised"


def _valid_http_url(value: str) -> bool:
    p = urlparse(value)
    return p.scheme in ("http", "https") and bool(p.hostname) and not p.username and not p.password


def import_websites(file_content: bytes) -> dict[str, Any]:
    """Parse and validate an uploaded website CSV. EVERY source column of a valid row is preserved."""

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

    column_map = {}
    for column in reader.fieldnames:
        if column:
            column_map.setdefault(normalise_header(column), column)

    def pick(aliases: list[str]) -> Optional[str]:
        for alt in aliases:
            if alt in column_map:
                return column_map[alt]
        return None

    selected_columns = {key: pick(alts) for key, alts in ALIASES.items() if pick(alts)}
    optional_columns = {key: pick(alts) for key, alts in OPTIONAL_ALIASES.items() if pick(alts)}

    missing = [column for column in ALIASES if column not in selected_columns]

    if missing:
        return {
            "success": False,
            "message": f"Missing required columns: {missing}",
            "websites": [],
        }

    mapped_sources = set(selected_columns.values()) | set(optional_columns.values())
    websites = []
    errors = []
    warnings = []

    for row_number, row in enumerate(reader, start=2):
        company = (row.get(selected_columns["company_name"]) or "").strip()
        website_url = (row.get(selected_columns["website_url"]) or "").strip()

        if not company or not website_url:
            errors.append({"row": row_number, "reason": "Company name or website URL is missing."})
            continue

        parsed = urlparse(website_url)

        is_fixture = False
        if is_fixture_reference(website_url):
            try:
                if not settings.fixtures_enabled:
                    raise FixtureError("Fixture URLs are disabled in this environment.")
                validate_fixture_name(extract_fixture_name(website_url))
                is_fixture = True
            except FixtureError as fx_err:
                errors.append({"row": row_number, "reason": f"Invalid fixture reference: {fx_err}"})
                continue
        is_web = parsed.scheme in ("http", "https") and bool(parsed.hostname)

        if (not is_web and not is_fixture) or parsed.username or parsed.password:
            errors.append({"row": row_number, "reason": "Invalid website URL."})
            continue

        def cell(key: str) -> Optional[str]:
            col = optional_columns.get(key)
            value = (row.get(col) or "").strip() if col else ""
            return value or None

        expected_page = cell("expected_contact_page")
        if expected_page and not _valid_http_url(expected_page):
            warnings.append({"row": row_number, "reason": "Contact Page is not a valid http(s) URL; it was ignored "
                                                          "(page discovery will be used instead)."})
            expected_page = None

        expected_raw = cell("expected_captcha")
        expected = normalise_expected_captcha(expected_raw)
        if expected == "unrecognised":
            warnings.append({"row": row_number, "reason": f"Captcha value '{(expected_raw or '')[:40]}' is not "
                                                          "recognised; the row is kept but not scored."})

        # Preserve the ORIGINAL row verbatim (keys = original headers), including unmapped columns.
        preserved = {k: (v if v is None else str(v)[:MAX_CELL_LEN]) for k, v in row.items() if k is not None}
        extras = row.get(None)  # DictReader collects overflow cells under key None
        if extras:
            warnings.append({"row": row_number, "reason": "Row has more cells than headers; extras were kept as _extra."})
            preserved["_extra"] = [str(x)[:MAX_CELL_LEN] for x in extras]

        websites.append({
            "company_name": company,
            "website_url": website_url,
            "status": "pending",
            "expected_captcha_raw": expected_raw,
            "expected_captcha": expected,
            "expected_contact_page": expected_page,
            "platform": cell("platform"),
            "city": cell("city"),
            "state": cell("state"),
            "category": cell("category"),
            "source_row": json.dumps(preserved, ensure_ascii=False),
            "source_row_number": row_number,
        })

    return {
        "success": True,
        "total_websites": len(websites),
        "invalid_rows": len(errors),
        "websites": websites,
        "errors": errors,
        "warnings": warnings,
        "columns": [c for c in reader.fieldnames if c],
        "mapped_columns": {**selected_columns, **optional_columns},
        "preserved_columns": [c for c in reader.fieldnames if c],
        "unmapped_columns": [c for c in reader.fieldnames if c and c not in mapped_sources],
    }
