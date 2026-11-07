# Security Summary (Phases 5 → 7)

Detail lives in the phase documents (`PHASE_5_*`, `PHASE_6A_*`, `PHASE_6B_*`, `PHASE_6B_FINAL_*`). This page is the current consolidated view. Phase 7 **did not weaken** any of it; the changes that touch security are listed at the end.

| Area | Controls |
| :--- | :--- |
| Authentication | bcrypt (12 rounds); JWT HS256 with fixed algorithm list, required `exp/iat/sub/jti`; per-user `token_version`; server-side revocation (denylist) on logout, logout-all, admin revoke/deactivate; pre-6B tokens rejected by default; equal-work login (no username-timing); login rate limit |
| Authorization | admin/operator RBAC on every route; admin-only user management, audit log and chain verification; evidence screenshots only for authenticated users, only `scans/<uuid>/*.png|jpg` |
| Provisioning | no default credentials; CLI prompt/generate; HTTP bootstrap disabled unless a ≥ 24-char setup token is configured, single-use, serialised, audited |
| SSRF / egress | all browser traffic through `NetworkGuard`: scheme/port/credential checks, domain allow-list, global-unicast-only IP policy (incl. CGNAT, ULA, IPv4-mapped/NAT64/6to4/Teredo), manual validated redirects, DNS-pinned fetch, TLS verification on, WebSockets and service workers blocked, response size cap; untrusted HTML runs with no network |
| Input limits | JSON ≤ 2 MB, multipart ≤ CSV limit, HTML ≤ 200 k chars, images ≤ 1 MB and ≤ 4 MP with format validation, field length/pattern limits |
| Abuse controls | per-IP rate limits (login, compute, admin, bootstrap, default); forwarding headers trusted only from configured proxies; concurrent crawl/batch/per-user job limits |
| Audit | HMAC hash-chained, append-only (DB triggers), independent `AUDIT_HMAC_KEY` with key ring; verification endpoint/CLI; redaction of secrets/JWTs/URL credentials and attempted usernames; sanitised request IDs; backup/restore with head verification |
| Secrets | `.env` git-ignored; production config validation (JWT ≥ 32 chars, independent audit key, no dev loopback/fixtures/invalid-cert flag); tokens and provider secrets never stored or returned |
| Web | CORS allow-list; security headers (`nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` for `/api`); minimal public `/health` |
| CAPTCHA safety | client-claimed `is_synthetic`/`is_official_test` validated server-side; production challenges → human review; no solving/bypass of third-party CAPTCHAs |
| Dependencies | declared with bounds; clean-install verified in Phase 6A |

## Changes in Phase 7 touching security
- Verification can no longer return success when the provider is unreachable (previous fake "offline verified").
- Verification responses are labelled by mode; simulations can never succeed; client assertions ignored.
- New persisted tables (`verification_records`, `ocr_benchmark_runs`) hold no tokens/secrets.
- Global exception handlers return generic messages (no SQL/paths); database failures → 503.
- New endpoints (`/api/stats/*`, `/api/captcha/ocr-benchmark/runs`, `/verification/*`) are authenticated and covered by the default rate limit.
- Crawler no longer leaves cancelled/failed-to-start scans in `crawling`.

## Residual risks
See `docs/KNOWN_LIMITATIONS.md` (single-process state, SQLite, `localStorage` JWT without CSP, externally anchored audit head, in-memory rate limiter).
