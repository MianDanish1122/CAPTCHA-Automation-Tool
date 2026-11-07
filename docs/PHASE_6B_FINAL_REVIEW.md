# Phase 6B — Final Review (conditions A–G)

**Branch:** `phase-6-security-remediation`, builds on `31d9ccf`.
No secret value appears in this document, in logs, or in the committed reports.

## A. Audit key

**Findings.** In 6B, `AUDIT_HMAC_KEY` was optional and, when empty, the chain key was *derived from `JWT_SECRET_KEY`*; the local `.env` had no `AUDIT_HMAC_KEY`. A JWT-secret leak would therefore also have allowed forging the audit chain, and rotating the JWT secret would have silently broken verification.

**Actions**
- A 32-byte random `AUDIT_HMAC_KEY` was generated and added to the local, git-ignored `.env` (value never displayed). Verified: set, ≥ 32 chars, ≠ `JWT_SECRET_KEY`.
- Independence is enforced in code: configuring a key equal to the JWT secret raises `AuditKeyError`; **production/staging startup requires** an `AUDIT_HMAC_KEY` ≥ 32 chars that differs from the JWT secret; a startup warning is logged when it is unset.
- **Key ring / rotation:** each entry now records a non-secret `key_id` (`sha256("audit-key-id:"+key)[:12]`). Verification picks the key by id from `AUDIT_HMAC_KEY` + `AUDIT_HMAC_KEYS_PREVIOUS`. Entries sealed before key ids existed are accepted with the legacy derived key only while `AUDIT_ALLOW_LEGACY_DERIVED_KEY=true`, and only as a **prefix** of the chain (a keyed entry downgraded to "unkeyed" is detected).
- `audit_key_status()` exposes only booleans, the key id and counts. Tests assert the secret never appears in status output or logs.
- The live development database (88 chained entries + 118 legacy) verifies **valid** under the new key ring.

**Storage guidance**
- Keep the key in a secret manager (Azure Key Vault, AWS Secrets Manager, HashiCorp Vault, Kubernetes/Docker secret) and inject it as an environment variable; never commit it, bake it into images, or put it in the same backup set/bucket as the database.
- Give it its own value — never reuse the JWT secret, setup token or any other credential. Restrict read access to the service account; limit who can read it in the vault.
- Generate with `python -m app.cli generate-audit-key` (prints a *new* random value only).

**Rotation procedure** (no entry is rewritten)
1. `python -m app.cli audit-verify` — must be valid. Record the head (`head_seq`, `head_hash`) off-box.
2. Generate a new key; set `AUDIT_HMAC_KEY=<new>` and `AUDIT_HMAC_KEYS_PREVIOUS=<old>` (comma-separate older ones). Restart.
3. `audit-verify` again; new entries carry the new `key_id`, old ones verify via the ring.
4. Retire an old key only after you accept losing verifiability of the segment it sealed (verification then reports "unknown key"). Keep old keys in the vault, not the running environment, if you archive old segments externally.
- If the key is **lost**, the existing log can no longer be verified; the entries themselves remain readable. If it **leaks**, rotate immediately and treat entries written before the rotation as unprotected against forgery by the leaker (anchor the head hashes you recorded earlier).

## B. Database migrations

**Findings.** `alembic/versions/5eb94b849402_*` was an empty stub (`pass`), `alembic_version` on existing databases points at it, and all schema changes in 6A/6B were applied only by `init_db()` (`create_all` + `ALTER TABLE`). `alembic upgrade head` on a new database produced an empty schema.

**Actions**
- `5eb94b849402` (baseline) now creates the Phase 1–5 schema **only for tables that don't exist** (idempotent), so new databases work and existing/stamped databases are untouched. Its downgrade drops everything and is guarded.
- New `6b01phase6security`: `users.token_version`; `audit_logs.seq/prev_hash/entry_hash/key_id` + index; `human_reviews.reviewed_by_id/reviewed_by_username/decision_count`; tables `revoked_tokens`, `review_decisions`; the four append-only triggers. Every step checks existence first.
- `alembic/env.py` now honors a programmatically supplied URL (previously it overwrote it), and picks batch mode from the real dialect.
- `app.database.init_db()` stays for development convenience; both paths are idempotent and converge on the same schema (a test compares the migrated schema to the ORM models to catch drift).

**Tests / evidence**
- A **real Phase 5 database** (a 442 KB snapshot found in the nested duplicate: 6 users, 41 audit rows, 97 reviews, 58 scans, 170 pages, 26 batches, 59 inspections, 86 intelligence records, 45 OCR records) was copied and upgraded: **every row in all 9 tables preserved with identical values**, `alembic_version = 6b01phase6security`, 4 triggers installed, new columns defaulted (`token_version=0`, `decision_count=0`, audit chain columns NULL = legacy).
- Automated: stamped-at-old-stub and never-stamped Phase 5 databases; migrated DB works with the application audit chain (legacy rows reported as unchained); idempotent on an app-built DB and on a second run; migrated schema == ORM schema; downgrade guarded; downgrade 6B→baseline removes only the 6B objects and preserves original values; re-upgrade works.

**Rollback.** Downgrades are **intentionally destructive** and refuse to run unless `ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1`: reverting `6b01phase6security` deletes the token revocation list, review decision history and the audit hash-chain columns (users, scans, reviews and audit rows themselves are kept); reverting the baseline drops all tables. **Take a backup (`python -m app.cli backup-db`) before any downgrade.** Production procedure: stop app → backup → `alembic upgrade head` → start → `audit-verify`.

## C. JWT session migration

**Findings.** Tokens issued before 6B have no `ver` claim; the 6B code treated a missing claim as version 0, so they stayed valid and could not be bulk-invalidated by a version bump from a missing claim. The decoder also did not require `exp`/`jti`.

**Actions**
- `jwt.decode` now **requires** `exp`, `iat`, `sub`, `jti` (a token without expiry is never accepted) and uses a fixed algorithm allow-list (`alg: none` rejected).
- **Controlled invalidation:** `JWT_REQUIRE_VER_CLAIM` (default **true**) rejects pre-6B tokens with "Session predates a security upgrade" → every user re-logs-in once after deployment. Set it to `false` only temporarily if a grace period is preferred (tokens then expire naturally within `ACCESS_TOKEN_EXPIRE_MINUTES`).
- New CLI `python -m app.cli invalidate-sessions --user NAME | --all` bumps `token_version` (emergency kill switch, works with the app stopped).
- Tested: new tokens accepted; pre-6B (no `ver`) rejected by default and accepted only in the explicit grace mode; expired; no `exp`; no `jti`; `alg: none`; wrong signature; revoked `jti` (other tokens unaffected); wrong `ver`; CLI invalidation kills existing tokens and a fresh login works.

## D. Browser verification (Playwright, real Chromium)

`tests/e2e_phase6b_browser.py` drove the production frontend (`npm run start`) against a real backend on an isolated, Alembic-migrated database (accounts created from environment-supplied random passwords). **32/32 checks passed**; report and screenshots in `evidence/phase6b/`. Covered: login page has no credential panel; operator login and dashboard; protected screenshot renders in the UI via an authenticated blob; the evidence request carried the bearer token; unauthenticated / garbage-token / legacy `/evidence` / traversal requests rejected (401/404); `/health` body is exactly `{"status":"healthy"}` and `/api/health/details` needs auth; operator gets 403 on audit logs and cannot create users and sees no audit section; logout clears storage, redirects, and the old token is **revoked** (401, cannot fetch evidence); signed-out navigation redirects to login; admin sees the audit trail, reads logs, chain verification is valid, no password appears in the audit log; no page errors, failed requests, HTTP ≥ 400 responses to application requests, or console errors.

**Defect found and fixed:** the first run failed one check — successful login triggered two navigations (`window.location.href` in the submit handler *and* in the `isAuthenticated` effect), producing `net::ERR_ABORTED` on `GET /`. The redundant navigation was removed from `frontend/app/login/page.tsx`; the re-run was clean.

## E. Audit verification, backup and restore

- Chain verification, modification, deletion and forged-hash detection: tested on isolated databases (6B tests + `test_phase6b_final.py`), including with triggers removed.
- **New CLI:** `backup-db` (SQLite online backup API — consistent while running — plus a `.head.json` sidecar with chain validity, `head_seq`, `head_hash`), `restore-db --file F [--expected-head-seq N --expected-head-hash H] --yes` (integrity check + chain verification of the candidate *before* anything is replaced; the current DB is kept as `pre_restore_*.db`; refuses without `--yes`), `audit-verify [--expected-head-seq/--expected-head-hash]` (exit code 1 when invalid).
- Tested: backup consistent and records head; restore requires confirmation and preserves the previous DB; tampered backup refused (live DB untouched); corrupt file refused; **rollback to an older backup and truncation are invisible to the chain alone but detected when the externally recorded head is supplied**; head-hash mismatch at the same sequence detected.

**Limitations to document and accept**
1. **Truncation / rollback** (deleting the newest entries or restoring an older backup) leaves a valid chain. Only an **externally stored head** detects it → after every backup (and daily), copy `head_seq`+`head_hash` to **write-once storage** (S3 Object Lock / Azure immutable blob / WORM log service / a ticket or e-mail to a security mailbox). Verify with `audit-verify --expected-head-seq … --expected-head-hash …` during restore and periodically.
2. **Single-process writer:** the chain lock is in-process. Run exactly one application process per database, or add a DB-level lock/sequence (e.g. PostgreSQL advisory lock) before scaling out.
3. The database triggers are SQLite-only and removable by anyone with file access (the HMAC chain still detects the resulting edits unless they also hold the key).
4. Legacy (pre-chain) entries are not tamper-evident.

## F. Repository hygiene

`evidence/captcha-automation-tool/` (untracked, 645 non-venv files + a venv) was inspected (645 files outside its venv): **617 were byte-identical to files in this repository, 28 differed (older snapshots of tracked code, its own `.git` metadata, and its database), and 0 existed only there.** Its `.git` was corrupt (`bad object HEAD`, no commits missing from this repository). It also contained the Phase 5 login page with the old hard-coded credentials and a database with password hashes (created with the old default passwords).
- Unique value preserved: the Phase 5 database **schema** was exported to `tests/fixtures/phase5_schema.sql` (no data/hashes) and a private copy of the snapshot was used for the real-data upgrade test outside the repository.
- The nested directory (including the venv, the old credentials and the database copy) was **deleted**. Nothing in tracked files referenced it except historical text in the 6A report. Evidence artifacts (screenshots, reports) all exist in the main `evidence/` tree.

## G. Final validation — see `PHASE_6B_FINAL_TEST_REPORT.md`.

## Remaining risks (after this review)

| # | Risk | Severity | Note |
| :-- | :--- | :---: | :--- |
| 1 | Audit head must be anchored externally; without it truncation/rollback is undetectable | Medium | Operational procedure above; no automation yet |
| 2 | Single-process audit writer / in-memory rate limiter / background jobs lost on restart | Medium | Fine for single-instance pilot; Redis + DB lock + job queue needed to scale |
| 3 | SQLite for production workloads; triggers are SQLite-specific | Medium | Postgres port needs equivalent protections |
| 4 | Access-token lifetime 60 min and JWT in `localStorage` (XSS-exposed); no CSP | Medium | HttpOnly cookie + CSP recommended; revocation limits the blast radius |
| 5 | `AUDIT_ALLOW_LEGACY_DERIVED_KEY` leaves legacy-derived verification for old rows | Low | Disable after old segments are archived/anchored |
| 6 | Review reviewer/history is API-only (not shown in UI) | Low | UI work |
| 7 | Remaining Phase 7 scope: OCR accuracy (20% exact-match measured), honest verification labelling, aggregate stats, cost/demo docs | — | Not started |
| 8 | Real-TLS handshake rejection and real DNS-rebinding timing not exercised against live infrastructure | Low | Unit/integration-simulated only |
| 9 | Older E2E scripts (`run_acceptance_tests.py`, `verify_frontend_e2e.py`, evidence capture) not re-run | Low | Pre-date the security changes; superseded by `e2e_phase6b_browser.py` for security flows |

## Approval requested

Phase 7 (assignment compliance & OCR quality) is **not started**. Please confirm that you want to proceed.
