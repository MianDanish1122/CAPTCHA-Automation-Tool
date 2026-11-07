from pathlib import Path
import pytest
from app.services.browser_scanner import inspect_local_demo, detect_captcha_in_html

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.anyio
async def test_fixture_normal_contact_form():
    html = (FIXTURES_DIR / "normal_contact_form.html").read_text(encoding="utf-8")
    result = await inspect_local_demo(html)

    assert result["success"] is True
    assert result["status"] == "no_known_captcha_detected"
    assert result["detected_providers"] == []
    assert result["contact_form_found"] is True
    assert result["is_active_challenge"] is False
    assert result["human_review_required"] is False


@pytest.mark.anyio
async def test_fixture_google_recaptcha():
    html = (FIXTURES_DIR / "google_recaptcha.html").read_text(encoding="utf-8")
    result = await inspect_local_demo(html)

    assert result["success"] is True
    assert result["status"] == "captcha_detected"
    assert "google_recaptcha" in result["detected_providers"]
    assert result["is_active_challenge"] is True
    assert result["contact_form_found"] is True
    assert result["human_review_required"] is True


@pytest.mark.anyio
async def test_fixture_invisible_recaptcha():
    html = (FIXTURES_DIR / "invisible_recaptcha.html").read_text(encoding="utf-8")
    result = await inspect_local_demo(html)

    assert result["success"] is True
    assert result["status"] == "captcha_detected"
    assert "google_recaptcha" in result["detected_providers"]
    assert result["contact_form_found"] is True
    assert result["human_review_required"] is True


@pytest.mark.anyio
async def test_fixture_hcaptcha():
    html = (FIXTURES_DIR / "hcaptcha.html").read_text(encoding="utf-8")
    result = await inspect_local_demo(html)

    assert result["success"] is True
    assert result["status"] == "captcha_detected"
    assert "hcaptcha" in result["detected_providers"]
    assert result["is_active_challenge"] is True
    assert result["contact_form_found"] is True
    assert result["human_review_required"] is True


@pytest.mark.anyio
async def test_fixture_cloudflare_turnstile():
    html = (FIXTURES_DIR / "cloudflare_turnstile.html").read_text(encoding="utf-8")
    result = await inspect_local_demo(html)

    assert result["success"] is True
    assert result["status"] == "captcha_detected"
    assert "cloudflare_turnstile" in result["detected_providers"]
    assert result["is_active_challenge"] is True
    assert result["contact_form_found"] is True
    assert result["human_review_required"] is True


@pytest.mark.anyio
async def test_fixture_unknown_challenge():
    html = (FIXTURES_DIR / "unknown_challenge.html").read_text(encoding="utf-8")
    result = await inspect_local_demo(html)

    assert result["success"] is True
    assert result["status"] == "unsupported_challenge"
    assert result["human_review_required"] is True
