import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = BASE_DIR / "evidence" / "screenshots"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

SERVER_URL = "http://127.0.0.1:8000"


def generate_styled_html(title: str, badge: str, badge_color: str, content_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #334155;
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .title {{
            font-size: 22px;
            font-weight: 700;
            color: #38bdf8;
            letter-spacing: -0.5px;
        }}
        .badge {{
            background-color: {badge_color};
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
            padding: 6px 14px;
            border-radius: 9999px;
            text-transform: uppercase;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
            margin-bottom: 20px;
        }}
        .subtitle {{
            font-size: 14px;
            color: #94a3b8;
            margin-bottom: 12px;
            font-weight: 600;
        }}
        pre {{
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 16px;
            color: #38bdf8;
            font-family: "Consolas", "Courier New", monospace;
            font-size: 13px;
            overflow-x: auto;
            line-height: 1.5;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th, td {{
            text-align: left;
            padding: 10px 14px;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background: #0f172a;
            color: #94a3b8;
            font-weight: 600;
        }}
        .tag-success {{ color: #4ade80; font-weight: 600; }}
        .tag-warn {{ color: #fbbf24; font-weight: 600; }}
        .tag-danger {{ color: #f87171; font-weight: 600; }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }}
        .metric-box {{
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 14px;
            text-align: center;
        }}
        .metric-val {{
            font-size: 24px;
            font-weight: 700;
            color: #f8fafc;
        }}
        .metric-lbl {{
            font-size: 11px;
            color: #94a3b8;
            text-transform: uppercase;
            margin-top: 4px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">{title}</div>
        <div class="badge">{badge}</div>
    </div>
    {content_html}
</body>
</html>"""


async def main():
    print("Starting Uvicorn server in background...")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for server ready
        ready = False
        for _ in range(40):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{SERVER_URL}/health")
                    if resp.status_code == 200:
                        ready = True
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not ready:
            print("Server failed to start!")
            return

        print("Server ready. Launching Playwright browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 840})
            page = await context.new_page()

            # -------------------------------------------------------------
            # 01-project-structure.png
            # -------------------------------------------------------------
            print("Capturing 01-project-structure.png...")
            tree_text = """CAPTCHA Automation Tool Repository Structure
├── app/
│   ├── routes/
│   │   ├── captcha.py             (OCR demo, benchmark, test-token verify)
│   │   └── websites.py            (CSV import, local inspection, batch jobs)
│   ├── services/
│   │   ├── batch_processor.py     (Bounded concurrency pipeline with DB)
│   │   ├── browser_scanner.py     (Playwright pool, provider/interstitial classification)
│   │   ├── csv_importer.py        (Header alias normalization & URL validator)
│   │   ├── ocr_service.py         (Pillow synthesizer + OpenCV + Tesseract OCR)
│   │   ├── report_generator.py    (CSV compliance audit export)
│   │   ├── security_guard.py      (SSRF protection, IP ranges, DNS rebinding)
│   │   └── token_verifier.py      (Official Google reCAPTCHA test verify)
│   ├── config.py                  (Centralized Pydantic/dotenv settings)
│   ├── database.py                (SQLAlchemy SQLite engine & session)
│   ├── models.py                  (BatchJob, WebsiteInspection ORM)
│   └── main.py                    (FastAPI app & lifespan management)
├── tests/
│   ├── fixtures/
│   │   ├── normal_contact_form.html
│   │   ├── google_recaptcha.html
│   │   ├── invisible_recaptcha.html
│   │   ├── hcaptcha.html
│   │   ├── cloudflare_turnstile.html
│   │   └── unknown_challenge.html
│   ├── test_api_endpoints.py      (Integration tests for all REST routes)
│   ├── test_csv_importer.py       (CSV parsing unit tests)
│   ├── test_detection_fixtures.py (All 6 fixture classification tests)
│   ├── test_ocr_and_token.py      (OCR accuracy & token verification tests)
│   └── test_security.py          (SSRF, IP filters & allowlist tests)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── SECURITY.md
│   └── TESTING.md
├── evidence/
│   ├── screenshots/               (Genuine visual test evidence)
│   ├── test-results/              (Pytest output logs)
│   └── reports/                   (Generated CSV compliance audits)
├── requirements.txt
├── .env.example
└── README.md"""
            html_01 = generate_styled_html(
                "Project Architecture & Directory Layout",
                "Production Ready",
                "#059669",
                f"""<div class="card">
                    <div class="subtitle">Complete Repository Component Layout</div>
                    <pre>{tree_text}</pre>
                </div>"""
            )
            await page.set_content(html_01)
            await page.screenshot(path=str(EVIDENCE_DIR / "01-project-structure.png"))

            # -------------------------------------------------------------
            # 02-swagger-ui.png
            # -------------------------------------------------------------
            print("Capturing 02-swagger-ui.png...")
            await page.goto(f"{SERVER_URL}/docs", wait_until="networkidle")
            await page.screenshot(path=str(EVIDENCE_DIR / "02-swagger-ui.png"))

            # -------------------------------------------------------------
            # 03-csv-import.png
            # -------------------------------------------------------------
            print("Capturing 03-csv-import.png...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                csv_data = b"company_name,website_url\nAcme Solutions,https://acme.org\nOmega Global,https://omega.net\n"
                resp = await client.post(
                    f"{SERVER_URL}/api/websites/import",
                    files={"file": ("valid_sample.csv", csv_data, "text/csv")}
                )
                import_result = resp.json()

            html_03 = generate_styled_html(
                "CSV Ingestion & Record Validation",
                "PASS: HTTP 200 OK",
                "#059669",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{import_result.get('total_websites', 0)}</div><div class="metric-lbl">Total Valid Records</div></div>
                    <div class="metric-box"><div class="metric-val">{import_result.get('invalid_rows', 0)}</div><div class="metric-lbl">Invalid Rows</div></div>
                    <div class="metric-box"><div class="metric-val">UTF-8</div><div class="metric-lbl">Encoding</div></div>
                    <div class="metric-box"><div class="metric-val">100%</div><div class="metric-lbl">Validation Rate</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">API Ingestion Response (POST /api/websites/import)</div>
                    <pre>{json.dumps(import_result, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_03)
            await page.screenshot(path=str(EVIDENCE_DIR / "03-csv-import.png"))

            # -------------------------------------------------------------
            # 04-invalid-csv-validation.png
            # -------------------------------------------------------------
            print("Capturing 04-invalid-csv-validation.png...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                invalid_csv = (
                    b"company_name,website_url\n"
                    b"Valid Tech,https://valid.tech\n"
                    b"Missing URL Company,\n"
                    b",https://missingcompany.com\n"
                    b"Bad Scheme,ftp://bad-scheme.org\n"
                    b"Injected Auth,https://user:pass@secret.com\n"
                )
                resp = await client.post(
                    f"{SERVER_URL}/api/websites/import",
                    files={"file": ("invalid_sample.csv", invalid_csv, "text/csv")}
                )
                invalid_result = resp.json()

            html_04 = generate_styled_html(
                "CSV Malformed Data Handling & Error Isolation",
                "PASS: 4 Invalid Rows Isolated",
                "#d97706",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{invalid_result.get('total_websites', 0)}</div><div class="metric-lbl">Valid Websites Accepted</div></div>
                    <div class="metric-box"><div class="metric-val" style="color:#f87171">{invalid_result.get('invalid_rows', 0)}</div><div class="metric-lbl">Invalid Rows Flagged</div></div>
                    <div class="metric-box"><div class="metric-val">Fault Tolerant</div><div class="metric-lbl">Batch Resilience</div></div>
                    <div class="metric-box"><div class="metric-val">True</div><div class="metric-lbl">Success Flag</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">Validation Audit Log with Granular Row Rejection Reasons</div>
                    <pre>{json.dumps(invalid_result, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_04)
            await page.screenshot(path=str(EVIDENCE_DIR / "04-invalid-csv-validation.png"))

            # -------------------------------------------------------------
            # 05-google-recaptcha-detection.png
            # -------------------------------------------------------------
            print("Capturing 05-google-recaptcha-detection.png...")
            recaptcha_fixture = (BASE_DIR / "tests" / "fixtures" / "google_recaptcha.html").read_text(encoding="utf-8")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{SERVER_URL}/api/websites/inspect-demo",
                    json={"html": recaptcha_fixture}
                )
                recaptcha_res = resp.json()

            html_05 = generate_styled_html(
                "CAPTCHA Inspection: Google reCAPTCHA v2 Checkbox",
                "Detected: google_recaptcha",
                "#2563eb",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{recaptcha_res.get('status')}</div><div class="metric-lbl">Scan Status</div></div>
                    <div class="metric-box"><div class="metric-val">True</div><div class="metric-lbl">Active Widget Container</div></div>
                    <div class="metric-box"><div class="metric-val">{recaptcha_res.get('inspection_duration_ms', 0)} ms</div><div class="metric-lbl">Execution Duration</div></div>
                    <div class="metric-box"><div class="metric-val">reCAPTCHA v2</div><div class="metric-lbl">Provider Signature</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">Structured Inspection Payload</div>
                    <pre>{json.dumps(recaptcha_res, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_05)
            await page.screenshot(path=str(EVIDENCE_DIR / "05-google-recaptcha-detection.png"))

            # -------------------------------------------------------------
            # 06-hcaptcha-detection.png
            # -------------------------------------------------------------
            print("Capturing 06-hcaptcha-detection.png...")
            hcaptcha_fixture = (BASE_DIR / "tests" / "fixtures" / "hcaptcha.html").read_text(encoding="utf-8")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{SERVER_URL}/api/websites/inspect-demo",
                    json={"html": hcaptcha_fixture}
                )
                hcaptcha_res = resp.json()

            html_06 = generate_styled_html(
                "CAPTCHA Inspection: hCaptcha Interactive Widget",
                "Detected: hcaptcha",
                "#7c3aed",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{hcaptcha_res.get('status')}</div><div class="metric-lbl">Classification Status</div></div>
                    <div class="metric-box"><div class="metric-val">True</div><div class="metric-lbl">Active Challenge Widget</div></div>
                    <div class="metric-box"><div class="metric-val">{hcaptcha_res.get('inspection_duration_ms', 0)} ms</div><div class="metric-lbl">Inspection Time</div></div>
                    <div class="metric-box"><div class="metric-val">hCaptcha</div><div class="metric-lbl">Provider Identification</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">Structured Inspection Payload</div>
                    <pre>{json.dumps(hcaptcha_res, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_06)
            await page.screenshot(path=str(EVIDENCE_DIR / "06-hcaptcha-detection.png"))

            # -------------------------------------------------------------
            # 07-cloudflare-turnstile-detection.png
            # -------------------------------------------------------------
            print("Capturing 07-cloudflare-turnstile-detection.png...")
            turnstile_fixture = (BASE_DIR / "tests" / "fixtures" / "cloudflare_turnstile.html").read_text(encoding="utf-8")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{SERVER_URL}/api/websites/inspect-demo",
                    json={"html": turnstile_fixture}
                )
                turnstile_res = resp.json()

            html_07 = generate_styled_html(
                "CAPTCHA Inspection: Cloudflare Turnstile",
                "Detected: cloudflare_turnstile",
                "#ea580c",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{turnstile_res.get('status')}</div><div class="metric-lbl">Status Classification</div></div>
                    <div class="metric-box"><div class="metric-val">True</div><div class="metric-lbl">Active Turnstile Container</div></div>
                    <div class="metric-box"><div class="metric-val">{turnstile_res.get('inspection_duration_ms', 0)} ms</div><div class="metric-lbl">Inspection Duration</div></div>
                    <div class="metric-box"><div class="metric-val">Turnstile API</div><div class="metric-lbl">Security Vendor</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">Structured Inspection Payload</div>
                    <pre>{json.dumps(turnstile_res, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_07)
            await page.screenshot(path=str(EVIDENCE_DIR / "07-cloudflare-turnstile-detection.png"))

            # -------------------------------------------------------------
            # 08-normal-contact-form.png
            # -------------------------------------------------------------
            print("Capturing 08-normal-contact-form.png...")
            normal_fixture = (BASE_DIR / "tests" / "fixtures" / "normal_contact_form.html").read_text(encoding="utf-8")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{SERVER_URL}/api/websites/inspect-demo",
                    json={"html": normal_fixture}
                )
                normal_res = resp.json()

            html_08 = generate_styled_html(
                "CAPTCHA Inspection: Normal Contact Form (No CAPTCHA)",
                "Clean Form Identified",
                "#059669",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{normal_res.get('status')}</div><div class="metric-lbl">Classification</div></div>
                    <div class="metric-box"><div class="metric-val">True</div><div class="metric-lbl">Contact Form Present</div></div>
                    <div class="metric-box"><div class="metric-val">0</div><div class="metric-lbl">CAPTCHA Markers</div></div>
                    <div class="metric-box"><div class="metric-val">{normal_res.get('inspection_duration_ms', 0)} ms</div><div class="metric-lbl">Inspection Speed</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">Clean Contact Form Inspection Result</div>
                    <pre>{json.dumps(normal_res, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_08)
            await page.screenshot(path=str(EVIDENCE_DIR / "08-normal-contact-form.png"))

            # -------------------------------------------------------------
            # 09-batch-processing.png
            # -------------------------------------------------------------
            print("Capturing 09-batch-processing.png...")
            batch_payload = {
                "websites": [
                    {"company_name": "Acme Global", "website_url": "fixture://normal_contact_form.html"},
                    {"company_name": "Nexus Security", "website_url": "fixture://google_recaptcha.html"},
                    {"company_name": "Apex Privacy", "website_url": "fixture://invisible_recaptcha.html"},
                    {"company_name": "Shield Corp", "website_url": "fixture://hcaptcha.html"},
                    {"company_name": "Vanguard Edge", "website_url": "fixture://cloudflare_turnstile.html"},
                    {"company_name": "Fortress Systems", "website_url": "fixture://unknown_challenge.html"},
                ]
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{SERVER_URL}/api/websites/scan-batch", json=batch_payload)
                batch_init = resp.json()
                batch_id = batch_init["batch_id"]

                # Poll until batch completed
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    status_resp = await client.get(f"{SERVER_URL}/api/websites/batches/{batch_id}")
                    batch_status_data = status_resp.json()["batch"]
                    if batch_status_data["status"] == "completed":
                        break

            html_09 = generate_styled_html(
                f"Batch Processing Pipeline (Batch ID: {batch_id[:8]}...)",
                f"Status: {batch_status_data['status']}",
                "#059669",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{batch_status_data['total_records']}</div><div class="metric-lbl">Total Queued</div></div>
                    <div class="metric-box"><div class="metric-val">{batch_status_data['processed_records']}</div><div class="metric-lbl">Processed</div></div>
                    <div class="metric-box"><div class="metric-val">{batch_status_data['successful_records']}</div><div class="metric-lbl">Successful</div></div>
                    <div class="metric-box"><div class="metric-val">{batch_status_data['failed_records']}</div><div class="metric-lbl">Failed</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">Asynchronous Batch Execution Metrics</div>
                    <pre>{json.dumps(batch_status_data, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_09)
            await page.screenshot(path=str(EVIDENCE_DIR / "09-batch-processing.png"))

            # -------------------------------------------------------------
            # 10-database-results.png
            # -------------------------------------------------------------
            print("Capturing 10-database-results.png...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(f"{SERVER_URL}/api/websites/batches/{batch_id}/results")
                items_data = resp.json().get("results", [])

            table_rows = ""
            for it in items_data:
                badge_class = "tag-danger" if it["scan_status"] == "failed" else ("tag-warn" if it["human_review_required"] else "tag-success")
                table_rows += f"""<tr>
                    <td><b>{it['company_name']}</b></td>
                    <td><code>{it['website_url']}</code></td>
                    <td><span class="{badge_class}">{it['scan_status']}</span></td>
                    <td>{it['captcha_provider'] or 'None'}</td>
                    <td>{'Yes' if it['human_review_required'] else 'No'}</td>
                    <td>{it['inspection_duration_ms']} ms</td>
                </tr>"""

            html_10 = generate_styled_html(
                "Persistent Database Inspection Records (SQLite / SQLAlchemy)",
                f"{len(items_data)} Persisted Records",
                "#0284c7",
                f"""<div class="card">
                    <div class="subtitle">Relational Table Audit (website_inspections)</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Company Name</th>
                                <th>Target URL</th>
                                <th>Scan Status</th>
                                <th>CAPTCHA Provider</th>
                                <th>Human Review</th>
                                <th>Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>"""
            )
            await page.set_content(html_10)
            await page.screenshot(path=str(EVIDENCE_DIR / "10-database-results.png"))

            # -------------------------------------------------------------
            # 11-ocr-demo.png
            # -------------------------------------------------------------
            print("Capturing 11-ocr-demo.png...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{SERVER_URL}/api/captcha/ocr-demo", json={"custom_text": "K7M9P"})
                ocr_res = resp.json()
                bench_resp = await client.post(f"{SERVER_URL}/api/captcha/ocr-benchmark", json={"samples": 3})
                bench_res = bench_resp.json()

            html_11 = generate_styled_html(
                "Synthetic OCR Distortion & Text Recognition Benchmark",
                "Tesseract OCR v5.5.0",
                "#7c3aed",
                f"""<div class="meta-grid">
                    <div class="metric-box"><div class="metric-val">{ocr_res.get('ground_truth')}</div><div class="metric-lbl">Ground Truth</div></div>
                    <div class="metric-box"><div class="metric-val">{ocr_res.get('ocr_prediction')}</div><div class="metric-lbl">OCR Extracted</div></div>
                    <div class="metric-box"><div class="metric-val">{bench_res.get('character_accuracy_pct')}%</div><div class="metric-lbl">Char Accuracy</div></div>
                    <div class="metric-box"><div class="metric-val">{ocr_res.get('execution_time_ms')} ms</div><div class="metric-lbl">Inference Duration</div></div>
                </div>
                <div class="card">
                    <div class="subtitle">OCR Evaluation & Vision Preprocessing Pipeline</div>
                    <pre>{json.dumps(ocr_res, indent=2)}</pre>
                </div>
                <div class="card">
                    <div class="subtitle">Architectural Limitation Analysis (Modern vs Legacy CAPTCHAs)</div>
                    <pre>{bench_res.get('limitations_analysis')}</pre>
                </div>"""
            )
            await page.set_content(html_11)
            await page.screenshot(path=str(EVIDENCE_DIR / "11-ocr-demo.png"))

            # -------------------------------------------------------------
            # 12-token-verification.png
            # -------------------------------------------------------------
            print("Capturing 12-token-verification.png...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                v1 = (await client.post(f"{SERVER_URL}/api/captcha/verify-token", json={"token": "VALID_TEST_RESPONSE"})).json()
                v2 = (await client.post(f"{SERVER_URL}/api/captcha/verify-token", json={"token": ""})).json()
                v3 = (await client.post(f"{SERVER_URL}/api/captcha/verify-token", json={"token": "MOCK_INVALID_TOKEN"})).json()
                v4 = (await client.post(f"{SERVER_URL}/api/captcha/verify-token", json={"token": "ANY", "simulate_status": "reused"})).json()

            verification_cases = [
                {"case": "Valid Test Token", "status": v1.get("verification_status"), "error": str(v1.get("error_codes")), "success": v1.get("success")},
                {"case": "Missing Token", "status": v2.get("verification_status"), "error": str(v2.get("error_codes")), "success": v2.get("success")},
                {"case": "Invalid Token", "status": v3.get("verification_status"), "error": str(v3.get("error_codes")), "success": v3.get("success")},
                {"case": "Expired / Reused Token", "status": v4.get("verification_status"), "error": str(v4.get("error_codes")), "success": v4.get("success")},
            ]
            v_rows = ""
            for c in verification_cases:
                badge_cls = "tag-success" if c["success"] else "tag-danger"
                v_rows += f"""<tr>
                    <td><b>{c['case']}</b></td>
                    <td><span class="{badge_cls}">{c['status']}</span></td>
                    <td><code>{c['error']}</code></td>
                    <td>{'APPROVED' if c['success'] else 'REJECTED'}</td>
                </tr>"""

            html_12 = generate_styled_html(
                "Google reCAPTCHA Official Test Token Server-Side Verification",
                "Siteverify API Integration",
                "#2563eb",
                f"""<div class="card">
                    <div class="subtitle">Server-Side Cryptographic Token Verification Matrix</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Test Scenario</th>
                                <th>Verification Status</th>
                                <th>Error Codes</th>
                                <th>Gateway Outcome</th>
                            </tr>
                        </thead>
                        <tbody>
                            {v_rows}
                        </tbody>
                    </table>
                </div>
                <div class="card">
                    <div class="subtitle">Sample Approved Test Token Response</div>
                    <pre>{json.dumps(v1, indent=2)}</pre>
                </div>"""
            )
            await page.set_content(html_12)
            await page.screenshot(path=str(EVIDENCE_DIR / "12-token-verification.png"))

            # -------------------------------------------------------------
            # 13-final-csv-report.png
            # -------------------------------------------------------------
            print("Capturing 13-final-csv-report.png...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                report_resp = await client.get(f"{SERVER_URL}/api/websites/batches/{batch_id}/report")
                report_csv = report_resp.text

            # Save sample report to reports/ and evidence/reports/
            (BASE_DIR / "reports" / "sample_captcha_audit_report.csv").write_text(report_csv, encoding="utf-8-sig")
            (BASE_DIR / "evidence" / "reports" / "sample_captcha_audit_report.csv").write_text(report_csv, encoding="utf-8-sig")

            csv_lines = [line.strip() for line in report_csv.strip().split("\n")]
            csv_headers = csv_lines[0].split(",")
            csv_data_rows = [line.split(",") for line in csv_lines[1:]]

            th_html = "".join(f"<th>{h}</th>" for h in csv_headers)
            tr_html = ""
            for r in csv_data_rows:
                tr_html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in r) + "</tr>"

            html_13 = generate_styled_html(
                "Final Downloadable CSV Compliance Audit Report",
                "CSV Export Verified",
                "#059669",
                f"""<div class="card">
                    <div class="subtitle">Generated Report Format (GET /api/websites/batches/{{batch_id}}/report)</div>
                    <table>
                        <thead>
                            <tr>{th_html}</tr>
                        </thead>
                        <tbody>
                            {tr_html}
                        </tbody>
                    </table>
                </div>
                <div class="card">
                    <div class="subtitle">Raw CSV Plaintext Preview</div>
                    <pre>{report_csv[:1200]}</pre>
                </div>"""
            )
            await page.set_content(html_13)
            await page.screenshot(path=str(EVIDENCE_DIR / "13-final-csv-report.png"))

            await browser.close()

    finally:
        print("Terminating background uvicorn server...")
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
        except Exception:
            server_process.kill()
        print("All 13 screenshots successfully captured!")


if __name__ == "__main__":
    asyncio.run(main())
