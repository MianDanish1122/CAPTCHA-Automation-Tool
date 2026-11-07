# Phase 7 — Verification Matrix (Token Handling)

## Vocabulary — what each "implementation type" means

| Type | Meaning | Can it prove a production challenge was solved? |
| :--- | :--- | :--- |
| **PROVIDER-LIVE** | The real provider endpoint verified a token using an operator-supplied *real* secret | Yes (needs the operator's own site keys; **not exercised end-to-end here** — no real keys were available) |
| **PROVIDER-TESTKEY** | The real provider endpoint answered, called with the provider's *published test secret*. Test secrets are designed to accept / reject / report "already spent" for any token | **No** — demonstrates the integration against the provider's official test infrastructure |
| **MOCK** | Test double (`httpx.MockTransport`) imitating provider responses in automated tests | No — tests error handling deterministically |
| **SIMULATED** | Application feature that fabricates a *failure* scenario locally; never calls the provider and **can never return success** | No |
| **LOCAL** | Rejected by the server before any provider call | n/a |

Implementation: `app/services/token_verifier.py`. Every API/UI result carries `verification_mode`, `provider_called`, `provider_verified`, `token_source`, `http_status`, `error_codes`; `success` is true **only** when the provider's own JSON said `success: true` (strict boolean). A client flag or an unreachable provider can never produce success. The earlier "offline fallback" that returned `success: true` when Google was unreachable was **removed**. Tokens are never stored or logged; secrets are never returned.

## Matrix

"Actual" = observed in the run recorded under *Evidence*. LIVE rows were executed against the real provider endpoints on 2026-11-07 from this machine.

| # | Scenario | Type | Expected | Actual | Evidence |
| :-- | :--- | :--- | :--- | :--- | :--- |
| V1 | reCAPTCHA, official test secret, any token | PROVIDER-TESTKEY | provider `success:true`, outcome `verified`, hostname `testkey.google.com` | verified, HTTP 200, `provider_verified=true` | `test_live_official_test_keys_pass[google_recaptcha]`; E2E check "official test keys: real provider called and confirmed" |
| V2 | hCaptcha, official test secret `0x00…00`, test response | PROVIDER-TESTKEY | verified | verified, HTTP 200 | `test_live_official_test_keys_pass[hcaptcha]` |
| V3 | Turnstile secret `1x…AA` (always passes) | PROVIDER-TESTKEY | verified | verified, HTTP 200 | `test_live_official_test_keys_pass[cloudflare_turnstile]` |
| V4 | Turnstile secret `2x…AA` (always fails) | PROVIDER-TESTKEY | rejected, `invalid-input-response` | `success:false`, `["invalid-input-response"]` | `test_live_turnstile_always_fails_test_secret` |
| V5 | Turnstile secret `3x…AA` (token already spent) | PROVIDER-TESTKEY | **genuine provider** `timeout-or-duplicate` | outcome `rejected_timeout_or_duplicate`, `["timeout-or-duplicate"]` | `test_live_turnstile_token_already_spent_is_a_real_provider_response`; UI screenshot `evidence/phase7/e2e/09_verification_turnstile_spent.png` |
| V6 | Invalid/unknown secret + token | PROVIDER-LIVE (real endpoint, bogus secret) | provider rejects | `success:false`, `invalid-input-response`, mode `provider_live` | `test_live_invalid_secret_rejected_by_provider` |
| V7 | Token **acquired from the official test widget** on an owned page, then verified server-side | PROVIDER-TESTKEY | token issued by widget; provider confirms | **reCAPTCHA**: 1 764-char token → verified (`hostname testkey.google.com`). **Turnstile**: token → verified (`hostname example.com`). **hCaptcha**: widget checkbox could **not** be automated in headless mode (selector timeout); its test-key verification is covered by V2 | `python -m scripts.token_acquisition_demo` → `evidence/phase7/verification/token_acquisition.json` (tokens not stored) |
| V8 | Page using the published reCAPTCHA test key + `is_official_test` | PROVIDER-TESTKEY via the app workflow | server validates the key is a published test key, then calls provider with the documented dummy token (labelled `token_source: dummy_test_token`) | verified, mode `provider_test_keys` | `test_official_test_page_flow_records_provider_test_keys` |
| V9 | Same page but a production-style site key + `is_official_test` | LOCAL policy | flag refused; routed to human review (never "verified") | refused, `queue_for_human_review` | Phase 6B `test_api_official_test_flag_cannot_bypass_review_for_real_key` |
| V10 | Missing token (`""`, `"   "`, null) | LOCAL | rejected, **no provider call** | `rejected_missing_token`, `provider_called=false` | `test_missing_token_rejected_locally_without_provider_call`; E2E "missing token rejected by local validation" |
| V11 | Malformed token (whitespace, control chars, non-ASCII, > 4 096 chars) | LOCAL | rejected, no provider call | `rejected_malformed_token` (5 cases) | `test_malformed_token_rejected_locally` |
| V12 | Invalid / expired / reused / provider-down / provider-malformed | **SIMULATED** | labelled simulated, no provider call, never success | 5/5: `verification_mode=simulated`, `provider_called=false`, `success=false`; the transport asserts it is never reached | `test_simulations_never_call_provider_and_never_succeed`; UI screenshot `08_verification_simulated.png` |
| V13 | Simulation scenario `valid` | LOCAL policy | does not exist (no simulated success) | HTTP 422 / `ValueError` | `test_api_rejects_unknown_provider_and_old_simulate_valid` |
| V14 | Provider timeout | MOCK | `provider_unavailable`, `success=false` | as expected | `test_provider_unavailable_never_yields_success[timeout]` |
| V15 | Provider connection error / HTTP 500 / HTTP 503 | MOCK | `provider_unavailable`, no success, no "verified offline" | as expected (4 cases) | same test, regression for the old fake-success fallback |
| V16 | Provider returns HTML, JSON array, missing `success`, `"true"` (string), `1`, `null` | MOCK | `provider_invalid_response`, never success | 6/6 | `test_malformed_provider_responses_are_rejected` |
| V17 | Provider rejection codes `timeout-or-duplicate`, `invalid-input-response`, `invalid-input-secret`, none | MOCK | mapped to distinct outcomes | 4/4 | `test_mock_provider_rejections_map_to_outcomes` |
| V18 | Real secret → success for a different hostname | MOCK of a PROVIDER-LIVE response | `rejected_hostname_mismatch`; matching hostname accepted | both as expected | `test_mock_real_secret_is_labelled_provider_live_and_hostname_checked` |
| V19 | Secret never echoed; token never persisted | all | absent from result and from `verification_records` | verified | `test_secret_never_appears_in_result`; E2E "no token is stored in verification records" |
| V20 | Client asserts success (`success`, `verified`, `provider_verified` in the request body) | LOCAL policy | ignored | result still `success=false` | `test_api_frontend_cannot_assert_success` |
| V21 | Unauthenticated verification request | auth | 401 | 401 | `test_api_requires_authentication` |

## Persistence and reporting

Each attempt is stored in `verification_records` (provider, mode, scenario, outcome, success, provider_called, provider_verified, HTTP status, error codes, duration; **no token, no secret**) and aggregated by mode and outcome in the Evaluation dashboard (`/evaluation`) and the downloadable report, with *simulated* and *provider-confirmed* counts shown separately.

## Limits of this evidence

- No production site keys/secrets were available, so the PROVIDER-LIVE success path (real token from a real user on a real site) is verified only by mock and by the live "invalid secret" rejection.
- Published test keys can change; the live tests skip (not fail) if a provider is unreachable.
- hCaptcha widget-driven token acquisition was not achieved in the headless run (see V7).
- Nothing here bypasses or defeats any production CAPTCHA; production challenges are detected and routed to human review.
