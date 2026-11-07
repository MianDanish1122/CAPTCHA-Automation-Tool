import pytest
from app.services.security_guard import SecurityGuard


def test_ip_allowed_public_ips():
    allowed, _ = SecurityGuard.is_ip_allowed("8.8.8.8")
    assert allowed is True

    allowed, _ = SecurityGuard.is_ip_allowed("1.1.1.1")
    assert allowed is True


def test_ip_rejected_private_ips():
    # RFC 1918 10.0.0.0/8
    allowed, reason = SecurityGuard.is_ip_allowed("10.0.0.1")
    assert allowed is False
    assert "Private" in reason

    # RFC 1918 192.168.0.0/16
    allowed, reason = SecurityGuard.is_ip_allowed("192.168.1.1")
    assert allowed is False
    assert "Private" in reason

    # RFC 1918 172.16.0.0/12
    allowed, reason = SecurityGuard.is_ip_allowed("172.20.0.5")
    assert allowed is False
    assert "Private" in reason


def test_ip_rejected_loopback():
    allowed, reason = SecurityGuard.is_ip_allowed("127.0.0.1")
    assert allowed is False
    assert "Loopback" in reason


def test_ip_rejected_cloud_metadata():
    allowed, reason = SecurityGuard.is_ip_allowed("169.254.169.254")
    assert allowed is False
    assert "metadata" in reason.lower()


def test_validate_target_url_invalid_scheme():
    allowed, reason = SecurityGuard.validate_target_url("file:///etc/passwd", enforce_live_scan=False)
    assert allowed is False
    assert "scheme" in reason.lower()

    allowed, reason = SecurityGuard.validate_target_url("javascript:alert(1)", enforce_live_scan=False)
    assert allowed is False


def test_validate_target_url_credentials():
    allowed, reason = SecurityGuard.validate_target_url("https://admin:pass@example.com", enforce_live_scan=False)
    assert allowed is False
    assert "credentials" in reason.lower()


def test_validate_target_url_live_scan_disabled():
    # With enforce_live_scan=True and settings.ENABLE_LIVE_SCAN=False (default)
    allowed, reason = SecurityGuard.validate_target_url("https://example.com", enforce_live_scan=True)
    assert allowed is False
    assert "disabled" in reason.lower()
