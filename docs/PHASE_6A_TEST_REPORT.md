# Phase 6A — Test & Verification Report

All figures below come from commands executed during Phase 6A on Windows 10, Python 3.12, Playwright Chromium. Nothing is estimated.

## 1. Backend regression + new tests

| Run | Interpreter | Result |
| :--- | :--- | :--- |
| `pytest tests/` (full suite) | **brand-new virtualenv** created from the updated `requirements.txt` | **223 passed, 1 skipped**, 0 failed (121 s) |
| `pytest tests/test_phase6a_security.py` | project venv | 138 passed, 1 skipped, 0 failed |

Collected tests: 224 = **85 pre-existing (all still pass, unmodified assertions)** + **139 new** in `tests/test_phase6a_security.py`.

Per-file collection: `test_api_endpoints` 9, `test_captcha_intelligence` 19, `test_csv_importer` 5, `test_detection_fixtures` 6, `test_ocr_and_token` 8, `test_phase5_security` 14, `test_security` 7, `test_smart_crawler` 17, `test_phase6a_security` 139.
(The Phase 5 report's table summed to 59 + "13 routes" for "85"; the real per-file breakdown is above. The total of 85 was correct.)

**The one skip:** `test_fixture_symlink_escape_rejected` — this Windows account cannot create symlinks (`OSError`). The symlink/containment logic (`resolve()` then `parent == FIXTURES_DIR`) is therefore **not exercised by an automated test on this machine**. It runs on accounts with symlink privilege (Developer Mode / Linux CI).

An earlier run during development showed 5 failures, which led to a real design fix, recorded here for transparency:

- 4 failures proved that passing 3xx responses to Chromium bypassed the guard (Chromium followed the redirect itself: it timed out connecting to `10.0.0.1`, and fetched `example.com`). The guard now follows redirects itself, and the tests then passed.
- 1 failure was the built-frontend bundle check detecting the *old* credentials in a stale `.next/` build; it passed after rebuilding.

## 2. New test coverage by finding

| Finding | What is tested |
| :--- | :--- |
| **H2** fixture traversal | 24 hostile names at the validator and 23 at the loader (`../.env`, `..\.env`, `%2e%2e%2f`, double-encoded `%252e…`, `..%5c`, `/etc/passwd`, `C:\Windows\win.ini`, `c:win.ini`, NUL injection, subdirs, `.env`, wrong extension, NTFS stream, empty); valid fixture still loads; fixtures refused when `APP_ENV=production` even with `ALLOW_FIXTURES=true`; CSV importer rejects traversal rows (4 of 5 rows rejected, legit row kept); end-to-end batch with `fixture://../../.env` → `failed`, `Fixture rejected`, no title leaked; batch fixtures blocked in production. *(Symlink escape: skipped, see above.)* |
| **H4** IP ranges | 43 blocked addresses (RFC 1918, loopback, link-local, metadata, **CGNAT** edges 100.64.0.0/100.127.255.255, 0.0.0.0/8, class E, broadcast, multicast v4/v6, **IPv6 ULA**, **IPv6 link-local**, unspecified, documentation, benchmarking, IPv4-mapped, NAT64, 6to4, Teredo); 5 public v4/v6 addresses allowed; 9 URL literals through `validate_target_url`; hostname resolving to CGNAT blocked; a single bad DNS record rejects a multi-record host. |
| **H3** rate limiter | Pure-function tests: header ignored by default, ignored from untrusted peer, rightmost-untrusted semantics from a trusted proxy (spoofed prefix ignored), chained trusted proxies, malformed chain, bad config. **Integration:** 9 logins with *rotating spoofed* `X-Forwarded-For` → first 5 are 401, remaining are **429**; and with a configured trusted proxy, distinct forwarded clients get independent buckets. |
| **H1** batch SSRF | Real Chromium against a local server: safe same-host redirect followed; redirects to `10.0.0.1`, `169.254.169.254`, `100.64.0.1` and a cross-domain host are **blocked** and recorded in `network_guard.blocked_requests`; page subresources to `10.0.0.5`, metadata IP, CGNAT and `192.168.1.1` (img, script, `fetch`) are blocked; private target rejected before any network use; **demo HTML cannot make any request** (server hit log checked); **DNS-rebinding** simulation (public answer then `127.0.0.1`) is rejected; the fetch connects to the **validated IP** with `Host`/SNI set to the hostname; `httpx` is created with `verify=True, trust_env=False`; `SCAN_ALLOW_INVALID_CERTS` rejected in production; source contains no `ignore_https_errors=True`. |
| Credentials | Source scan (frontend + app + tests) finds no forbidden credential strings; **built bundle scan** of `frontend/.next/static` finds none; CLI password resolution works without a command-line password. |
| Dependencies | An AST scan of every import in `app/`, `tests/`, `alembic/` and root scripts must map to a declared requirement; PyJWT, bcrypt and alembic must be declared with version bounds. |

Not verified by test (stated plainly): real TLS handshakes/certificate rejection against a live HTTPS server (only the `verify=True` setting and SNI/Host pinning are asserted), and real-world DNS rebinding timing against a live authoritative server (simulated by patching `getaddrinfo`).

## 3. Frontend production build

`npm run build` (Next.js 16.4.5, Turbopack) after the login-page change and with `.next/` deleted first: compiled successfully, TypeScript finished with no errors, **13/13 static pages generated**. A recursive search of the new `.next/` output for `AdminSecure2026` / `OperatorPass123` returned nothing. (Lint was not run.)

## 4. No hard-coded credentials

- Repository search (excluding `node_modules`, `venv`, `.next`, `evidence`, caches) before the change matched `frontend/app/login/page.tsx`, `tests/capture_phase5_evidence.py`, `tests/conftest.py`; after the change the only occurrences are the forbidden-pattern list inside the new regression test and these Phase 6A documents that name the removed strings. (Excluded from that search: the untracked nested copy `evidence/captcha-automation-tool/`, which holds an old snapshot of the repo and still contains the old strings — it should be deleted or kept out of version control; see review notes.)
- Built bundle: clean (above).

## 5. Fresh dependency installation

- New venv created in the session scratchpad with `python -m venv`; `pip install --no-cache-dir -r requirements.txt` exited **0**.
- `import app.main, jwt, bcrypt, alembic` succeeded in that venv, and the full 224-test suite ran in it (section 1).
- CLI check (temp SQLite DB): `create-admin --generate-password` created an admin and printed the password once; `list-users` listed it; a 5-character `ADMIN_PASSWORD` was rejected (minimum 12).

## 6. No unintended removals

- `git diff --stat` shows deletions only in: the login-page credentials panel and handler; the old inline crawler route interceptor (replaced by the shared guard); the old `is_ip_allowed` body and `fixture` path join (replaced); the `ignore_https_errors=True` arguments; hard-coded passwords in `conftest.py` / evidence script.
- All 85 pre-existing tests pass unchanged. API routes, response shapes (batch/crawl results gained an additive `network_guard` field) and frontend pages are otherwise untouched.
- Intentional behavior changes: fixtures are unavailable outside development/test; redirects/subresources that violate the SSRF policy now fail (previously they were fetched); third-party CDN subresources are blocked unless allow-listed (unchanged from the Phase 5 crawler policy, now also applied to batch scans).

## 7. Not run

`tests/run_acceptance_tests.py`, `tests/verify_frontend_e2e.py`, `capture_evidence.py` and `tests/capture_phase5_evidence.py` (they start servers/browsers against a running stack and, for the last, now need `E2E_*` credentials). They were not part of the pytest suite and were not executed in Phase 6A.
