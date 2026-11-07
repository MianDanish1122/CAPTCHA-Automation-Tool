"""
Server-side CAPTCHA token verification against the providers' OFFICIAL siteverify endpoints.

Every result states HOW it was produced, because the three situations below must never be confused:

  provider_live        the real provider verified a token with an operator-supplied (real) secret key
  provider_test_keys   the real provider endpoint was called with the provider's published TEST secret.
                       The provider genuinely answered, but test keys are designed to accept (or reject /
                       report "already spent") ANY token: this demonstrates the integration, it is not
                       proof that a human solved a production challenge.
  simulated            NO provider call was made. Failure scenarios (invalid / expired / reused /
                       provider down / garbled response) generated locally so error handling can be
                       demonstrated and tested. A simulation can NEVER return success=True.
  local_validation     rejected locally before any provider call (missing / malformed token).

`success` is True only when `provider_verified` is True, i.e. the provider's own JSON said so.
A client assertion, a flag, or an unreachable provider can never produce success. There is no
"offline success" fallback: if the provider cannot be reached the outcome is `provider_unavailable`.
"""
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import settings

PROVIDERS: dict[str, dict[str, Any]] = {
    "google_recaptcha": {
        "url": "https://www.google.com/recaptcha/api/siteverify",
        "test_secrets": {"6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"},
        "dummy_token": "VALID_TEST_RESPONSE",
        "label": "Google reCAPTCHA",
    },
    "hcaptcha": {
        "url": "https://api.hcaptcha.com/siteverify",
        "test_secrets": {"0x0000000000000000000000000000000000000000"},
        "dummy_token": "10000000-aaaa-bbbb-cccc-000000000001",
        "label": "hCaptcha",
    },
    "cloudflare_turnstile": {
        "url": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        # Cloudflare's published dummy secrets: 1x = always passes, 2x = always fails,
        # 3x = "token already spent" (genuine provider-side timeout-or-duplicate).
        "test_secrets": {
            "1x0000000000000000000000000000000AA",
            "2x0000000000000000000000000000000AA",
            "3x0000000000000000000000000000000AA",
        },
        "dummy_token": "XXXX.DUMMY.TOKEN.XXXX",
        "label": "Cloudflare Turnstile",
    },
}

SIMULATIONS = {
    "invalid": ("rejected_invalid_token", ["invalid-input-response"], "Simulated: provider rejects the token as invalid."),
    "expired": ("rejected_timeout_or_duplicate", ["timeout-or-duplicate"], "Simulated: token expired."),
    "reused": ("rejected_timeout_or_duplicate", ["timeout-or-duplicate"], "Simulated: token already consumed."),
    "provider_down": ("provider_unavailable", ["network-verification-error"], "Simulated: provider unreachable."),
    "provider_malformed": ("provider_invalid_response", ["provider-invalid-response"], "Simulated: provider returned a malformed response."),
}
# Legacy magic tokens used by earlier phases/tests are treated as SIMULATIONS (and labelled as such)
_MAGIC = {"MOCK_INVALID_TOKEN": "invalid", "MOCK_EXPIRED_OR_REUSED_TOKEN": "reused"}

_MAX_TOKEN = 4096
_TOKEN_OK = re.compile(r"^[\x21-\x7e]+$")  # printable ASCII, no whitespace/control characters

# legacy status vocabulary kept for API/test compatibility
_STATUS = {
    "verified": "verified",
    "rejected_missing_token": "rejected_missing_token",
    "rejected_malformed_token": "rejected_malformed_token",
    "rejected_invalid_token": "rejected_invalid_token",
    "rejected_timeout_or_duplicate": "rejected_timeout_or_duplicate",
    "rejected_hostname_mismatch": "rejected_hostname_mismatch",
    "provider_unavailable": "error",
    "provider_invalid_response": "error",
    "verification_failed": "verification_failed",
}


def _result(provider: str, mode: str, outcome: str, started: float, *, provider_called: bool = False,
            provider_verified: bool = False, error_codes: Optional[list] = None, message: str = "",
            http_status: Optional[int] = None, hostname: Optional[str] = None, challenge_ts: Optional[str] = None,
            scenario: Optional[str] = None, token_source: str = "client") -> dict[str, Any]:
    return {
        "success": bool(provider_verified),
        "provider": provider,
        "verification_mode": mode,
        "outcome": outcome,
        "verification_status": _STATUS.get(outcome, outcome),
        "provider_called": provider_called,
        "provider_verified": bool(provider_verified),
        "scenario": scenario,
        "token_source": token_source,
        "http_status": http_status,
        "error_codes": error_codes or [],
        "hostname": hostname,
        "challenge_ts": challenge_ts,
        "message": message,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "evidence_note": {
            "provider_live": "Verified by the provider with an operator-supplied secret key.",
            "provider_test_keys": "Provider endpoint called with a published TEST secret: demonstrates the "
                                  "integration only; test keys do not prove a real challenge was solved.",
            "simulated": "No provider call was made; locally simulated failure scenario.",
            "local_validation": "Rejected locally before contacting the provider.",
        }[mode],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def verify_token(
    provider: str,
    response_token: Optional[str],
    secret_key: Optional[str] = None,
    remote_ip: Optional[str] = None,
    simulate_status: Optional[str] = None,
    expected_hostname: Optional[str] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    token_source: str = "client",
) -> dict[str, Any]:
    started = time.perf_counter()
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise ValueError(f"unsupported provider {provider!r}")

    token = (response_token or "").strip()

    def R(*args, **kwargs):
        return _result(*args, token_source=token_source, **kwargs)

    # 1) local validation (never reaches the provider)
    if simulate_status is None and not token:
        return R(provider, "local_validation", "rejected_missing_token", started,
                       error_codes=["missing-input-response"], message="Token was not provided in request.")
    if token and (len(token) > _MAX_TOKEN or not _TOKEN_OK.match(token)):
        return R(provider, "local_validation", "rejected_malformed_token", started,
                       error_codes=["invalid-input-response"],
                       message="Token is malformed (length or characters out of range).")

    # 2) simulations (explicit request, or legacy magic token) -- no provider call, never success
    scenario = simulate_status or _MAGIC.get(token)
    if scenario:
        if scenario not in SIMULATIONS:
            raise ValueError(f"unknown simulation scenario {scenario!r}")
        outcome, codes, msg = SIMULATIONS[scenario]
        return R(provider, "simulated", outcome, started, error_codes=codes, message=msg, scenario=scenario)

    # 3) real call to the provider's official siteverify endpoint
    secret = secret_key or sorted(cfg["test_secrets"])[0]
    using_test_secret = secret in cfg["test_secrets"]
    mode = "provider_test_keys" if using_test_secret else "provider_live"
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=settings.VERIFY_TIMEOUT_SECONDS)
    try:
        resp = await client.post(cfg["url"], data=payload)
    except httpx.TimeoutException:
        return R(provider, mode, "provider_unavailable", started, provider_called=True,
                       error_codes=["network-verification-error"], message="Provider timed out.")
    except httpx.HTTPError as exc:
        return R(provider, mode, "provider_unavailable", started, provider_called=True,
                       error_codes=["network-verification-error"],
                       message=f"Provider unreachable ({type(exc).__name__}).")
    finally:
        if owns_client:
            await client.aclose()

    if resp.status_code >= 500:
        return R(provider, mode, "provider_unavailable", started, provider_called=True,
                       http_status=resp.status_code, error_codes=["provider-server-error"],
                       message=f"Provider returned HTTP {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("success"), bool):
        return R(provider, mode, "provider_invalid_response", started, provider_called=True,
                       http_status=resp.status_code, error_codes=["provider-invalid-response"],
                       message="Provider response was not valid verification JSON.")

    codes = [str(c) for c in (data.get("error-codes") or []) if isinstance(c, (str, int))]
    hostname = data.get("hostname") if isinstance(data.get("hostname"), str) else None
    ts = data.get("challenge_ts") if isinstance(data.get("challenge_ts"), str) else None

    if data["success"] is True:
        if expected_hostname and mode == "provider_live" and hostname != expected_hostname:
            return R(provider, mode, "rejected_hostname_mismatch", started, provider_called=True,
                           http_status=resp.status_code, hostname=hostname, challenge_ts=ts,
                           error_codes=["hostname-mismatch"],
                           message="Provider verified the token for a different hostname.")
        return R(provider, mode, "verified", started, provider_called=True, provider_verified=True,
                       http_status=resp.status_code, hostname=hostname, challenge_ts=ts,
                       message="Provider confirmed the token.")

    outcome = "rejected_timeout_or_duplicate" if "timeout-or-duplicate" in codes else (
        "rejected_invalid_token" if codes else "verification_failed")
    return R(provider, mode, outcome, started, provider_called=True, http_status=resp.status_code,
                   hostname=hostname, challenge_ts=ts, error_codes=codes,
                   message="Provider rejected the token.")


async def verify_recaptcha_token(
    response_token: Optional[str],
    secret_key: Optional[str] = None,
    remote_ip: Optional[str] = None,
    simulate_status: Optional[str] = None,
) -> dict[str, Any]:
    """Backward-compatible reCAPTCHA entry point (Phase 3-6 callers)."""
    return await verify_token("google_recaptcha", response_token, secret_key, remote_ip, simulate_status)
