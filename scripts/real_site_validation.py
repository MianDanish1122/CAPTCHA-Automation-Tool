"""
Polite, read-only validation of the CAPTCHA inspector on a SMALL, user-approved set of real websites.

    python -m scripts.real_site_validation --sites "Big Frog,Breadtopia,Barrett Firearms"

What it does, per site, through the SAME engine the batch workflow uses (inspect_website):
  1. robots.txt / access-restriction check first. A disallow, a 401/403/429 or a bot challenge STOPS the site
     (reported "not accessible"); there is no retry, no header tweak, no workaround.
  2. one visit to the CSV's Contact Page, bounded wait for JS-rendered widgets, provider/subtype/widget evidence.
  3. screenshot of the page, field inventory of the form, and a SYNTHETIC fill under a hard no-transmission
     lockdown (network cut, browser offline, submit shield). Nothing is submitted, no CAPTCHA is touched.
Politeness: sites are visited sequentially with a >= --gap seconds pause (default 8 s); each site has a hard timeout.
Egress is limited to the approved hosts (ALLOWED_DOMAINS) plus the narrow CAPTCHA-provider widget policy.
Evidence is written to evidence/final_qa/real_sites/. Nothing is mocked: a failure is recorded as a failure.
"""
import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CSV_PATH = ROOT / "USA_Ecommerce_Platforms_200_Contact_Pages.csv"
OUT = ROOT / "evidence" / "final_qa" / "real_sites"


def _hosts_for(rows):
    hosts = set()
    for r in rows:
        for u in (r["Website"], r["Contact Page"]):
            h = (urlparse(u).hostname or "").lower()
            if h:
                hosts.add(h)
                hosts.add(h[4:] if h.startswith("www.") else "www." + h)
    return sorted(hosts)


async def run(names, gap, site_timeout):
    from app.config import settings
    from app.services.browser_scanner import inspect_website
    from app.services.csv_importer import import_websites
    from app.services.evaluation import categorise, summarise

    imported = import_websites(CSV_PATH.read_bytes())
    by_name = {w["company_name"]: w for w in imported["websites"]}
    results = []
    shots = OUT / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(names):
        row = by_name[name]
        if i:
            await asyncio.sleep(gap)
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{started}] {name}: {row['website_url']}  contact={row['expected_contact_page']}  expected={row['expected_captcha_raw']}", flush=True)
        try:
            r = await asyncio.wait_for(inspect_website(
                row["website_url"], check_security=True,
                expected_contact_page=row["expected_contact_page"],
                respect_robots=True, probe_forms=True, user_agent=settings.CRAWLER_USER_AGENT,
                evidence_dir=shots, evidence_name=name.replace(" ", "_").lower()), timeout=site_timeout)
        except asyncio.TimeoutError:
            r = {"success": False, "scan_status": "failed", "error_details": f"Hard timeout after {site_timeout}s",
                 "detected_providers": [], "detection_method": "timeout"}
        providers = r.get("detected_providers") or []
        cat = categorise(row["expected_captcha"], providers, r.get("scan_status"), subtype=r.get("captcha_subtype"))
        rec = {
            "company": name, "website": row["website_url"], "csv_contact_page": row["expected_contact_page"],
            "csv_expected": row["expected_captcha_raw"], "csv_expected_normalised": row["expected_captcha"],
            "visited_at": started, "result_category": cat["category"], "reason": cat["reason"],
            "subtype_agreement": cat["subtype_agreement"], "inspection": r,
        }
        # keep the evidence file free of any token-like or oversized material
        rec["inspection"].pop("network_guard", None)
        (OUT / f"{name.replace(' ', '_').lower()}.json").write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
        results.append(rec)
        probe = r.get("form_probe") or {}
        print(f"    -> {cat['category'].upper()} | status={r.get('scan_status')} robots={r.get('robots_status')} "
              f"detected={providers or 'none'} subtype={r.get('captcha_subtype')} widget={r.get('widget_state')} "
              f"forms={probe.get('form_count')} filled={probe.get('filled_fields')}", flush=True)
        if r.get("error_details"):
            print(f"    error: {str(r['error_details'])[:200]}", flush=True)

    summary = summarise([{"result_category": x["result_category"], "subtype_agreement": x["subtype_agreement"]} for x in results])
    (OUT / "results.json").write_text(json.dumps({"sites": results, "summary": summary,
                                                 "policy": {"robots_first": True, "submit": False, "captcha_clicked": False,
                                                            "min_gap_seconds": gap}}, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default="Big Frog,Breadtopia,Barrett Firearms")
    ap.add_argument("--gap", type=float, default=8.0)
    ap.add_argument("--site-timeout", type=float, default=150.0)
    args = ap.parse_args()
    names = [n.strip() for n in args.sites.split(",") if n.strip()]

    rows = [r for r in csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")) if r["Company"] in names]
    missing = set(names) - {r["Company"] for r in rows}
    if missing:
        print("not in CSV:", missing)
        return 2
    # Egress is restricted to exactly the approved sites BEFORE the app config is imported.
    os.environ["ENABLE_LIVE_SCAN"] = "true"
    os.environ["ALLOWED_DOMAINS"] = ",".join(_hosts_for(rows))
    os.environ["BATCH_MIN_HOST_INTERVAL_S"] = "5"
    print("allow-list:", os.environ["ALLOWED_DOMAINS"], flush=True)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    OUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(names, args.gap, args.site_timeout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
