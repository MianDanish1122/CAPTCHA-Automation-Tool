# Final Security Review (real-world QA stage)

Scope: changes made in this stage. The Phase 5–6B architecture (SSRF guard, allow-list, DNS pinning, TLS verification, RBAC, audit chain, rate limits) is unchanged and all of its tests still pass.

| Area | Change | Security consequence |
|---|---|---|
| Redirects | Apex ↔ `www.` counted as the same site (`same_site`) | Only that one pair. Subdomains, other domains, lookalikes (`x.com.evil.com`) and private IPs are still blocked (tests). |
| Allow-list | `host_matches_allowed` accepts the apex/www sibling of an allowed host | No broadening to unrelated hosts (tests incl. `evilbigfrog.com`). |
| Provider widgets | New narrow policy (`provider_hosts.py`): GET/HEAD, https, no credentials, exact host + path prefix, for reCAPTCHA / hCaptcha / Turnstile only | Waives **only** the domain allow-list. Public-IP rule, DNS pinning, TLS, redirect checks still apply; a provider host resolving to a private IP is blocked (test). Provider→non-provider redirects blocked. |
| No transmission | `read_only` aborts every non-GET request; `lock()` aborts everything; `set_offline`; in-page submit shield | Tested with a hostile page that fires fetch/XHR/beacon/image on every keystroke: 0 requests reached the server. Fail-closed if a layer cannot be established. |
| Form probe | Fills only visible text-like fields with fixed placeholder data | Never clicks, presses Enter, ticks boxes, selects options, fills hidden/honeypot fields or touches CAPTCHA response fields. No token is read. |
| robots / access | Checked before any page; disallow, 401/403/429, challenge, 5xx or error ⇒ stop | No workaround code path exists. |
| Politeness | ≥ `BATCH_MIN_HOST_INTERVAL_S` (5 s) between inspections of one external host | Loopback exempt. |
| CSV output | `csv_safe` prefixes `=`,`+`,`-`,`@`, tab, CR cells with `'` in the audit report and evaluation CSV | CWE-1236 closed; verified in a real browser download (`'=Evil()`). |
| Importer | Original row stored verbatim (cells capped at 2 KB); client-supplied normalised labels ignored (re-derived server-side); non-http(s) Contact Page ignored | No new injection path; fixture URLs still gated. |
| Evidence | Batch screenshots stored under `evidence/scans/<batch-uuid>/` | Served only by the existing authenticated, pattern-restricted evidence endpoint. API returns relative paths only (tested: no local absolute paths). |
| Schema | Migration `8a01realworldqa`, additive, idempotent; downgrade guarded by `ALEMBIC_ALLOW_DESTRUCTIVE_DOWNGRADE=1` | Tested against a pre-populated table. |
| Frontend | Downloads now use the bearer token via fetch+blob (plain links could not authenticate) | No token in URLs. |

## Not changed / still open
- The batch scanner's default browser user agent is Chrome-like while robots rules are matched against the crawler agent; the live-site script sends the honest agent. Align before production use.
- `localStorage` JWT without a CSP, single-process job state and SQLite remain as documented in `KNOWN_LIMITATIONS.md`.
- Third-party page URLs (including public keys such as a site's own maps key) can appear in saved blocked-request evidence; treat evidence files as sensitive.
