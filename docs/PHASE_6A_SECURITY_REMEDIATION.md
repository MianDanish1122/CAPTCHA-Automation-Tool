# Phase 6A — Critical Security Remediation

**Branch:** `phase-6-security-remediation` (from `phase-5-security-hardening` @ `98f1457`)
**Scope:** findings H1–H4, hard-coded frontend credentials, dependency declarations.
**Out of scope (Phase 6B / 7):** evidence authentication, `/health` trimming, token revocation, request-size limits, audit tamper-evidence, OCR quality.

No CAPTCHA-bypass capability was added. Synthetic CAPTCHA testing, official test-mode verification, authorized fixtures and human review are unchanged.

---

## H2 — `fixture://` path traversal

**Before:** `batch_processor.py` did `url.replace("fixture://", "")` and joined it onto `tests/fixtures/`, so `fixture://../../.env` read arbitrary files. The CSV importer accepted any `fixture:` URL.

**Now** (`app/services/fixture_loader.py`):

- A fixture reference is only a bare file name matching `^[A-Za-z0-9_-]{1,100}\.html$`.
- Percent-encoding (including double-encoding) is decoded and any name that changes is rejected. `/`, `\`, `:`, `..`, NUL/control characters, drive letters, NTFS streams and other extensions fail the allow-list.
- The path is `resolve()`d and must have `parent == FIXTURES_DIR.resolve()` and be a regular file, which defeats symlink escapes.
- 512 KB size cap.
- **Production safety:** `settings.fixtures_enabled` is true only when `APP_ENV` is `development` or `test` (and `ALLOW_FIXTURES` is not false). In staging/production fixtures are refused at CSV import and at batch processing regardless of configuration.
- The CSV importer and batch processor both use the loader; a rejected fixture row fails with `Fixture rejected: …` and leaks nothing.

## H4 — IP range validation

`SecurityGuard.is_ip_allowed` was rewritten around a *global-unicast-only* policy:

- Explicit deny list (`_BLOCKED_NETWORKS`) independent of stdlib classification, including **CGNAT 100.64.0.0/10** (previously *allowed*), `0.0.0.0/8`, RFC 1918, loopback, link-local, TEST-NETs, benchmarking, multicast, class E/broadcast, IPv6 ULA `fc00::/7`, link-local `fe80::/10`, site-local, multicast, documentation, discard and Teredo ranges.
- IPv6 forms that embed IPv4 (IPv4-mapped, NAT64, 6to4) are unwrapped and re-checked; Teredo is rejected. Transition-mechanism addresses are rejected even when the embedded IPv4 is public (conservative).
- Anything not `is_global` is rejected as a final backstop; zone IDs are stripped.
- New `resolve_public_addresses()` resolves a host and rejects it if **any** record is non-public.

## H1 — Batch scanner SSRF, redirects, subresources, DNS rebinding, TLS

**Before:** only the first URL of a batch scan was validated; Chromium then followed redirects and loaded subresources unchecked, resolved DNS itself, and ran with `ignore_https_errors=True`. `inspect-demo` rendered untrusted HTML with full network access.

**Now** every browsing context (single scans via `SmartCrawler`, batch scans via `inspect_website`, demo/fixture rendering) is created by `new_guarded_context()` in `app/services/network_guard.py`:

1. **All requests are routed** through `NetworkGuard` (navigations, subresources, XHR/fetch, iframes). Non-HTTP(S) schemes are aborted. Service workers are blocked and WebSockets are closed, because both bypass routing.
2. **Every request** is validated with `SecurityGuard.validate_target_url` (scheme, port allow-list, embedded credentials, domain allow-list, IP policy).
3. **Redirects are followed by the guard, hop by hop**, with the same validation plus the same-domain rule, up to 10 hops. *Design note:* an early version passed 3xx responses to Chromium; testing showed Chromium follows a fulfilled redirect **without routing the next hop**, which was a bypass (it connected to `10.0.0.1` and fetched `example.com` directly). Redirect responses are therefore never handed to Chromium. The crawler/scanner use `guard.effective_url()` for the post-redirect URL.
4. **DNS rebinding / TOCTOU:** the guard resolves the host once, validates *all* answers, then makes the HTTP request itself with `httpx`, connecting **directly to the validated IP** (SNI and certificate verification use the original hostname; `Host` header preserved). Chromium never performs its own lookup or opens its own socket for guarded traffic, so there is no second resolution to re-point. `trust_env=False` prevents proxy env vars from changing the route.
5. **TLS validation is on.** `ignore_https_errors` is removed everywhere; `httpx` verifies certificates. `SCAN_ALLOW_INVALID_CERTS` exists as an explicit, default-off development opt-in and is **rejected at startup** in staging/production.
6. **Demo HTML** (`inspect_local_demo`, used for `/inspect-demo*` and fixtures) runs in `block_all_network` mode: no outbound request is ever made.
7. Responses are capped (`GUARD_MAX_RESPONSE_BYTES`, default 10 MB). Blocked requests are recorded and returned as `network_guard.blocked_requests` in batch scan results.

**Behavioral notes / limits**

- Because the guard performs the fetch, cookies set by *intermediate redirect hops* are not forwarded, and brotli is not requested (`Accept-Encoding: gzip, deflate`). These do not affect CAPTCHA detection.
- Subresources must satisfy the same domain allow-list as pages (unchanged from the Phase 5 crawler); third-party CDN scripts are therefore blocked unless allow-listed.
- Relative subresource URLs on a redirected document resolve against the pre-redirect URL inside Chromium (harmless 404s; link discovery uses the final URL).

## H3 — Rate-limit bypass via `X-Forwarded-For`

**Before:** the limiter used the first `X-Forwarded-For` value from any client, so rotating the header defeated the login limit.

**Now** (`app/services/client_ip.py`): forwarding headers are ignored unless the direct TCP peer is in `TRUSTED_PROXIES` (comma-separated IPs/CIDRs, default empty). For a trusted peer the header is read **right-to-left**, skipping trusted proxies; the first untrusted address is the client, so values a client prepended are never used. Malformed chains fall back to the peer. Audit-log IP addresses use the same helper.

Configuration:

```env
# only if a proxy you operate (e.g. nginx at 10.0.0.2) sits in front of the app
TRUSTED_PROXIES=10.0.0.2
```

The proxy must *append* the real client address (`proxy_add_x_forwarded_for`, as in `docs/PHASE_5_DEPLOYMENT_GUIDE.md`). The limiter is still per-process memory (Redis is a 6B/infra item).

## Hard-coded frontend credentials

- Removed the "Quick Test Credentials" panel and `handleQuickLogin` (`admin / AdminSecure2026!`, `operator / OperatorPass123!`) from `frontend/app/login/page.tsx`. A rebuilt production bundle was grepped: no credential strings remain.
- `tests/conftest.py` now seeds test users with random passwords (tests authenticate with signed tokens, not passwords).
- `tests/capture_phase5_evidence.py` reads `E2E_OPERATOR_*` / `E2E_ADMIN_*` from the environment.
- **Provisioning:** `python -m app.cli create-admin --username … --email …` now prompts for a password (hidden, confirmed, min 12), or accepts `ADMIN_PASSWORD`, or `--generate-password` (random, printed once). `--password` still works but warns that it leaks into shell history. The same applies to `create-user`.
- **Not yet addressed (6B):** the unauthenticated, first-caller-wins `POST /api/auth/setup-initial-admin` endpoint. Until 6B, prefer the CLI and note the endpoint closes once any user exists.

## Dependency declarations

`requirements.txt` now declares `PyJWT>=2.8,<3`, `bcrypt>=4.1,<6`, `alembic>=1.13,<2`, and `numpy`. A test parses every import in `app/`, `tests/`, `alembic/` and root scripts and fails if a third-party import is undeclared. Clean installation was verified in a brand-new virtual environment (see the test report).

## Files

New: `app/services/{fixture_loader,network_guard,client_ip}.py`, `tests/test_phase6a_security.py`.
Changed: `config.py`, `cli.py`, `security_guard.py`, `browser_scanner.py`, `smart_crawler.py`, `batch_processor.py`, `csv_importer.py`, `rate_limiter.py`, the three route modules (client IP helper), `requirements.txt`, `.env.example`, `frontend/app/login/page.tsx`, `tests/conftest.py`, `tests/capture_phase5_evidence.py`.

Nothing was removed from the product; the only deleted UI element is the credentials panel.
