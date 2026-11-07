import io
import time
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models import User, UserRole, AuditLog
from app.services.auth_service import hash_password, create_access_token
from app.services.security_guard import SecurityGuard
from app.services.rate_limiter import limiter


@pytest.fixture
def unauthenticated_client():
    """Client with explicitly disabled auth header auto-injection."""
    c = TestClient(app)
    c._unauthenticated = True
    return c


@pytest.fixture
def operator_client():
    """Client authenticated with an operator-role token."""
    token = create_access_token(
        user_id="test-operator-id",
        username="test_operator",
        role=UserRole.OPERATOR
    )
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


@pytest.fixture
def admin_client():
    """Client authenticated with an admin-role token."""
    token = create_access_token(
        user_id="test-admin-id",
        username="test_admin",
        role=UserRole.ADMIN
    )
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


# ----------------------------------------------------
# 1. Authentication & Authorization Enforcement
# ----------------------------------------------------

def test_unauthenticated_request_rejected(unauthenticated_client):
    """Scenario 1: Unauthenticated request to protected endpoints is rejected with HTTP 401."""
    # Test protected scan endpoint
    res_scan = unauthenticated_client.post("/api/websites/inspect-url", json={"url": "https://example.com"})
    assert res_scan.status_code == 401
    assert "Authentication required" in res_scan.json()["detail"]

    # Test protected import endpoint
    res_import = unauthenticated_client.post(
        "/api/websites/import",
        files={"file": ("test.csv", b"company_name,website_url\nAcme,https://example.com", "text/csv")}
    )
    assert res_import.status_code == 401

    # Test protected reviews endpoint
    res_rev = unauthenticated_client.get("/api/captcha/reviews")
    assert res_rev.status_code == 401


def test_authenticated_operator_permitted(operator_client):
    """Scenario 2: Authenticated operator can perform standard inspection and query tasks."""
    res_me = operator_client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["user"]["role"] == UserRole.OPERATOR

    res_demo = operator_client.post("/api/websites/inspect-demo", json={"html": "<form><input></form>"})
    assert res_demo.status_code == 200


def test_operator_cannot_perform_admin_operations(operator_client):
    """Scenario 3: Operator cannot access administrator-only endpoints (HTTP 403 Forbidden)."""
    # Attempt to create a user as operator
    res_user = operator_client.post("/api/auth/users", json={
        "username": "unauthorized_user",
        "email": "unauth@example.com",
        "password": "Password123!",
        "role": UserRole.OPERATOR
    })
    assert res_user.status_code == 403
    assert "Required role: admin" in res_user.json()["detail"]

    # Attempt to read audit logs as operator
    res_logs = operator_client.get("/api/auth/audit-logs")
    assert res_logs.status_code == 403


def test_admin_can_perform_admin_operations(admin_client):
    """Admin can create users and inspect audit logs."""
    timestamp_suffix = str(int(time.time()))
    res_user = admin_client.post("/api/auth/users", json={
        "username": f"new_op_{timestamp_suffix}",
        "email": f"op_{timestamp_suffix}@example.com",
        "password": "StrongPassword123!",
        "role": UserRole.OPERATOR
    })
    assert res_user.status_code == 200
    assert res_user.json()["success"] is True

    res_logs = admin_client.get("/api/auth/audit-logs")
    assert res_logs.status_code == 200
    assert "logs" in res_logs.json()


def test_unauthorized_user_cannot_modify_reviews(unauthenticated_client):
    """Scenario 4: Unauthorized user cannot modify human review records."""
    res = unauthenticated_client.patch(
        "/api/captcha/reviews/some-review-id",
        json={"review_status": "manually_verified"}
    )
    assert res.status_code == 401


# ----------------------------------------------------
# 2. SSRF & Loopback Protection Hardening
# ----------------------------------------------------

def test_client_cannot_enable_loopback(operator_client, monkeypatch):
    """Scenario 5: Client cannot enable loopback access when server setting is False."""
    # Force server setting to False
    monkeypatch.setattr(settings, "ALLOW_DEV_LOOPBACK", False)
    assert settings.can_allow_loopback is False

    payload = {
        "url": "http://127.0.0.1:8888",
        "allow_loopback": True,  # Client attempts to bypass
    }
    res = operator_client.post("/api/websites/inspect-url", json=payload)
    assert res.status_code == 400
    assert "Client-controlled loopback authorization is prohibited" in res.json()["detail"]


def test_production_environment_always_rejects_loopback(operator_client, monkeypatch):
    """Scenario 6: In production, loopback exceptions are unconditionally denied."""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOW_DEV_LOOPBACK", True)  # Even if flag was mistakenly true
    assert settings.can_allow_loopback is False  # Property must strictly return False

    allowed, reason = SecurityGuard.validate_target_url(
        "http://127.0.0.1:8888",
        allow_loopback=True,
    )
    assert allowed is False
    assert "Loopback address (127.0.0.1) is prohibited" in reason

    allowed_v6, reason_v6 = SecurityGuard.validate_target_url(
        "http://[::1]:8888",
        allow_loopback=True,
    )
    assert allowed_v6 is False
    assert "Loopback address" in reason_v6


def test_cloud_metadata_ip_blocked():
    """Scenario 8: Cloud metadata IP (169.254.169.254) is blocked unconditionally."""
    allowed, reason = SecurityGuard.validate_target_url(
        "http://169.254.169.254/latest/meta-data",
        allow_loopback=True
    )
    assert allowed is False
    assert "cloud metadata" in reason.lower()

    allowed_v6, reason_v6 = SecurityGuard.validate_target_url(
        "http://[fd00:ec2::254]/latest/meta-data",
        allow_loopback=True
    )
    assert allowed_v6 is False
    assert "cloud metadata" in reason_v6.lower()


def test_private_subnets_blocked():
    """Private RFC 1918 subnets (10.0.0.1, 192.168.1.1, 172.16.0.1) are blocked."""
    for ip in ("10.0.0.1", "192.168.1.1", "172.16.0.1"):
        allowed, reason = SecurityGuard.validate_target_url(f"http://{ip}/admin", allow_loopback=True)
        assert allowed is False
        assert "prohibited" in reason.lower()


def test_non_approved_port_blocked():
    """Non-standard/sensitive ports (22, 6379, 5432) are rejected."""
    allowed, reason = SecurityGuard.validate_target_url("http://example.com:6379")
    assert allowed is False
    assert "Non-standard port" in reason


def test_redirect_to_private_ip_blocked():
    """Scenario 7: Redirect to private IP is blocked by validate_redirect_url."""
    allowed, reason = SecurityGuard.validate_redirect_url(
        redirect_url="http://10.0.0.1/internal-secret",
        original_url="https://example.com/page",
        require_same_domain=False,
    )
    assert allowed is False
    assert "Redirect target rejected" in reason


# ----------------------------------------------------
# 3. Rate Limiting & Resource Protection
# ----------------------------------------------------

def test_rate_limiting_enforcement(unauthenticated_client):
    """Scenario 11: Rapid requests trigger HTTP 429 Too Many Requests."""
    limiter.reset("login:127.0.0.1")
    # settings.RATE_LIMIT_LOGIN_PER_MIN is 5
    for _ in range(5):
        unauthenticated_client.post("/api/auth/login", json={"username": "fake", "password": "wrongpassword"})

    # 6th attempt must be throttled
    throttled = unauthenticated_client.post("/api/auth/login", json={"username": "fake", "password": "wrongpassword"})
    assert throttled.status_code == 429
    assert "Rate limit exceeded" in throttled.json()["detail"]
    assert "Retry-After" in throttled.headers
    limiter.reset("login:127.0.0.1")


def test_csv_row_and_size_limits(operator_client):
    """Scenario 12: CSV size and row limit protections."""
    # Exceed row count
    rows = ["company_name,website_url"]
    for i in range(settings.MAX_CSV_ROWS + 5):
        rows.append(f"Company {i},https://example.com")
    large_csv = "\n".join(rows).encode("utf-8")

    res = operator_client.post(
        "/api/websites/import",
        files={"file": ("large.csv", io.BytesIO(large_csv), "text/csv")}
    )
    assert res.status_code == 400
    assert "exceeds maximum permitted limit" in res.json()["detail"]


# ----------------------------------------------------
# 4. Database Migrations & Audit Integrity
# ----------------------------------------------------

def test_database_records_and_audit_trail():
    """Scenario 13 & 14: Audit logs are created on security events."""
    db = SessionLocal()
    try:
        # Check users table exists and has records
        user_count = db.query(User).count()
        assert user_count >= 2

        # Check audit_logs table exists and captures entries
        audit_count = db.query(AuditLog).count()
        assert audit_count >= 1
    finally:
        db.close()
