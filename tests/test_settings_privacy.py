"""Privacy: /api/websites/settings must not reveal local filesystem layout, user profile names or secrets."""
import json
import re

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.auth_service import create_access_token
from app.models import UserRole

BS = chr(92)  # backslash, spelled out to keep the patterns unambiguous
PATH_PATTERNS = [
    re.compile("[A-Za-z]:[" + re.escape(BS) + "/]"),                     # Windows drive paths (C:\ or C:/)
    re.compile(re.escape(BS)),                                           # any backslash at all
    re.compile("(^|[ \"'])/(home|Users|usr|etc|var|opt|root|mnt)/"),      # POSIX absolute paths
    re.compile("AppData|OneDrive|/Users/|Program Files", re.I),
]


def _client(role=UserRole.OPERATOR, uid="test-operator-id", name="test_operator"):
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + create_access_token(uid, name, role)
    return c


def _strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


def test_settings_return_safe_values():
    body = _client().get("/api/websites/settings").json()
    assert body["success"] is True
    assert body["evidence_dir"] == "evidence/"
    assert body["tesseract_cmd"] == "tesseract"
    assert body["reports_dir"] == "reports/"


def test_settings_response_contains_no_absolute_paths_or_profile_names():
    res = _client().get("/api/websites/settings")
    text = res.text
    for s in _strings(res.json()):
        for rx in PATH_PATTERNS:
            assert not rx.search(s), f"path-like value leaked: {s!r}"
    for private in (str(settings.BASE_DIR), str(settings.EVIDENCE_DIR), str(settings.REPORTS_DIR),
                    str(settings.DATA_DIR), settings.TESSERACT_CMD):
        assert private not in text
    # the OS user name embedded in the real base directory must not appear anywhere
    parts = [p for p in settings.BASE_DIR.parts if p.lower() not in ("c:\\", "/", "users", "home", "desktop")]
    user_dirs = [p for p in settings.BASE_DIR.parts[1:3]]
    for p in user_dirs:
        if p.lower() not in ("users", "home") and len(p) > 2:
            assert p not in text, f"profile segment {p!r} leaked"


def test_settings_response_contains_no_secrets_or_database_location():
    text = _client().get("/api/websites/settings").text
    for secret in (settings.JWT_SECRET_KEY, settings.AUDIT_HMAC_KEY, settings.RECAPTCHA_TEST_SECRET_KEY,
                   settings.DATABASE_URL, settings.INITIAL_ADMIN_SETUP_TOKEN):
        if secret:
            assert secret not in text
    lowered = text.lower()
    for word in ("sqlite", "jwt_secret", "database_url", "hmac", "password", "secret"):
        assert word not in lowered


def test_all_expected_fields_still_present_for_frontend_compatibility():
    body = _client().get("/api/websites/settings").json()
    expected = {"success", "app_name", "app_env", "debug", "host", "port", "enable_live_scan",
                "allow_dev_loopback", "allowed_domains", "request_timeout_ms", "max_concurrent_pages",
                "crawler_max_pages", "crawler_max_depth", "crawler_page_timeout_ms",
                "crawler_total_timeout_sec", "tesseract_cmd", "tesseract_installed", "reports_dir",
                "evidence_dir", "current_user_role"}
    assert expected <= set(body)
    assert isinstance(body["tesseract_installed"], bool)


def test_internal_configuration_is_untouched_and_ocr_still_uses_it():
    import pytesseract
    from pathlib import Path
    from app.ocr import dataset as ds
    from app.ocr import engines

    before = (settings.TESSERACT_CMD, str(settings.EVIDENCE_DIR), str(settings.REPORTS_DIR))
    _client().get("/api/websites/settings")
    assert (settings.TESSERACT_CMD, str(settings.EVIDENCE_DIR), str(settings.REPORTS_DIR)) == before
    assert Path(settings.EVIDENCE_DIR).is_absolute() and Path(settings.REPORTS_DIR).is_absolute()

    if Path(settings.TESSERACT_CMD).exists():
        assert pytesseract.pytesseract.tesseract_cmd == settings.TESSERACT_CMD  # real path still in use
    png, label = ds.sample_from_seed(11)
    res = engines.recognize(png, "tesseract_legacy")
    assert res["failed"] is False and res["pred"], res  # Tesseract actually ran through the internal path


def test_settings_reports_tesseract_installed_from_real_path():
    from pathlib import Path
    body = _client().get("/api/websites/settings").json()
    assert body["tesseract_installed"] == Path(settings.TESSERACT_CMD).exists()


def test_settings_access_control_unchanged():
    anon = TestClient(app)
    anon._unauthenticated = True
    assert anon.get("/api/websites/settings").status_code == 401
    assert anon.get("/api/websites/settings", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert _client().get("/api/websites/settings").status_code == 200
    admin = _client(UserRole.ADMIN, "test-admin-id", "test_admin")
    body = admin.get("/api/websites/settings").json()
    assert body["current_user_role"] == "admin" and body["evidence_dir"] == "evidence/"


def test_other_diagnostic_endpoint_has_no_paths_either():
    res = _client().get("/api/health/details")
    for s in _strings(res.json()):
        for rx in PATH_PATTERNS:
            assert not rx.search(s), f"path-like value leaked by health details: {s!r}"
    assert _client().get("/health").json() == {"status": "healthy"}
