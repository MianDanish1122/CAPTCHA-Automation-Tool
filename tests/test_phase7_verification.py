"""
Phase 7 verification tests.

Three kinds of evidence, kept apart on purpose:
  * MOCK  - httpx.MockTransport stands in for the provider (deterministic; covers outages/garbage)
  * LIVE  - the REAL official provider endpoints with their published TEST secrets (skipped if offline)
  * SIM   - locally simulated scenarios (must never succeed, never call the provider)
"""
import json

import httpx
import pytest
from starlette.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import VerificationRecord
from app.services.token_verifier import PROVIDERS, SIMULATIONS, verify_token

PROVIDER_NAMES = list(PROVIDERS)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json_handler(payload, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)
    return handler


# ------------------------------------------------------------------ MOCK: provider behaviour
@pytest.mark.anyio
@pytest.mark.parametrize("provider", PROVIDER_NAMES)
async def test_mock_provider_success_is_only_success_when_provider_says_true(provider):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"success": True, "hostname": "example.test",
                                         "challenge_ts": "2026-01-01T00:00:00Z"})

    async with _client(handler) as c:
        r = await verify_token(provider, "tok-abc", http_client=c)
    assert r["success"] is True and r["provider_verified"] is True and r["provider_called"] is True
    assert r["verification_mode"] == "provider_test_keys"  # no secret supplied -> official test secret
    assert seen["url"] == PROVIDERS[provider]["url"]
    assert "secret=" in seen["body"] and "response=tok-abc" in seen["body"]
    assert r["hostname"] == "example.test"


@pytest.mark.anyio
async def test_mock_real_secret_is_labelled_provider_live_and_hostname_checked():
    async with _client(_json_handler({"success": True, "hostname": "other.example"})) as c:
        r = await verify_token("google_recaptcha", "tok", secret_key="my-real-secret-xyz",
                               expected_hostname="mysite.example", http_client=c)
    assert r["verification_mode"] == "provider_live"
    assert r["success"] is False and r["outcome"] == "rejected_hostname_mismatch"
    async with _client(_json_handler({"success": True, "hostname": "mysite.example"})) as c:
        ok = await verify_token("google_recaptcha", "tok", secret_key="my-real-secret-xyz",
                                expected_hostname="mysite.example", http_client=c)
    assert ok["success"] is True and ok["verification_mode"] == "provider_live"


@pytest.mark.anyio
@pytest.mark.parametrize("codes,outcome", [
    (["timeout-or-duplicate"], "rejected_timeout_or_duplicate"),
    (["invalid-input-response"], "rejected_invalid_token"),
    (["invalid-input-secret"], "rejected_invalid_token"),
    ([], "verification_failed"),
])
async def test_mock_provider_rejections_map_to_outcomes(codes, outcome):
    async with _client(_json_handler({"success": False, "error-codes": codes})) as c:
        r = await verify_token("cloudflare_turnstile", "tok", http_client=c)
    assert r["success"] is False and r["provider_verified"] is False
    assert r["outcome"] == outcome and r["error_codes"] == codes


@pytest.mark.anyio
@pytest.mark.parametrize("name,handler", [
    ("timeout", lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=req))),
    ("connect_error", lambda req: (_ for _ in ()).throw(httpx.ConnectError("down", request=req))),
    ("http_500", lambda req: httpx.Response(500, text="oops")),
    ("http_503", lambda req: httpx.Response(503, text="maintenance")),
])
async def test_provider_unavailable_never_yields_success(name, handler):
    """Regression: the old code returned success=True ('verified offline') when Google was unreachable."""
    async with _client(handler) as c:
        r = await verify_token("google_recaptcha", "VALID_TEST_RESPONSE", http_client=c)
    assert r["success"] is False and r["provider_verified"] is False
    assert r["outcome"] == "provider_unavailable"
    assert "verified_offline" not in json.dumps(r)


@pytest.mark.anyio
@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>not json</html>"),
    httpx.Response(200, json=["success", True]),
    httpx.Response(200, json={"ok": True}),
    httpx.Response(200, json={"success": "true"}),   # truthy string must NOT count as success
    httpx.Response(200, json={"success": 1}),
    httpx.Response(200, json=None),
])
async def test_malformed_provider_responses_are_rejected(response):
    async with _client(lambda req: response) as c:
        r = await verify_token("hcaptcha", "tok", http_client=c)
    assert r["success"] is False and r["outcome"] == "provider_invalid_response"


@pytest.mark.anyio
async def test_secret_never_appears_in_result():
    secret = "super-secret-key-12345"
    async with _client(_json_handler({"success": False, "error-codes": ["invalid-input-secret"]})) as c:
        r = await verify_token("google_recaptcha", "tok", secret_key=secret, http_client=c)
    assert secret not in json.dumps(r)


# ------------------------------------------------------------------ local validation + SIM
@pytest.mark.anyio
@pytest.mark.parametrize("token", ["", "   ", None])
async def test_missing_token_rejected_locally_without_provider_call(token):
    r = await verify_token("google_recaptcha", token)
    assert r["verification_mode"] == "local_validation" and r["provider_called"] is False
    assert r["outcome"] == "rejected_missing_token" and r["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("token", ["has space", "tab\there", "x" * 5000, "uniécode", "ctrl\x00char"])
async def test_malformed_token_rejected_locally(token):
    r = await verify_token("google_recaptcha", token)
    assert r["verification_mode"] == "local_validation" and r["provider_called"] is False
    assert r["outcome"] == "rejected_malformed_token"


@pytest.mark.anyio
@pytest.mark.parametrize("scenario", sorted(SIMULATIONS))
async def test_simulations_never_call_provider_and_never_succeed(scenario):
    def must_not_be_called(request):
        raise AssertionError("simulation reached the network")

    async with _client(must_not_be_called) as c:
        r = await verify_token("google_recaptcha", "any-token", simulate_status=scenario, http_client=c)
    assert r["verification_mode"] == "simulated" and r["provider_called"] is False
    assert r["success"] is False and r["provider_verified"] is False
    assert r["scenario"] == scenario


@pytest.mark.anyio
async def test_unknown_provider_and_scenario_rejected():
    with pytest.raises(ValueError):
        await verify_token("not_a_provider", "tok")
    with pytest.raises(ValueError):
        await verify_token("google_recaptcha", "tok", simulate_status="valid")  # no simulated success exists


# ------------------------------------------------------------------ LIVE: real provider endpoints, TEST secrets
async def _live(provider, token, secret=None):
    try:
        return await verify_token(provider, token, secret_key=secret)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"offline: {exc}")


def _skip_if_unreachable(r):
    if r["outcome"] == "provider_unavailable":
        pytest.skip("provider endpoint unreachable from this machine")


@pytest.mark.anyio
@pytest.mark.parametrize("provider", PROVIDER_NAMES)
async def test_live_official_test_keys_pass(provider):
    r = await _live(provider, PROVIDERS[provider]["dummy_token"])
    _skip_if_unreachable(r)
    assert r["provider_called"] is True and r["verification_mode"] == "provider_test_keys"
    assert r["success"] is True and r["outcome"] == "verified" and r["http_status"] == 200


@pytest.mark.anyio
async def test_live_turnstile_always_fails_test_secret():
    r = await _live("cloudflare_turnstile", "XXXX.DUMMY.TOKEN.XXXX", "2x0000000000000000000000000000000AA")
    _skip_if_unreachable(r)
    assert r["success"] is False and r["provider_called"] is True
    assert r["error_codes"] == ["invalid-input-response"]


@pytest.mark.anyio
async def test_live_turnstile_token_already_spent_is_a_real_provider_response():
    """Genuine provider-side 'reused/expired' behaviour (not a local simulation)."""
    r = await _live("cloudflare_turnstile", "XXXX.DUMMY.TOKEN.XXXX", "3x0000000000000000000000000000000AA")
    _skip_if_unreachable(r)
    assert r["verification_mode"] == "provider_test_keys" and r["provider_called"] is True
    assert r["outcome"] == "rejected_timeout_or_duplicate" and r["error_codes"] == ["timeout-or-duplicate"]


@pytest.mark.anyio
async def test_live_invalid_secret_rejected_by_provider():
    r = await _live("google_recaptcha", "some-token", "definitely-not-a-real-secret")
    _skip_if_unreachable(r)
    assert r["verification_mode"] == "provider_live" and r["provider_called"] is True
    assert r["success"] is False and r["error_codes"]


# ------------------------------------------------------------------ API: persistence + honesty
@pytest.fixture
def api():
    return TestClient(app)


def _records_since(before_ids):
    db = SessionLocal()
    try:
        return [r for r in db.query(VerificationRecord).all() if r.id not in before_ids]
    finally:
        db.close()


def _ids():
    db = SessionLocal()
    try:
        return {r.id for r in db.query(VerificationRecord.id).all()}
    finally:
        db.close()


def test_api_simulated_attempt_is_labelled_persisted_and_never_succeeds(api):
    before = _ids()
    res = api.post("/api/captcha/verify-token", json={"provider": "google_recaptcha", "token": "t",
                                                      "simulate_status": "expired"})
    body = res.json()
    assert res.status_code == 200 and body["verification_mode"] == "simulated" and body["success"] is False
    new = _records_since(before)
    assert len(new) == 1 and new[0].verification_mode == "simulated" and new[0].provider_called is False
    assert "t" not in (new[0].error_codes or "").split(",")  # token never stored anywhere


def test_api_missing_token_is_local_validation(api):
    body = api.post("/api/captcha/verify-token", json={"provider": "hcaptcha", "token": ""}).json()
    assert body["verification_mode"] == "local_validation" and body["provider_called"] is False


def test_api_rejects_unknown_provider_and_old_simulate_valid(api):
    assert api.post("/api/captcha/verify-token", json={"provider": "nope", "token": "x"}).status_code == 422
    assert api.post("/api/captcha/verify-token",
                    json={"provider": "google_recaptcha", "token": "x", "simulate_status": "valid"}).status_code == 422


def test_api_frontend_cannot_assert_success(api):
    """Extra client-supplied fields claiming success are ignored; success comes only from the provider."""
    res = api.post("/api/captcha/verify-token", json={
        "provider": "google_recaptcha", "token": "t", "simulate_status": "invalid",
        "success": True, "provider_verified": True, "verified": True})
    assert res.json()["success"] is False


def test_api_provider_listing_and_records(api):
    prov = api.get("/api/captcha/verification/providers").json()
    assert {p["provider"] for p in prov["providers"]} == set(PROVIDER_NAMES)
    assert set(prov["simulation_scenarios"]) == set(SIMULATIONS)
    rec = api.get("/api/captcha/verification/records?limit=5").json()
    assert rec["success"] is True and isinstance(rec["records"], list)


def test_api_requires_authentication():
    c = TestClient(app)
    c._unauthenticated = True
    assert c.post("/api/captcha/verify-token", json={"provider": "google_recaptcha", "token": "x"}).status_code == 401
    assert c.get("/api/captcha/verification/records").status_code == 401


def test_official_test_page_flow_records_provider_test_keys(api):
    """evaluate-handling with a page using the published reCAPTCHA TEST key -> real provider test-key call."""
    html = ("<script src='https://www.google.com/recaptcha/api.js'></script>"
            "<div class='g-recaptcha' data-sitekey='6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'></div>")
    before = _ids()
    body = api.post("/api/captcha/evaluate-handling", json={"html": html, "is_official_test": True}).json()
    new = _records_since(before)
    if new and new[0].outcome == "provider_unavailable":
        pytest.skip("provider unreachable")
    tv = body["token_verification"]
    assert body["strategy_applied"] == "official_token_verify"
    assert tv["verification_mode"] == "provider_test_keys" and tv["token_source"] == "dummy_test_token"
    assert body["success"] is True and tv["provider_verified"] is True
    assert "test" in body["message"].lower()
