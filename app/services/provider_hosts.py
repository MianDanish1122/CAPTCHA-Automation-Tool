"""
Narrow, explicit policy for the CAPTCHA providers' widget resources.

Real contact pages load their CAPTCHA widget from the provider (not from the site's own domain), so a guard that
allows only the target domain can never observe a loaded widget. This module lists the ONLY third-party
hosts/paths that may be fetched as subresources of an inspection, and only with GET/HEAD:

    reCAPTCHA   www.google.com/recaptcha/*, www.recaptcha.net/recaptcha/*, www.gstatic.com/recaptcha/*
    hCaptcha    hcaptcha.com and *.hcaptcha.com
    Turnstile   challenges.cloudflare.com/turnstile/*  (and its /cdn-cgi/challenge-platform/ helper path)

Everything else still goes through the normal domain allow-list. These requests are still subject to scheme/port/
credential checks, the public-IP-only policy, DNS pinning and TLS verification: the policy only waives the
*domain allow-list* for these exact provider locations.
"""
from urllib.parse import urlparse

# (exact host or "*.suffix", required path prefix or "" for any path)
PROVIDER_RULES: list[tuple[str, str]] = [
    ("www.google.com", "/recaptcha/"),
    ("www.recaptcha.net", "/recaptcha/"),
    ("recaptcha.net", "/recaptcha/"),
    ("www.gstatic.com", "/recaptcha/"),
    ("hcaptcha.com", ""),
    ("*.hcaptcha.com", ""),
    ("challenges.cloudflare.com", "/turnstile/"),
    ("challenges.cloudflare.com", "/cdn-cgi/challenge-platform/"),
]

PROVIDER_OF_HOST = {
    "google.com": "google_recaptcha", "gstatic.com": "google_recaptcha", "recaptcha.net": "google_recaptcha",
    "hcaptcha.com": "hcaptcha", "cloudflare.com": "cloudflare_turnstile",
}

SAFE_METHODS = ("GET", "HEAD")


def is_provider_resource(url: str, method: str = "GET") -> bool:
    """True only for GET/HEAD requests to an exact provider host AND path prefix listed above."""
    if method.upper() not in SAFE_METHODS:
        return False
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    for rule_host, prefix in PROVIDER_RULES:
        if rule_host.startswith("*."):
            host_ok = host.endswith(rule_host[1:]) and host != rule_host[2:]
        else:
            host_ok = host == rule_host
        if host_ok and (not prefix or path.startswith(prefix)):
            return True
    return False


def provider_for_url(url: str):
    """Map a provider URL to a provider key (None if the URL is not a provider URL)."""
    host = (urlparse(url).hostname or "").lower()
    for suffix, key in PROVIDER_OF_HOST.items():
        if host == suffix or host.endswith("." + suffix):
            if suffix == "google.com" and "/recaptcha" not in url:
                return None
            if suffix == "gstatic.com" and "/recaptcha" not in url:
                return None
            if suffix == "cloudflare.com" and "/turnstile" not in url and "challenge-platform" not in url:
                return None
            return key
    return None
