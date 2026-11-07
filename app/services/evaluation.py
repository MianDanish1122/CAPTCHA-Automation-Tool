"""
Expected-versus-detected CAPTCHA evaluation (pure logic, no I/O).

Result categories (exactly the five requested):
  match           expected and detected agree (provider level; subtype agreement is reported separately)
  mismatch        expected X but a different provider was detected, or expected none but one was detected
  not_detected    a CAPTCHA was expected, the page WAS inspected, and none was detected
  not_accessible  the site/page could not be inspected (error, robots/access restriction, bot challenge)
  not_verified    there is no usable expectation (empty / unrecognised) so nothing can be scored

Metrics are computed ONLY over eligible records (match + mismatch + not_detected): records that were really inspected
AND carry ground truth. not_accessible and not_verified are reported separately and never counted as correct/incorrect.
"""
from typing import Any, Iterable, Optional

CATEGORIES = ("match", "mismatch", "not_detected", "not_accessible", "not_verified")

PROVIDER_KEY = {"google_recaptcha": "recaptcha", "hcaptcha": "hcaptcha", "cloudflare_turnstile": "turnstile"}
EXPECTED_FAMILY = {
    "recaptcha": "recaptcha", "recaptcha_v2": "recaptcha", "recaptcha_invisible": "recaptcha",
    "recaptcha_v3": "recaptcha", "hcaptcha": "hcaptcha", "turnstile": "turnstile",
}
INACCESSIBLE_STATUSES = {
    "failed", "blocked_by_robots", "blocked_by_challenge", "unsupported_challenge", "navigation_failure", "pending",
    "scanning",
}


def detected_families(providers: Iterable[str]) -> set[str]:
    out = set()
    for p in providers or []:
        p = (p or "").strip()
        out.add(PROVIDER_KEY.get(p, p))
    return {x for x in out if x}


def subtype_agreement(expected: str, subtype: Optional[str]) -> str:
    """'agree' | 'differs' | 'n/a' — informational, does not change the category."""
    if expected in ("recaptcha", "hcaptcha", "turnstile", "none") or not subtype:
        return "n/a"
    s = subtype.replace("enterprise_", "")
    want = {"recaptcha_v2": ("v2_checkbox",), "recaptcha_invisible": ("invisible", "invisible_or_v3"),
            "recaptcha_v3": ("v3_score_based", "invisible_or_v3")}.get(expected)
    if want is None:
        return "n/a"
    return "agree" if s in want else "differs"


def categorise(
    expected: Optional[str],
    detected_providers: Iterable[str],
    scan_status: Optional[str],
    subtype: Optional[str] = None,
    accessible: Optional[bool] = None,
) -> dict[str, Any]:
    """Classify one inspected website. `accessible=False` forces not_accessible."""
    fams = detected_families(detected_providers)
    if accessible is False or (scan_status or "") in INACCESSIBLE_STATUSES:
        return {"category": "not_accessible", "reason": "The page could not be inspected (error, access restriction or bot challenge).",
                "subtype_agreement": "n/a"}
    if not expected or expected == "unrecognised":
        return {"category": "not_verified", "reason": "No usable expected value in the CSV; detection recorded but not scored.",
                "subtype_agreement": "n/a"}
    if expected == "none":
        if fams:
            return {"category": "mismatch", "reason": f"Expected no CAPTCHA but detected: {', '.join(sorted(fams))}.",
                    "subtype_agreement": "n/a"}
        return {"category": "match", "reason": "Expected no CAPTCHA and none was detected.", "subtype_agreement": "n/a"}
    want = EXPECTED_FAMILY.get(expected)
    if want is None:
        return {"category": "not_verified", "reason": f"Expected value '{expected}' is not a known label.",
                "subtype_agreement": "n/a"}
    if not fams:
        return {"category": "not_detected", "reason": f"Expected {expected} but no CAPTCHA was detected on the inspected page.",
                "subtype_agreement": "n/a"}
    if want in fams:
        return {"category": "match", "reason": f"Expected {expected}; detected {', '.join(sorted(fams))}.",
                "subtype_agreement": subtype_agreement(expected, subtype)}
    return {"category": "mismatch", "reason": f"Expected {expected} but detected {', '.join(sorted(fams))}.",
            "subtype_agreement": "n/a"}


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts and metrics over eligible records only, with the sample size stated."""
    counts = {c: 0 for c in CATEGORIES}
    for r in rows:
        counts[r.get("result_category") if r.get("result_category") in counts else "not_verified"] += 1
    eligible = counts["match"] + counts["mismatch"] + counts["not_detected"]
    agree = sum(1 for r in rows if r.get("result_category") == "match" and r.get("subtype_agreement") == "agree")
    differ = sum(1 for r in rows if r.get("result_category") == "match" and r.get("subtype_agreement") == "differs")
    return {
        "total_records": len(rows),
        "counts": counts,
        "eligible_records": eligible,
        "excluded": {"not_accessible": counts["not_accessible"], "not_verified": counts["not_verified"]},
        "agreement_pct": round(100.0 * counts["match"] / eligible, 1) if eligible else None,
        "subtype_agreement": {"agree": agree, "differs": differ},
        "sample_size_note": (
            f"Agreement is computed over {eligible} eligible inspected record(s) out of {len(rows)} total. "
            + ("This sample is too small to estimate accuracy statistically; treat it as a demonstration, not a benchmark."
               if eligible < 30 else "")
        ).strip(),
    }
