# Final Deployment Readiness Checklist

Nothing has been deployed, pushed or committed. Tick items before any deployment you approve.

## Code and tests
- [ ] Review the working-tree diff (baseline tag `baseline-before-real-world-qa` = commit `f5c7df8`).
- [ ] Backend `pytest tests` green (see FINAL_FUNCTIONAL_TEST_REPORT).
- [ ] Frontend `npm run build` green.
- [ ] Browser suites: Phase 7 (30), Phase 6B (32), demo rehearsal (19 steps), batch UI (16).

## Configuration (`.env`)
- [ ] `APP_ENV=production`, strong `JWT_SECRET_KEY` and `AUDIT_HMAC_KEY` set, no default credentials.
- [ ] `ENABLE_LIVE_SCAN=true` only with a deliberate `ALLOWED_DOMAINS` list (apex and `www.` are treated as one site).
- [ ] `ALLOW_DEV_LOOPBACK` and fixture URLs disabled.
- [ ] `BATCH_MIN_HOST_INTERVAL_S` ≥ 5; `BATCH_PROBE_FORMS` left `false` unless you want the synthetic fill during batch runs.
- [ ] Decide the user agent: the batch default is Chrome-like with no crawler token; `CRAWLER_USER_AGENT` is Chrome-like ending in `TechnologyBrainz-Crawler/2.0`. Consider a plainly self-identifying agent. robots.txt rules are matched against the `TechnologyBrainz-Crawler` token and the full string (most restrictive wins).

## Database
- [ ] Back up, then `alembic upgrade head` (head `8a01realworldqa`, additive, idempotent).
- [ ] Do not run downgrades without `ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1` and a backup.

## Operational
- [ ] Playwright Chromium installed on the host; `evidence/` writable and kept private.
- [ ] Reverse proxy / TLS in front; CSP considered (JWT in `localStorage`).
- [ ] Single-process limits accepted (jobs lost on restart; SQLite).

## Authorisation
- [ ] Written permission for every external host scanned; robots.txt honoured; contact for opt-out.
- [ ] No submission of third-party contact forms; no solving of third-party CAPTCHAs.

## Documentation / hand-off
- [ ] Demo video recorded from `docs/DEMO_VIDEO_SCRIPT.md` (updated section "Real-world QA addendum").
- [ ] Remaining risks (FINAL_REMAINING_RISKS) accepted.
