"""
Phase 6B hardening tests: evidence authentication, /health minimisation, gated admin bootstrap,
token revocation, server-side validation of client modes, request-size limits, rate limits,
job limits, reviewer identity/history, tamper-evident audit chain, and log redaction.
"""
import asyncio
import base64
import io
import json
import sqlite3
import threading
import uuid

import pytest
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.config import settings
from app.database import SessionLocal, get_db, _AUDIT_TRIGGERS
from app.main import app
from app.models import AuditLog, Base, HumanReviewRecord, ReviewDecision, User, UserRole
from app.services import audit
from app.services.audit import (
    fingerprint,
    log_audit_event,
    redact,
    redact_url,
    sanitize_request_id,
    verify_audit_chain,
)
from app.services.auth_service import create_access_token, verify_password_or_dummy
from app.services.captcha_intelligence import extract_sitekeys, validate_client_assertions
from app.services.job_manager import JobLimitExceeded, JobManager
from app.services.rate_limiter import limiter


# ---------------------------------------------------------------- fixtures
def _client_with_token(user_id, username, role):
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + create_access_token(user_id=user_id, username=username, role=role)
    return c


@pytest.fixture
def operator_client():
    return _client_with_token("test-operator-id", "test_operator", UserRole.OPERATOR)


@pytest.fixture
def admin_client():
    return _client_with_token("test-admin-id", "test_admin", UserRole.ADMIN)


@pytest.fixture
def anon_client():
    c = TestClient(app)
    c._unauthenticated = True
    return c


@pytest.fixture
def temp_db(tmp_path):
    """Fresh, isolated database (schema + audit triggers) for destructive/bootstrap tests."""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'iso.db').as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for trig in _AUDIT_TRIGGERS:
            conn.execute(text(trig))
    maker = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield engine, maker
    engine.dispose()


@pytest.fixture
def override_db(temp_db):
    _, maker = temp_db

    def _get():
        db = maker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get
    yield maker
    app.dependency_overrides.pop(get_db, None)


PW = "Str0ng-Test-Passw0rd!"


def _make_user(admin_client, role=UserRole.OPERATOR):
    name = "t6b_" + uuid.uuid4().hex[:10]
    res = admin_client.post(
        "/api/auth/users",
        json={"username": name, "email": f"{name}@test.internal", "password": PW, "role": role},
    )
    assert res.status_code == 200, res.text
    return name, res.json()["user"]["id"]


def _login(username, password=PW):
    c = TestClient(app)
    c._unauthenticated = True
    res = c.post("/api/auth/login", json={"username": username, "password": password})
    return c, res


# ================================================================ 1. evidence auth
@pytest.fixture
def evidence_file():
    scan_dir = settings.SCANS_EVIDENCE_DIR / str(uuid.uuid4())
    scan_dir.mkdir(parents=True)
    f = scan_dir / "page_0_home.png"
    Image.new("RGB", (4, 4), "white").save(f)
    yield scan_dir.name, f
    f.unlink(missing_ok=True)
    scan_dir.rmdir()


def test_evidence_requires_authentication(anon_client, evidence_file):
    scan, _ = evidence_file
    assert anon_client.get(f"/api/evidence/scans/{scan}/page_0_home.png").status_code == 401


def test_old_public_evidence_mount_is_gone(anon_client, evidence_file):
    scan, _ = evidence_file
    assert anon_client.get(f"/evidence/scans/{scan}/page_0_home.png").status_code == 404
    assert anon_client.get("/evidence/TEST_EVIDENCE.md").status_code == 404


def test_evidence_served_to_authenticated_operator(operator_client, evidence_file):
    scan, _ = evidence_file
    res = operator_client.get(f"/api/evidence/scans/{scan}/page_0_home.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert "no-store" in res.headers["cache-control"]
    assert res.headers["x-content-type-options"] == "nosniff"
    # stored relative path form ("evidence/scans/...") also works
    assert operator_client.get(f"/api/evidence/evidence/scans/{scan}/page_0_home.png").status_code == 200


@pytest.mark.parametrize("path", [
    "../.env", "scans/../../.env", "scans/%2e%2e/%2e%2e/.env", "TEST_EVIDENCE.md", "phase5/phase5_01_login_screen.png",
    "scans/not-a-uuid/x.png", "scans/00000000-0000-0000-0000-000000000000/../../../.env",
    "scans/00000000-0000-0000-0000-000000000000/x.html", "scans/00000000-0000-0000-0000-000000000000/missing.png",
    "scans\\00000000-0000-0000-0000-000000000000\\x.png",
])
def test_evidence_path_restrictions(operator_client, path):
    assert operator_client.get(f"/api/evidence/{path}").status_code == 404


# ================================================================ 2. /health
def test_public_health_reveals_only_liveness(anon_client):
    for url in ("/health", "/api/health"):
        res = anon_client.get(url)
        assert res.status_code == 200
        assert res.json() == {"status": "healthy"}


def test_root_does_not_leak_configuration(anon_client):
    body = anon_client.get("/").json()
    assert "app_env" not in body and "live_scan_enabled" not in body


def test_health_details_require_auth(anon_client, operator_client):
    assert anon_client.get("/api/health/details").status_code == 401
    res = operator_client.get("/api/health/details")
    assert res.status_code == 200 and "allowed_domains" in res.json()


# ================================================================ 3. admin bootstrap
BOOT_TOKEN = "bootstrap-secret-token-" + "x" * 12
BOOT_BODY = {"username": "first_admin", "email": "first@test.internal", "password": "Another-Str0ng-Pass!"}


def test_setup_endpoint_absent_when_token_not_configured(anon_client, override_db, monkeypatch):
    monkeypatch.setattr(settings, "INITIAL_ADMIN_SETUP_TOKEN", "")
    res = anon_client.post("/api/auth/setup-initial-admin", json=BOOT_BODY, headers={"X-Setup-Token": BOOT_TOKEN})
    assert res.status_code == 404


def test_setup_rejects_missing_or_wrong_token_and_audits(anon_client, override_db, monkeypatch):
    monkeypatch.setattr(settings, "INITIAL_ADMIN_SETUP_TOKEN", BOOT_TOKEN)
    assert anon_client.post("/api/auth/setup-initial-admin", json=BOOT_BODY).status_code == 403
    bad = anon_client.post("/api/auth/setup-initial-admin", json=BOOT_BODY, headers={"X-Setup-Token": "nope"})
    assert bad.status_code == 403
    db = override_db()
    try:
        assert db.query(User).count() == 0
        assert db.query(AuditLog).filter_by(action="auth.initial_admin_setup_denied").count() == 2
    finally:
        db.close()


def test_setup_succeeds_once_then_closes(anon_client, override_db, monkeypatch):
    monkeypatch.setattr(settings, "INITIAL_ADMIN_SETUP_TOKEN", BOOT_TOKEN)
    ok = anon_client.post("/api/auth/setup-initial-admin", json=BOOT_BODY, headers={"X-Setup-Token": BOOT_TOKEN})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "admin"
    again = anon_client.post(
        "/api/auth/setup-initial-admin",
        json={**BOOT_BODY, "username": "second_admin", "email": "second@test.internal"},
        headers={"X-Setup-Token": BOOT_TOKEN},
    )
    assert again.status_code == 400


def test_setup_weak_password_rejected(anon_client, override_db, monkeypatch):
    monkeypatch.setattr(settings, "INITIAL_ADMIN_SETUP_TOKEN", BOOT_TOKEN)
    res = anon_client.post(
        "/api/auth/setup-initial-admin",
        json={**BOOT_BODY, "password": "short"},
        headers={"X-Setup-Token": BOOT_TOKEN},
    )
    assert res.status_code == 422


def test_setup_is_race_safe(override_db, monkeypatch):
    """Two simultaneous bootstrap attempts with different identities: exactly one wins."""
    monkeypatch.setattr(settings, "INITIAL_ADMIN_SETUP_TOKEN", BOOT_TOKEN)
    codes = []

    def attempt(i):
        c = TestClient(app)
        c._unauthenticated = True
        r = c.post(
            "/api/auth/setup-initial-admin",
            json={"username": f"racer_{i}", "email": f"r{i}@test.internal", "password": "Another-Str0ng-Pass!"},
            headers={"X-Setup-Token": BOOT_TOKEN},
        )
        codes.append(r.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [200, 400]
    db = override_db()
    try:
        assert db.query(User).count() == 1
    finally:
        db.close()


def test_short_setup_token_rejected_in_production_config(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ALLOW_DEV_LOOPBACK", False)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "k" * 40)
    monkeypatch.setattr(settings, "INITIAL_ADMIN_SETUP_TOKEN", "too-short")
    with pytest.raises(ValueError):
        settings.validate_production_config()


# ================================================================ 4. token revocation
def test_logout_revokes_token_server_side(admin_client):
    name, _ = _make_user(admin_client)
    c, res = _login(name)
    token = res.json()["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    after = c.get("/api/auth/me")
    assert after.status_code == 401 and "revoked" in after.json()["detail"].lower()


def test_logout_all_invalidates_every_session(admin_client):
    name, _ = _make_user(admin_client)
    c1, r1 = _login(name)
    c2, r2 = _login(name)
    c1.headers["Authorization"] = f"Bearer {r1.json()['access_token']}"
    c2.headers["Authorization"] = f"Bearer {r2.json()['access_token']}"
    assert c1.get("/api/auth/me").status_code == 200 and c2.get("/api/auth/me").status_code == 200
    assert c1.post("/api/auth/logout-all").status_code == 200
    assert c1.get("/api/auth/me").status_code == 401
    assert c2.get("/api/auth/me").status_code == 401
    # a fresh login works again
    c3, r3 = _login(name)
    assert r3.status_code == 200


def test_admin_can_revoke_user_sessions(admin_client):
    name, uid = _make_user(admin_client)
    c, res = _login(name)
    c.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
    assert c.get("/api/auth/me").status_code == 200
    assert admin_client.post(f"/api/auth/users/{uid}/revoke-sessions").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_deactivation_blocks_login_and_kills_existing_token(admin_client):
    name, uid = _make_user(admin_client)
    c, res = _login(name)
    c.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
    assert admin_client.post(f"/api/auth/users/{uid}/deactivate").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    _, relogin = _login(name)
    assert relogin.status_code == 401


def test_operator_cannot_revoke_or_deactivate(operator_client, admin_client):
    _, uid = _make_user(admin_client)
    assert operator_client.post(f"/api/auth/users/{uid}/revoke-sessions").status_code == 403
    assert operator_client.post(f"/api/auth/users/{uid}/deactivate").status_code == 403


def test_admin_cannot_deactivate_self(admin_client):
    assert admin_client.post("/api/auth/users/test-admin-id/deactivate").status_code == 400


def test_login_performs_equal_work_for_unknown_user(monkeypatch):
    calls = []
    import app.services.auth_service as svc
    real = svc.verify_password
    monkeypatch.setattr(svc, "verify_password", lambda p, h: calls.append(h) or real(p, h))
    assert verify_password_or_dummy("whatever-pw", None) is False
    assert len(calls) == 1  # a real bcrypt comparison was still performed


# ================================================================ 5. client-asserted modes
REAL_RECAPTCHA = (
    "<script src='https://www.google.com/recaptcha/api.js'></script>"
    "<div class='g-recaptcha' data-sitekey='6LcREALPRODUCTIONKEYxxxxxxxxxxxxxxxxxxxx'></div>"
)
TEST_RECAPTCHA = (
    "<script src='https://www.google.com/recaptcha/api.js'></script>"
    "<div class='g-recaptcha' data-sitekey='6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'></div>"
)


def _png_b64(size=(60, 24)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_extract_sitekeys():
    assert extract_sitekeys(TEST_RECAPTCHA) == ["6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"]
    assert extract_sitekeys("<p>none</p>") == []


def test_official_test_flag_refused_for_production_site_key():
    a = validate_client_assertions(REAL_RECAPTCHA, None, None, False, True)
    assert a["is_official_test"]["accepted"] is False


def test_official_test_flag_refused_without_site_key():
    a = validate_client_assertions("<script src='https://www.google.com/recaptcha/api.js'></script>", None, None, False, True)
    assert a["is_official_test"]["accepted"] is False


def test_official_test_flag_refused_when_mixed_with_real_key():
    html = TEST_RECAPTCHA + "<div class='g-recaptcha' data-sitekey='6LcREALPRODUCTIONKEYxxxxxxxxxxxxxxxxxxxx'></div>"
    assert validate_client_assertions(html, None, None, False, True)["is_official_test"]["accepted"] is False


def test_official_test_flag_accepted_for_published_test_key():
    assert validate_client_assertions(TEST_RECAPTCHA, None, None, False, True)["is_official_test"]["accepted"] is True


def test_synthetic_flag_refused_without_image():
    assert validate_client_assertions(None, None, None, True, False)["is_synthetic"]["accepted"] is False


def test_synthetic_flag_refused_when_page_has_real_provider():
    a = validate_client_assertions(REAL_RECAPTCHA, None, b"img", True, False)
    assert a["is_synthetic"]["accepted"] is False


def test_synthetic_flag_accepted_for_valid_image_and_plain_page():
    assert validate_client_assertions("<p>x</p>", None, b"img", True, False)["is_synthetic"]["accepted"] is True


def test_api_cannot_hide_real_recaptcha_behind_synthetic_flag(operator_client):
    res = operator_client.post(
        "/api/captcha/classify",
        json={"html": REAL_RECAPTCHA, "is_synthetic": True, "image_base64": _png_b64()},
    )
    body = res.json()
    assert res.status_code == 200
    assert body["classification"] == "google_recaptcha"
    assert body["human_review_required"] is True
    assert body["client_assertions"]["is_synthetic"]["accepted"] is False


def test_api_official_test_flag_cannot_bypass_review_for_real_key(operator_client):
    body = operator_client.post(
        "/api/captcha/classify", json={"html": REAL_RECAPTCHA, "is_official_test": True}
    ).json()
    assert body["human_review_required"] is True
    assert body["handling_strategy"] == "queue_for_human_review"
    assert body["client_assertions"]["is_official_test"]["accepted"] is False


def test_api_official_test_mode_honored_for_published_test_key(operator_client):
    body = operator_client.post(
        "/api/captcha/classify", json={"html": TEST_RECAPTCHA, "is_official_test": True}
    ).json()
    assert body["handling_strategy"] == "official_token_verify"
    assert body["client_assertions"]["is_official_test"]["accepted"] is True


# ================================================================ 6. request size limits
def test_oversized_json_rejected_by_content_length(operator_client):
    big = json.dumps({"html": "a" * (settings.MAX_JSON_BODY_BYTES + 10)})
    res = operator_client.post("/api/captcha/classify", content=big, headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_oversized_chunked_body_rejected(operator_client):
    def gen():
        for _ in range(4):
            yield b"x" * (settings.MAX_JSON_BODY_BYTES // 2)

    res = operator_client.post("/api/captcha/classify", content=gen(), headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_html_field_length_limit(operator_client):
    res = operator_client.post("/api/captcha/classify", json={"html": "a" * (settings.MAX_HTML_CHARS + 1)})
    assert res.status_code == 422
    res = operator_client.post("/api/websites/inspect-demo", json={"html": "a" * (settings.MAX_HTML_CHARS + 1)})
    assert res.status_code == 422


def test_invalid_base64_rejected(operator_client):
    res = operator_client.post("/api/captcha/evaluate-handling", json={"image_base64": "***not base64***"})
    assert res.status_code == 400


def test_non_image_payload_rejected(operator_client):
    payload = base64.b64encode(b"this is definitely not an image").decode()
    assert operator_client.post("/api/captcha/classify", json={"image_base64": payload}).status_code == 400


def test_decompression_bomb_dimensions_rejected(operator_client):
    buf = io.BytesIO()
    Image.new("1", (6000, 6000)).save(buf, format="PNG")  # tiny file, 36M pixels
    assert len(buf.getvalue()) < settings.MAX_IMAGE_BYTES
    res = operator_client.post(
        "/api/captcha/classify", json={"image_base64": base64.b64encode(buf.getvalue()).decode()}
    )
    assert res.status_code == 413


def test_oversized_base64_rejected(operator_client):
    res = operator_client.post("/api/captcha/classify", json={"image_base64": "A" * (settings.MAX_IMAGE_BYTES * 2)})
    assert res.status_code in (413, 422)


def test_token_field_limits(operator_client):
    assert operator_client.post("/api/captcha/verify-token", json={"token": "t" * 5000}).status_code == 422
    assert operator_client.post("/api/captcha/verify-token", json={"simulate_status": "drop table"}).status_code == 422


def test_valid_image_still_accepted(operator_client):
    res = operator_client.post("/api/captcha/classify", json={"image_base64": _png_b64(), "is_synthetic": True})
    assert res.status_code == 200 and res.json()["client_assertions"]["is_synthetic"]["accepted"] is True


# ================================================================ 7. rate limits
def test_compute_endpoints_are_rate_limited(operator_client):
    limit = settings.RATE_LIMIT_COMPUTE_PER_MIN
    codes = [
        operator_client.post("/api/captcha/verify-token", json={"token": "t", "simulate_status": "invalid"}).status_code
        for _ in range(limit + 3)
    ]
    assert codes[:limit] == [200] * limit
    assert all(c == 429 for c in codes[limit:])


def test_classify_is_rate_limited(operator_client):
    limit = settings.RATE_LIMIT_COMPUTE_PER_MIN
    codes = [operator_client.post("/api/captcha/classify", json={"html": "<p>x</p>"}).status_code for _ in range(limit + 2)]
    assert codes[-1] == 429


def test_admin_operations_are_rate_limited(admin_client):
    limit = settings.RATE_LIMIT_ADMIN_PER_MIN
    codes = [admin_client.post("/api/auth/users/does-not-exist/revoke-sessions").status_code for _ in range(limit + 2)]
    assert codes[0] == 404 and codes[-1] == 429


# ================================================================ 8. job limits
@pytest.mark.anyio
async def test_job_manager_enforces_concurrency_and_per_user_limits(monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS", 2)
    monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 5)
    jm = JobManager()
    gate = asyncio.Event()

    async def work():
        await gate.wait()

    t1 = jm.spawn("crawl", "u1", work())
    t2 = jm.spawn("crawl", "u2", work())
    with pytest.raises(JobLimitExceeded):
        jm.spawn("crawl", "u3", work())
    assert jm.active("crawl") == 2
    gate.set()
    await asyncio.gather(t1, t2)
    assert jm.active("crawl") == 0
    jm.spawn("crawl", "u3", work())  # capacity returned after completion
    await jm.shutdown()


@pytest.mark.anyio
async def test_job_manager_per_user_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS", 10)
    monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 1)
    jm = JobManager()
    gate = asyncio.Event()

    async def work():
        await gate.wait()

    jm.spawn("crawl", "same-user", work())
    with pytest.raises(JobLimitExceeded):
        jm.spawn("crawl", "same-user", work())
    jm.spawn("crawl", "other-user", work())
    gate.set()
    await jm.shutdown()


@pytest.mark.anyio
async def test_job_manager_foreground_slot_and_shutdown_cancel(monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS", 1)
    monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 5)
    jm = JobManager()
    async with jm.slot("crawl", "u"):
        assert jm.active("crawl") == 1
        with pytest.raises(JobLimitExceeded):
            async with jm.slot("crawl", "v"):
                pass
    assert jm.active("crawl") == 0

    async def forever():
        await asyncio.sleep(3600)

    jm.spawn("crawl", "u", forever())
    await jm.shutdown()
    assert jm.active("crawl") == 0


def test_inspect_url_returns_429_when_crawl_capacity_exhausted(operator_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS", 0)
    res = operator_client.post(
        "/api/websites/inspect-url", json={"url": "http://127.0.0.1:18765/", "allow_loopback": True}
    )
    assert res.status_code == 429 and "Retry-After" in res.headers


def test_scan_batch_returns_429_when_batch_capacity_exhausted(operator_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_BATCH_JOBS", 0)
    res = operator_client.post(
        "/api/websites/scan-batch",
        json={"websites": [{"company_name": "A", "website_url": "fixture://normal_contact_form.html"}]},
    )
    assert res.status_code == 429


# ================================================================ 9. reviewer identity / history
@pytest.fixture
def review_id():
    db = SessionLocal()
    try:
        rec = HumanReviewRecord(
            page_url="https://example.com/contact", captcha_provider="google_recaptcha",
            reason_for_review="test", review_status="pending",
        )
        db.add(rec)
        db.commit()
        return rec.id
    finally:
        db.close()


def test_review_decision_records_identity_and_history(operator_client, admin_client, review_id):
    first = operator_client.patch(
        f"/api/captcha/reviews/{review_id}", json={"review_status": "approved", "operator_notes": "looks fine"}
    )
    assert first.status_code == 200
    assert first.json()["review"]["reviewed_by"] == "test_operator"
    second = admin_client.patch(f"/api/captcha/reviews/{review_id}", json={"review_status": "rejected"})
    assert second.json()["review"]["reviewed_by"] == "test_admin"
    assert second.json()["review"]["decision_count"] == 2

    hist = operator_client.get(f"/api/captcha/reviews/{review_id}/history").json()["history"]
    assert [(h["decided_by"], h["previous_status"], h["new_status"]) for h in hist] == [
        ("test_operator", "pending", "approved"),
        ("test_admin", "approved", "rejected"),
    ]
    assert hist[0]["notes"] == "looks fine"
    detail = operator_client.get(f"/api/captcha/reviews/{review_id}").json()
    assert len(detail["history"]) == 2


def test_review_history_is_append_only_in_database(operator_client, review_id):
    operator_client.patch(f"/api/captcha/reviews/{review_id}", json={"review_status": "approved"})
    db = SessionLocal()
    try:
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("UPDATE review_decisions SET new_status='pending' WHERE review_id=:r"), {"r": review_id})
            db.commit()
        db.rollback()
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("DELETE FROM review_decisions WHERE review_id=:r"), {"r": review_id})
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_review_notes_not_copied_into_audit_trail(operator_client, review_id):
    operator_client.patch(
        f"/api/captcha/reviews/{review_id}",
        json={"review_status": "approved", "operator_notes": "contains-private-note-XYZZY"},
    )
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter_by(action="review.update", resource_id=review_id).all()
        assert rows and all("XYZZY" not in (r.details or "") for r in rows)
    finally:
        db.close()


# ================================================================ 10. tamper-evident audit
def _write_events(maker, n=5):
    db = maker()
    try:
        for i in range(n):
            log_audit_event(db, action=f"test.event_{i}", actor_username="tester", details={"i": i, "token": "s3cr3t"})
    finally:
        db.close()


def test_audit_chain_valid_after_normal_use(temp_db):
    _, maker = temp_db
    _write_events(maker)
    db = maker()
    try:
        report = verify_audit_chain(db)
        assert report["valid"] is True and report["checked_entries"] == 5
        rows = db.query(AuditLog).order_by(AuditLog.seq).all()
        assert [r.seq for r in rows] == [1, 2, 3, 4, 5]
        assert rows[0].prev_hash == audit.GENESIS_HASH and rows[1].prev_hash == rows[0].entry_hash
    finally:
        db.close()


def test_database_blocks_audit_update_and_delete(temp_db):
    _, maker = temp_db
    _write_events(maker, 2)
    db = maker()
    try:
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("UPDATE audit_logs SET action='x'"))
            db.commit()
        db.rollback()
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("DELETE FROM audit_logs"))
            db.commit()
        db.rollback()
    finally:
        db.close()


def _raw(engine):
    path = engine.url.database
    return sqlite3.connect(path)


def test_chain_detects_modified_entry_even_if_triggers_removed(temp_db):
    engine, maker = temp_db
    _write_events(maker)
    conn = _raw(engine)
    conn.execute("DROP TRIGGER audit_logs_no_update")
    conn.execute("UPDATE audit_logs SET action='forged.action' WHERE seq=3")
    conn.commit()
    conn.close()
    db = maker()
    try:
        report = verify_audit_chain(db)
        assert report["valid"] is False and report["first_invalid_seq"] == 3
    finally:
        db.close()


def test_chain_detects_deleted_entry(temp_db):
    engine, maker = temp_db
    _write_events(maker)
    conn = _raw(engine)
    conn.execute("DROP TRIGGER audit_logs_no_delete")
    conn.execute("DELETE FROM audit_logs WHERE seq=2")
    conn.commit()
    conn.close()
    db = maker()
    try:
        report = verify_audit_chain(db)
        assert report["valid"] is False and "gap" in report["problem"]
    finally:
        db.close()


def test_chain_detects_rewritten_hash_without_key(temp_db):
    """Recomputing a plain SHA-256 (no HMAC key) over a forged entry is detected."""
    import hashlib
    engine, maker = temp_db
    _write_events(maker)
    conn = _raw(engine)
    conn.execute("DROP TRIGGER audit_logs_no_update")
    conn.execute("UPDATE audit_logs SET action='forged', entry_hash=? WHERE seq=5", (hashlib.sha256(b"forged").hexdigest(),))
    conn.commit()
    conn.close()
    db = maker()
    try:
        assert verify_audit_chain(db)["valid"] is False
    finally:
        db.close()


def test_audit_verify_endpoint_on_live_database(admin_client, operator_client):
    admin_client.get("/api/auth/me")  # no audit
    res = admin_client.get("/api/auth/audit-logs/verify")
    assert res.status_code == 200 and res.json()["valid"] is True
    assert operator_client.get("/api/auth/audit-logs/verify").status_code == 403


def test_audit_log_listing_limit_is_capped(admin_client):
    assert admin_client.get("/api/auth/audit-logs?limit=100000").status_code == 422


# ================================================================ 11. redaction
def test_redact_nested_secrets():
    jwt_like = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"
    out = redact({
        "password": "hunter2",
        "nested": {"api_key": "AKIA123", "Authorization": "Bearer abc", "ok": "value"},
        "note": f"token was {jwt_like} in text",
        "list": [{"secret": "s"}, "plain"],
        "token_version": 3,
    })
    flat = json.dumps(out)
    assert "hunter2" not in flat and "AKIA123" not in flat and jwt_like not in flat and '"s"' not in flat
    assert out["nested"]["ok"] == "value" and out["token_version"] == 3


def test_redact_url_strips_credentials_and_query():
    assert redact_url("https://user:pw@example.com/a/b?token=abc&x=1#frag") == "https://example.com/a/b?[REDACTED]"
    assert redact("see https://u:p@example.com/p?k=v now") == "see https://example.com/p?[REDACTED] now"


def test_redaction_truncates_long_strings():
    assert len(redact("a" * 5000)) < 600


def test_request_id_sanitisation():
    assert sanitize_request_id("abc-123_DEF.9") == "abc-123_DEF.9"
    for bad in ("a b", "x" * 100, "id\nforged-log-line", "<script>", ""):
        assert sanitize_request_id(bad) is None


def test_fingerprint_is_stable_and_not_reversible():
    assert fingerprint("alice") == fingerprint("alice") != fingerprint("bob")
    assert "alice" not in fingerprint("alice")


def test_failed_login_does_not_store_attempted_username(anon_client):
    typed = "My-Real-Passw0rd!-typed-in-username-box"
    res = anon_client.post("/api/auth/login", json={"username": typed, "password": "wrong-password"})
    assert res.status_code == 401
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter_by(action="auth.login_failed").order_by(AuditLog.seq.desc()).limit(5).all()
        assert rows
        for r in rows:
            blob = json.dumps(r.to_dict())
            assert typed not in blob and "Passw0rd" not in blob
        assert any(fingerprint(typed) in (r.details or "") for r in rows)
    finally:
        db.close()


def test_inspect_url_audit_entry_redacts_query_secrets(operator_client):
    operator_client.post(
        "/api/websites/inspect-url",
        json={"url": "http://127.0.0.1:18765/page?api_key=SUPERSECRETKEY123", "allow_loopback": True,
              "background": True, "max_pages": 1},
    )
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter_by(action="scan.create").order_by(AuditLog.seq.desc()).limit(3).all()
        assert rows and all("SUPERSECRETKEY123" not in (r.details or "") for r in rows)
    finally:
        db.close()


# ================================================================ misc headers
def test_security_headers_and_request_id_handling(anon_client):
    res = anon_client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
    assert res.headers["x-request-id"] != "bad id with spaces"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    ok = anon_client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert ok.headers["x-request-id"] == "trace-123"
