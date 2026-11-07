"""
Aggregate evaluation metrics computed ONLY from persisted rows.

Every metric block states its denominator and time range. Nothing here is synthetic or hard-coded:
an empty database yields zeros (and `has_data: false`), never placeholder values.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    BatchJob, DiscoveredPage, HumanReviewRecord, OcrBenchmarkRun, OcrEvaluationRecord,
    ReviewDecision, UrlScan, User, VerificationRecord, WebsiteInspection,
)
from app.services.auth_service import require_operator
from app.services.rate_limiter import rate_limit

router = APIRouter(
    prefix="/api/stats",
    tags=["Evaluation metrics & reports"],
    dependencies=[Depends(rate_limit(max_requests=settings.RATE_LIMIT_DEFAULT_PER_MIN, window_seconds=60, scope="api_default"))],
)


def _pct(num: float, den: float) -> Optional[float]:
    return round(100.0 * num / den, 2) if den else None


def _range(days: Optional[int]) -> tuple[Optional[datetime], dict]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if days:
        since = now - timedelta(days=days)
        return since, {"since": since.isoformat() + "Z", "until": now.isoformat() + "Z", "all_time": False, "days": days}
    return None, {"since": None, "until": now.isoformat() + "Z", "all_time": True, "days": None}


def build_summary(db: Session, days: Optional[int] = None) -> dict:
    since, time_range = _range(days)

    def scoped(query, column):
        return query.filter(column >= since) if since else query

    # ---- inspections ----------------------------------------------------------------
    scans_q = scoped(db.query(UrlScan), UrlScan.created_at)
    scans_total = scans_q.count()
    scans_by_status = dict(scoped(db.query(UrlScan.status, func.count(UrlScan.id)), UrlScan.created_at)
                           .group_by(UrlScan.status).all())
    batch_items_total = scoped(db.query(WebsiteInspection), WebsiteInspection.created_at).count()
    batch_by_status = dict(
        scoped(db.query(WebsiteInspection.scan_status, func.count(WebsiteInspection.id)), WebsiteInspection.created_at)
        .group_by(WebsiteInspection.scan_status).all()
    )

    # ---- pages & CAPTCHA types ------------------------------------------------------
    pages_q = scoped(db.query(DiscoveredPage), DiscoveredPage.created_at)
    pages_total = pages_q.count()
    captcha_pages = pages_q.filter(DiscoveredPage.captcha_detected == True).count()  # noqa: E712
    provider_rows = (
        scoped(db.query(DiscoveredPage.captcha_provider, func.count(DiscoveredPage.id)), DiscoveredPage.created_at)
        .filter(DiscoveredPage.captcha_detected == True)  # noqa: E712
        .group_by(DiscoveredPage.captcha_provider).all()
    )
    providers = {(p or "unknown"): n for p, n in provider_rows}

    # ---- OCR ------------------------------------------------------------------------
    # Records written before Phase 7 for uploaded images carry ground_truth="SYNTHETIC" with a hard-coded
    # 0 % accuracy: they were never real evaluations, so they are EXCLUDED and reported separately.
    valid_ocr = OcrEvaluationRecord.ground_truth != "SYNTHETIC"
    ocr_q = scoped(db.query(OcrEvaluationRecord).filter(valid_ocr), OcrEvaluationRecord.created_at)
    ocr_n = ocr_q.count()
    ocr_excluded = scoped(db.query(OcrEvaluationRecord).filter(~valid_ocr), OcrEvaluationRecord.created_at).count()
    ocr_exact = ocr_q.filter(OcrEvaluationRecord.exact_match == True).count()  # noqa: E712
    ocr_char = scoped(db.query(func.avg(OcrEvaluationRecord.character_accuracy)).filter(valid_ocr),
                      OcrEvaluationRecord.created_at).scalar()
    ocr_lat = scoped(db.query(func.avg(OcrEvaluationRecord.duration_ms)).filter(valid_ocr),
                     OcrEvaluationRecord.created_at).scalar()

    heldout = {}
    for run in (db.query(OcrBenchmarkRun).filter(OcrBenchmarkRun.source == "cli_heldout")
                .order_by(OcrBenchmarkRun.created_at.asc()).all()):
        heldout[run.engine] = run.to_dict()  # latest per engine wins
    api_runs = scoped(db.query(OcrBenchmarkRun).filter(OcrBenchmarkRun.source == "api"), OcrBenchmarkRun.created_at).count()

    # ---- verification ---------------------------------------------------------------
    ver_q = scoped(db.query(VerificationRecord), VerificationRecord.created_at)
    ver_total = ver_q.count()
    ver_rows = (scoped(db.query(VerificationRecord.verification_mode, VerificationRecord.outcome, func.count(VerificationRecord.id)),
                       VerificationRecord.created_at)
                .group_by(VerificationRecord.verification_mode, VerificationRecord.outcome).all())
    by_mode: dict[str, dict[str, int]] = {}
    for mode, outcome, n in ver_rows:
        by_mode.setdefault(mode, {})[outcome] = n

    # ---- failures -------------------------------------------------------------------
    failed_scans = scans_q.filter(UrlScan.status == "failed").count()
    err_rows = (scoped(db.query(UrlScan.error_message, func.count(UrlScan.id)), UrlScan.created_at)
                .filter(UrlScan.status == "failed", UrlScan.error_message.isnot(None))
                .group_by(UrlScan.error_message).order_by(func.count(UrlScan.id).desc()).limit(5).all())

    # ---- human review ---------------------------------------------------------------
    rev_q = scoped(db.query(HumanReviewRecord), HumanReviewRecord.created_at)
    rev_total = rev_q.count()
    rev_by = dict(scoped(db.query(HumanReviewRecord.review_status, func.count(HumanReviewRecord.id)),
                         HumanReviewRecord.created_at).group_by(HumanReviewRecord.review_status).all())

    return {
        "success": True,
        "time_range": time_range,
        "has_data": bool(scans_total or pages_total or ocr_n or ver_total or heldout),
        "inspections": {
            "denominator": "url scans (single-site crawls) created in range",
            "url_scans_total": scans_total,
            "url_scans_by_status": scans_by_status,
            "batch_inspections_total": batch_items_total,
            "batch_inspections_by_status": batch_by_status,
            "batches_total": db.query(BatchJob).count(),
        },
        "pages": {
            "denominator": "discovered pages created in range",
            "pages_inspected": pages_total,
            "pages_with_captcha": captcha_pages,
            "pages_with_captcha_pct": _pct(captcha_pages, pages_total),
        },
        "captcha_types": {
            "denominator": f"{captcha_pages} pages with a CAPTCHA detected",
            "by_provider": providers,
            "share_pct": {k: _pct(v, captcha_pages) for k, v in providers.items()},
        },
        "ocr": {
            "denominator": "OCR demo/handling evaluations with a KNOWN true label (unlabelled uploads are not counted)",
            "evaluations": ocr_n,
            "excluded_legacy_unlabelled_records": ocr_excluded,
            "exact_matches": ocr_exact,
            "exact_match_pct": _pct(ocr_exact, ocr_n),
            "mean_char_accuracy_pct": round(ocr_char, 2) if ocr_char is not None else None,
            "mean_latency_ms": round(ocr_lat, 2) if ocr_lat is not None else None,
            "heldout_benchmarks": {
                "denominator": "latest CLI evaluation on the held-out TEST split, per engine",
                "by_engine": heldout,
            },
            "api_benchmark_runs": api_runs,
        },
        "verification": {
            "denominator": f"{ver_total} recorded verification attempts",
            "attempts": ver_total,
            "by_mode_and_outcome": by_mode,
            "provider_confirmed": sum(n for m in by_mode if m in ("provider_live", "provider_test_keys")
                                      for o, n in by_mode[m].items() if o == "verified"),
            "simulated_attempts": sum(by_mode.get("simulated", {}).values()),
            "note": "Only provider_live/provider_test_keys involve the provider; 'simulated' never calls it and never succeeds.",
        },
        "failures": {
            "denominator": f"{scans_total} url scans",
            "failed_scans": failed_scans,
            "failed_scans_pct": _pct(failed_scans, scans_total),
            "top_errors": [{"message": (m or "")[:160], "count": n} for m, n in err_rows],
        },
        "human_review": {
            "denominator": "human review cases created in range",
            "cases": rev_total,
            "by_status": rev_by,
            "decisions_recorded": db.query(ReviewDecision).count(),
        },
    }


@router.get("/summary")
async def stats_summary(
    days: Optional[int] = Query(None, ge=1, le=3650, description="Restrict to the last N days (default: all time)"),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    return build_summary(db, days)


@router.get("/report", response_class=PlainTextResponse)
async def evaluation_report(
    days: Optional[int] = Query(None, ge=1, le=3650),
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Markdown evaluation report generated from the same persisted data as the dashboard."""
    s = build_summary(db, days)
    tr = s["time_range"]
    lines = [
        "# CAPTCHA Inspector - Evaluation Report",
        "",
        f"Generated (UTC): {tr['until']}  |  Range: {'all time' if tr['all_time'] else f'last {tr['days']} days'}",
        f"Generated for: {current_user.username} ({current_user.role})",
        "",
        "All figures come from persisted records; denominators are stated for every block.",
        "",
        "## Inspections", f"- URL scans: {s['inspections']['url_scans_total']} "
        f"(by status: {s['inspections']['url_scans_by_status'] or 'none'})",
        f"- Batch inspections: {s['inspections']['batch_inspections_total']}",
        f"- Pages inspected: {s['pages']['pages_inspected']} "
        f"(with CAPTCHA: {s['pages']['pages_with_captcha']}, {s['pages']['pages_with_captcha_pct']}%)",
        "", "## CAPTCHA types detected",
        f"_Denominator: {s['captcha_types']['denominator']}_",
    ]
    lines += [f"- {k}: {v} ({s['captcha_types']['share_pct'][k]}%)" for k, v in s["captcha_types"]["by_provider"].items()] \
        or ["- none recorded"]
    o = s["ocr"]
    lines += ["", "## OCR evaluation", f"_Denominator: {o['denominator']}_",
              f"- Labelled evaluations: {o['evaluations']}; exact match: {o['exact_match_pct']}%; "
              f"mean character accuracy: {o['mean_char_accuracy_pct']}%; mean latency: {o['mean_latency_ms']} ms",
              "", "### Held-out benchmark (latest CLI run per engine)"]
    for engine, run in o["heldout_benchmarks"]["by_engine"].items():
        lines.append(f"- {engine}: n={run['samples']}, exact {run['exact_match_pct']}%, char {run['char_accuracy_pct']}%, "
                     f"latency {run['latency_ms_mean']} ms, failures {run['failures']}")
    if not o["heldout_benchmarks"]["by_engine"]:
        lines.append("- none imported yet (`python -m scripts.ocr_benchmark import-results`)")
    v = s["verification"]
    lines += ["", "## Verification outcomes", f"_Denominator: {v['denominator']}_",
              f"- Confirmed by a provider: {v['provider_confirmed']}; simulated attempts: {v['simulated_attempts']}"]
    for mode, outcomes in v["by_mode_and_outcome"].items():
        lines.append(f"- {mode}: " + ", ".join(f"{k}={n}" for k, n in outcomes.items()))
    f = s["failures"]
    lines += ["", "## Failures", f"- Failed scans: {f['failed_scans']} ({f['failed_scans_pct']}% of {s['inspections']['url_scans_total']})"]
    lines += [f"  - {e['count']}x {e['message']}" for e in f["top_errors"]]
    h = s["human_review"]
    lines += ["", "## Human review", f"- Cases: {h['cases']} (by status: {h['by_status'] or 'none'}); "
              f"decisions recorded: {h['decisions_recorded']}", ""]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="captcha_inspector_evaluation_report.md"',
                 "Cache-Control": "no-store"},
    )
