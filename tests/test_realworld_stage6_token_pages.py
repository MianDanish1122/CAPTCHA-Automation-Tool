"""Stage 6: the official-test-key acquisition pages must keep the three providers isolated.

Root cause of the old hCaptcha failure: all three scripts lived on ONE page; hCaptcha's api.js has a reCAPTCHA
compatibility layer (recaptchacompat=on by default), so `hcaptcha.render` produced a Google reCAPTCHA iframe and the
hCaptcha checkbox never existed. These offline tests pin that fix; the live run is scripts/token_acquisition_demo.py.
"""
import importlib

import pytest

demo = importlib.import_module("scripts.token_acquisition_demo")


@pytest.mark.parametrize("provider,own,others", [
    ("google_recaptcha", "google.com/recaptcha/api.js", ["hcaptcha.com", "challenges.cloudflare.com"]),
    ("hcaptcha", "js.hcaptcha.com/1/api.js", ["google.com/recaptcha", "challenges.cloudflare.com"]),
    ("cloudflare_turnstile", "challenges.cloudflare.com/turnstile", ["google.com/recaptcha", "hcaptcha.com"]),
])
def test_each_provider_page_loads_only_its_own_script(provider, own, others):
    html = demo.page_for(provider)
    assert own in html
    for other in others:
        assert other not in html


def test_hcaptcha_page_disables_the_recaptcha_compat_layer():
    assert "recaptchacompat=off" in demo.page_for("hcaptcha")


def test_only_published_test_keys_are_used():
    assert demo.TEST_SITEKEYS["google_recaptcha"] == "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
    assert demo.TEST_SITEKEYS["hcaptcha"] == "10000000-ffff-ffff-ffff-000000000001"
    assert demo.TEST_SITEKEYS["cloudflare_turnstile"] == "1x00000000000000000000AA"
