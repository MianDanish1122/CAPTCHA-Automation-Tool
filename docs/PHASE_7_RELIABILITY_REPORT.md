# Phase 7 — Reliability & Error-Handling Report

Principle: every failure is **reported** (structured result or a safe HTTP error); none may crash a worker, leak internals (paths, SQL, stack traces), hang indefinitely, or leave a scan in a non-terminal state. Existing SSRF, audit, rate-limit and session protections are unchanged (their tests still run).

## Error-handling matrix

| # | Failure mode | Behaviour (after Phase 7) | Defect found while testing → fix | Test evidence |
| :-- | :--- | :--- | :--- | :--- |
| R1a | Browser cannot launch (single-page scan) | `success:false`, `detection_method: browser_unavailable`, error shows the exception **type only** (no path leak) | `get_shared_browser()` was awaited outside any `try`: the exception escaped | `test_browser_launch_failure_reported_by_single_page_scan` |
| R1b | Browser cannot launch (demo inspection) | `status: inspection_failed` | same | `test_browser_launch_failure_reported_by_demo_inspection` |
| R1c | Browser cannot launch (crawl) | scan marked `failed` with `completed_at`, message "Browser could not be started"; never left in `crawling` | scan stayed `crawling` forever | `test_browser_launch_failure_marks_crawl_failed_not_stuck` |
| R1d | …through the API | HTTP 200 with `success:false` (not 500) | — | `test_api_returns_failure_not_500_when_browser_cannot_start` |
| R2 | Navigation timeout | structured failure `Navigation error…` within the configured timeout (0.8 s test, slow server 4 s) | — | `test_navigation_timeout_is_reported` |
| R3a | Unreachable host (connection refused) | `scan_status: failed` | — | `test_unreachable_host_is_reported` |
| R3b | Crawler on unreachable host | terminal status `completed`/`failed`, never `crawling` | — | `test_crawler_on_unreachable_host_completes_with_a_terminal_status` |
| R4 | Redirect / network-policy violations (private, link-local/metadata, CGNAT, non-HTTP scheme, non-approved port, cross-domain or private redirect, private subresource, DNS rebinding) | rejected before network use or aborted per request; blocked requests listed in `network_guard` | — | Phase 6A suite (139 tests) + `test_policy_violations_rejected_before_any_network_use` (5) |
| R5a | Unsupported / unknown challenge (interstitials) | classified `unknown_challenge` → `manual_investigation` human-review case; **not solved** | — | `test_unsupported_challenges_are_routed_to_human_review_not_solved` |
| R5b | Unknown widget markup with no known provider | `no_captcha` (no guessing) | — | `test_unknown_markup_without_provider_is_no_captcha_not_a_guess` |
| R6a | OCR engine receives garbage / non-image bytes | every engine returns `failed:true`, empty prediction, error text; never raises | — | `test_every_engine_reports_instead_of_raising_on_garbage_input` |
| R6b | OCR model file missing | `failed`, "glyph model file not found"; hybrid falls back | — | `test_custom_engine_reports_missing_model`, `test_hybrid_falls_back_to_tesseract_when_custom_unavailable` |
| R6c | Tesseract binary missing | `failed` with message; no exception | — | `test_tesseract_failure_is_reported_not_raised` |
| R6d | Invalid/oversized/bomb image upload to the API | 400 / 413 before any decoding | (Phase 6B) | `test_decompression_bomb_dimensions_rejected`, `test_non_image_payload_rejected`, … |
| R7a | Provider timeout / connect error / 5xx | `provider_unavailable`, **never success** (the old offline fake-success was removed) | the old fallback returned `success:true` when Google was unreachable | `test_provider_unavailable_never_yields_success` (4) |
| R7b | Provider returns garbage / wrong types | `provider_invalid_response` (6 shapes incl. `"true"`, `1`) | — | `test_malformed_provider_responses_are_rejected` |
| R7c | Provider outage during an app workflow | workflow `verification_failed`, recorded as `provider_unavailable` | — | `test_official_test_page_flow…` (skips when offline) |
| R8a | Job concurrency / per-user limits | HTTP 429 + `Retry-After`; slots released even if cancelled before start | slot leak (6B) | `test_job_manager_*`, `test_inspect_url_returns_429_…` |
| R8b | Job cancellation (shutdown) during a crawl | scan becomes `failed` ("Crawl cancelled before completion"), task cancelled, slot freed | cancelled crawl left the scan in `crawling` (cancel could arrive before the inner `try`) → wrapper around the whole crawl | `test_cancelled_crawl_does_not_leave_scan_in_crawling_state` |
| R9a | Database failure on a request | HTTP 503 + `Retry-After`; body has no SQL, path or lock message | no handler existed | `test_database_failure_returns_503_without_leaking_internals` |
| R9b | Any unhandled exception | HTTP 500 `{"detail":"Internal server error."}`; details only in the server log | no handler existed | `test_unhandled_exception_returns_generic_500` |
| R10a | Missing / garbage / wrong-scheme / empty bearer token | 401 on every protected endpoint probed (4 endpoints × 4 header variants) | — | `test_protected_endpoints_reject_bad_credentials` |
| R10b | Operator calls admin endpoint | 403 | — | `test_operator_cannot_reach_admin_endpoints` + Phase 5/6 suites |
| R10c | Expired / revoked / wrong-version / `alg:none` / no-`exp` tokens | 401 | (Phase 6B) | `test_phase6b_final.py` JWT tests |
| R11 | Rate limiting, oversized bodies, invalid base64 | 429 / 413 / 400 | (Phase 6B) | `test_phase6b_security.py` |
| R12 | Stats/report on an empty database | zeros and `null` percentages, `has_data:false`, no placeholders | — | `test_stats_with_empty_database_yields_zeros_not_mock_values` |

## Not covered / known gaps

- **Process crash recovery:** background crawls and batches run inside the API process; a crash or restart loses in-flight work (a scan can remain `crawling` after a hard kill, since no handler runs). A job queue and a start-up reaper are not implemented.
- **Real network faults** (packet loss, TLS failures against a real HTTPS server) are simulated with local servers and mocks, not injected on a real network.
- **Disk-full / filesystem errors** for screenshot and report writing are not tested.
- **Chromium crash mid-navigation** is handled as a navigation error; a hung browser *process* is not independently watchdogged.
- **Multi-process deployments** (audit chain lock, in-memory rate limiter, job registry are per-process) are unsupported until a shared store/lock is added.
