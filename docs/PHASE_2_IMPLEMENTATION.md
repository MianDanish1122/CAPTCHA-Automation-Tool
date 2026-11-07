# Technology Brainz — CAPTCHA Inspector
## Phase 2: Implementation & Engineering Report
### Smart Website Crawler Engine

## 1. Executive Summary

Phase 2 successfully delivered the **Smart Website Crawler Engine** for the **Technology Brainz — CAPTCHA Inspector** platform. 

Moving beyond static HTML fixture inspection, Phase 2 implements a real, automated browser crawler driven by Playwright Chromium that:
- Validates URLs and strictly guards against SSRF, cross-domain jumps, and cloud metadata access.
- Traverses websites up to configurable crawl limits (default: 10 pages per domain, max depth 2).
- Intelligently prioritizes candidate links using anchor text and URL path heuristics.
- Classifies discovered pages into `contact_page`, `support_page`, `general_page`, or `unknown` with a 0.0–1.0 confidence score and evidence explanation.
- Inspects form elements (inputs, textareas, submit buttons) and detects CAPTCHA providers (reCAPTCHA, hCaptcha, Turnstile, interstitial challenges).
- Enforces an ethical security policy: **never** submits contact forms and **never** bypasses third-party challenges (`human_review_required=True`).
- Automatically captures full-context evidence screenshots stored under `evidence/scans/<scan_id>/`.
- Exposes three new RESTful endpoints (`/inspect-url`, `/scans/{scan_id}`, `/scans/{scan_id}/results`).
- Fully persists crawl runs and itemized page discoveries to SQLite via SQLAlchemy.

All 52 automated tests in the test suite pass with 100% success.

---

## 2. Architecture & Crawling Engine Design

```
[ User / Client Request ]
           │
           ▼
[ POST /api/websites/inspect-url ]
           │
           ├─► [ SecurityGuard: SSRF, IP literal, Allowlist Pre-check ]
           │
           ▼
[ SmartCrawler Engine ] ◄─── Config: max_pages=10, max_depth=2, timeouts
           │
           ├─► 1. Robots.txt Compliance Check
           ├─► 2. Priority BFS Queue (Depth + Link Scoring)
           │
           ▼
[ Playwright Browser Context ]
   │
   ├─► Page 0: Root Homepage Navigation
   │     ├─ Redirect Security Validation (detects cross-domain/SSRF hops)
   │     ├─ Canonical URL Extraction
   │     ├─ Same-Domain Candidate Link Harvester (excludes static assets)
   │     ├─ Priority Scoring (contact/support signals get priority in queue)
   │     └─ Evidence Screenshot Capture -> evidence/scans/<scan_id>/
   │
   ├─► Page 1: High-Priority Candidate (e.g. /contact-us)
   │     ├─ DOM Form Analysis (form count, inputs, textarea)
   │     ├─ CAPTCHA Provider Detection (reCAPTCHA, hCaptcha, Turnstile)
   │     ├─ Contact Page Classification & Confidence Scoring
   │     └─ Evidence Screenshot Capture -> evidence/scans/<scan_id>/
   │
   └─► Page 2: Support Candidate (e.g. /support)
         ├─ Support Keywords & Ticket Form Inspection
         ├─ Classification: support_page
         └─ Evidence Screenshot Capture -> evidence/scans/<scan_id>/
           │
           ▼
[ SQLite Database: UrlScan & DiscoveredPage ]
```

---

## 3. Heuristics & Scoring Engine

The discovery engine classifies pages without blind crawling by applying multi-factor heuristic weights:

### Factor Weights

| Signal Source | Evaluation Criteria | Contact Weight | Support Weight |
| :--- | :--- | :--- | :--- |
| **URL Path** | `/contact`, `/contact-us`, `/get-in-touch`, `/inquiry` | +0.40 | — |
| **URL Path** | `/support`, `/help`, `/customer-service`, `/faq` | — | +0.40 |
| **Anchor Text** | "Contact Us", "Get in Touch", "Reach Us", "Email Us" | +0.25 | — |
| **Anchor Text** | "Customer Support", "Help Center", "Submit a Ticket" | — | +0.25 |
| **Page Title** | `<title>` contains contact keywords | +0.25 | — |
| **Page Title** | `<title>` contains support/help keywords | — | +0.25 |
| **Content Text** | Phrases like "send a message", "phone number", "our office" | +0.15 | — |
| **Content Text** | Phrases like "knowledge base", "help desk", "frequently asked" | — | +0.15 |
| **Form Presence** | `<form>` with `<textarea>` (message field) | +0.25 | — |
| **Form Presence** | `<form>` with interactive `<input>` fields | +0.15 | — |

### Classification Rules

1. **`contact_page`**: `contact_score >= 0.45` and `contact_score >= support_score`. Confidence is set to `min(contact_score, 1.0)`.
2. **`support_page`**: `support_score >= 0.45` and `support_score > contact_score`. Confidence is set to `min(support_score, 1.0)`.
3. **`general_page`**: Assigned to root landing pages (depth 0) or general content pages where contact/support scores remain below 0.25.
4. **`unknown`**: Assigned when signals are ambiguous or conflicting.

Every result contains an `evidence` JSON object breaking down matched signals for full auditability:
```json
{
  "path_signals": ["Path matches contact keyword 'contact'"],
  "anchor_signals": ["Anchor text matches contact keyword 'contact us'"],
  "title_signals": ["Title matches contact keyword 'contact'"],
  "content_signals": ["Body contains contact phrase 'send a message'"],
  "form_signals": [
    "Page contains 1 form(s)",
    "Multi-line textarea detected (strong contact indicator)"
  ],
  "contact_score": 0.95,
  "support_score": 0.0,
  "classification_reason": "Classified as contact_page (score 0.95) based on URL path, anchor text, and form signals."
}
```

---

## 4. Crawl Control & Deduplication

To prevent infinite crawl loops, spider traps, and resource exhaustion:
1. **URL Normalizer (`normalize_url`)**:
   - Resolves relative URLs (`/contact`, `help.html`, `../about`) against the current page's base URL.
   - Strips fragments (`#contact-section`, `#form`).
   - Removes non-functional marketing queries (`utm_source`, `utm_medium`, `fbclid`, `gclid`, `_ga`, etc.) while retaining query parameters needed for functional navigation.
   - Converts schemes and hostnames to lowercase and removes redundant default ports (`:80`, `:443`).
   - Normalizes trailing slashes to prevent `/contact` and `/contact/` from being crawled as separate URLs.
2. **Queue Deduplication**:
   - Maintains an in-memory `visited_urls` set.
   - Checks both `visited_urls` and queued URLs before enqueueing candidate links.
3. **Static Resource Exclusion**:
   - Skips media, stylesheets, scripts, documents, and archives (`.png`, `.jpg`, `.pdf`, `.zip`, `.js`, `.css`, etc.).
4. **Configurable Crawl Limits**:
   - `max_pages`: default 10 (hard limit: 20).
   - `max_depth`: default 2 (hard limit: 3).
   - `page_timeout`: 10,000 ms per navigation.
   - `total_timeout`: 60 seconds total execution.
5. **Robots.txt Adherence**:
   - Queries `/robots.txt` using Python's `urllib.robotparser.RobotFileParser` before crawling pages.
   - Gracefully falls back to allowed status if robots.txt is unavailable or returns 404/500.

---

## 5. Security & SSRF Enhancements

Phase 2 reinforced the `SecurityGuard` layer with defense-in-depth protections:

1. **IP Literal Detection**:
   - Immediate recognition of IP addresses in target URLs before allowlist lookup.
   - Rejects cloud metadata addresses (`169.254.169.254`, `fd00:ec2::254`) with specific policy alerts.
   - Rejects private subnets (RFC 1918 `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local, loopback, and multicast.
2. **Redirect Validation (`validate_redirect_url`)**:
   - Playwright navigations re-validate the final URL post-navigation.
   - Cross-domain HTTP redirects (e.g. 301/302 from `example.com` to `evil-attacker.com`) are rejected.
   - Internal redirection to local metadata or loopback IPs is intercepted and blocked.
3. **Gated Live Scanning**:
   - Live scanning remains off by default (`ENABLE_LIVE_SCAN=false`).
   - Only explicitly permitted domains in `ALLOWED_DOMAINS` or authorized test configurations (`allow_loopback=True`) can be crawled.
4. **Non-Intrusive CAPTCHA Policy**:
   - Contact forms are **never** submitted.
   - Any detected CAPTCHA challenge or interstitial triggers `human_review_required=True`.

---

## 6. Database Models & Schema Extensions

Phase 2 added two SQLAlchemy models to [app/models.py](file:///C:/Users/Hp/OneDrive/Desktop/captcha-automation-tool/app/models.py):

### `UrlScan` (`url_scans`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | UUID primary key. |
| `submitted_url` | `VARCHAR(1024)` | Original URL provided for inspection. |
| `domain` | `VARCHAR(255)` | Parsed target domain. |
| `status` | `VARCHAR(32)` | Execution state (`pending`, `crawling`, `completed`, `failed`). |
| `pages_crawled` | `INTEGER` | Total unique pages visited. |
| `contact_pages_found` | `INTEGER` | Count of pages classified as `contact_page`. |
| `captcha_detected` | `BOOLEAN` | Whether any CAPTCHA was identified across pages. |
| `captcha_providers` | `VARCHAR(255)` | Comma-separated list of identified providers. |
| `error_message` | `TEXT` | Failure explanation if scan did not complete. |
| `crawl_duration_ms` | `FLOAT` | Overall crawling runtime in milliseconds. |
| `created_at` | `DATETIME` | UTC timestamp of scan initiation. |
| `completed_at` | `DATETIME` | UTC timestamp of scan completion. |

### `DiscoveredPage` (`discovered_pages`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | UUID primary key. |
| `scan_id` | `VARCHAR(36)` | Foreign key referencing `url_scans.id`. |
| `url` | `VARCHAR(1024)` | Normalized final URL of discovered page. |
| `depth` | `INTEGER` | Crawl depth (0 for root, 1 for direct links, 2 for sub-links). |
| `page_title` | `VARCHAR(512)` | Extracted DOM document title. |
| `canonical_url` | `VARCHAR(1024)` | Canonical URL from `<link rel="canonical">`. |
| `classification` | `VARCHAR(32)` | `contact_page`, `support_page`, `general_page`, `unknown`. |
| `confidence_score` | `FLOAT` | Heuristic confidence metric (0.0 to 1.0). |
| `evidence` | `TEXT` | JSON-encoded breakdown of matched heuristics. |
| `contact_form_found`| `BOOLEAN` | True if interactive `<form>` elements exist. |
| `forms_count` | `INTEGER` | Count of `<form>` tags found in DOM. |
| `has_inputs` | `BOOLEAN` | True if text/email input fields exist. |
| `has_textarea` | `BOOLEAN` | True if multi-line message textarea exists. |
| `captcha_detected` | `BOOLEAN` | True if CAPTCHA widget or script is present. |
| `captcha_provider` | `VARCHAR(128)` | Name of provider (`google_recaptcha`, `hcaptcha`, etc.). |
| `is_active_challenge`| `BOOLEAN` | True if challenge requires interactive input. |
| `human_review_required`| `BOOLEAN`| Mandatory True if CAPTCHA detected. |
| `detection_method` | `VARCHAR(128)` | Detection approach used. |
| `screenshot_path` | `VARCHAR(512)` | Relative path to saved evidence screenshot. |
| `http_status` | `INTEGER` | Final HTTP status code (e.g. 200). |
| `crawl_duration_ms`| `FLOAT` | Per-page navigation and inspection duration. |

---

## 7. REST API Endpoints

### 1. `POST /api/websites/inspect-url`
Initiates a single-domain inspection and smart crawl run.

**Request Body**:
```json
{
  "url": "https://example.com",
  "max_pages": 10,
  "max_depth": 2,
  "background": false
}
```

**Response (Synchronous)**:
```json
{
  "success": true,
  "scan_id": "0d65be6e-5b82-41b0-9b8d-f2ccc0d544e8",
  "status": "completed",
  "submitted_url": "https://example.com",
  "domain": "example.com",
  "pages_crawled": 4,
  "contact_pages_found": 1,
  "captcha_detected": true,
  "captcha_providers": ["google_recaptcha"],
  "crawl_duration_ms": 3140.25,
  "results": [
    {
      "id": "...",
      "scan_id": "...",
      "url": "https://example.com/contact",
      "depth": 1,
      "page_title": "Contact Us - Acme Corp",
      "classification": "contact_page",
      "confidence_score": 0.95,
      "contact_form_found": true,
      "captcha_detected": true,
      "captcha_provider": "google_recaptcha",
      "human_review_required": true,
      "screenshot_path": "evidence/scans/0d65be6e.../page_2_contact.png"
    }
  ]
}
```

### 2. `GET /api/websites/scans/{scan_id}`
Returns scan execution status and summary metrics.

### 3. `GET /api/websites/scans/{scan_id}/results`
Returns comprehensive itemized discovery results, form details, classification scores, and screenshot paths.
