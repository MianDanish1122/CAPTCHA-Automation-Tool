# System Architecture (current, Phase 7)

```
 Browser (Next.js dashboard, :3000)
        │  JWT bearer (server-side revocation)         screenshots fetched with the token (blob)
        ▼
 FastAPI (:8000)  ── middleware: body-size limit · request-id · security headers · CORS · error handlers
   routes:  /api/auth  /api/websites  /api/captcha  /api/stats  /api/evidence
        │
        ├─ Auth & audit ......... bcrypt, JWT(jti, ver), denylist, RBAC, HMAC hash-chained audit log, rate limits, job limits
        ├─ Inspection ........... SmartCrawler / batch scanner → Playwright Chromium
        │        every request ──► NetworkGuard (SSRF policy, allow-list, manual validated redirects,
        │                           DNS-pinned httpx fetch, TLS verification ON, WebSockets/service workers blocked)
        ├─ CAPTCHA intelligence . rule-based classification → handling strategy
        │        none ─► completed | synthetic image ─► OCR engines | official test key ─► provider verification
        │        production provider / interstitial ─► HUMAN REVIEW queue (append-only decision history)
        ├─ OCR (app/ocr) ........ generator · preprocess · segmentation · HOG+MLP model · Tesseract · hybrid router · metrics
        ├─ Verification ......... token_verifier ─► provider siteverify (reCAPTCHA / hCaptcha / Turnstile) | simulated | local
        └─ Persistence .......... SQLAlchemy ─► SQLite (Alembic migrations)
                                   url_scans · discovered_pages · human_reviews(+decisions) · captcha_intelligence
                                   ocr_evaluations · ocr_benchmark_runs · verification_records · users · revoked_tokens · audit_logs
 Offline tooling: scripts/ocr_benchmark.py (dataset, train, experiments, evaluate, import) · scripts/token_acquisition_demo.py
```

## Request flows

1. **Inspect a site:** `POST /api/websites/inspect-url` → capacity check (job manager) → SSRF pre-check → crawler opens a guarded browser context → each page: robots check, navigation through the guard, screenshot, contact-page scoring, CAPTCHA detection → rows persisted → results/evidence UI. Production CAPTCHA ⇒ review case, never solved.
2. **OCR evaluation:** UI/API selects engine (`hybrid` default) → image → engine → prediction + latency → stored with the *true* label (generated or dataset sample) → aggregated by `/api/stats/summary`.
3. **Verification:** request → local validation (missing/malformed) → simulation branch (no network) **or** provider call with timeout → strict response validation → `verification_mode`/`outcome` → persisted (no token) → UI badge.
4. **Evaluation report:** `/api/stats/summary` and `/report` read only persisted rows; every block returns its denominator and time range.

## Design decisions

| Decision | Reason |
| :--- | :--- |
| Egress guard performs the fetch itself (DNS pinning) and follows redirects hop by hop | Chromium follows a fulfilled redirect without routing the next hop (found and fixed in 6A) |
| `success` in verification means "the provider said so" | prevents simulations, flags or outages from looking like verification |
| Custom model in NumPy with an in-repo HOG | no heavyweight framework; OpenCV 5 removed `HOGDescriptor`; fully reproducible from seeds |
| Held-out splits by disjoint seed ranges + hash-verified files | evaluation integrity and tamper detection |
| Additive, idempotent Alembic migrations + guarded destructive downgrades | existing databases upgrade without data loss |
| Single-process assumptions (audit lock, rate limiter, job registry) | documented limit; scaling requires shared stores |
