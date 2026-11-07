import os
import secrets
import pytest
from starlette.testclient import TestClient

# Ensure test environment settings
os.environ["APP_ENV"] = "test"
os.environ["ALLOW_DEV_LOOPBACK"] = "true"

from app.database import SessionLocal, init_db
from app.models import User, UserRole
from app.services.auth_service import hash_password, create_access_token


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure database schema is initialized and test users exist for automated runs."""
    init_db()
    db = SessionLocal()
    try:
        op = db.query(User).filter(User.username == "test_operator").first()
        if not op:
            op = User(
                id="test-operator-id",
                username="test_operator",
                email="operator@test.internal",
                hashed_password=hash_password(secrets.token_urlsafe(24)),  # random; tests use tokens
                role=UserRole.OPERATOR,
                is_active=True,
            )
            db.add(op)

        adm = db.query(User).filter(User.username == "test_admin").first()
        if not adm:
            adm = User(
                id="test-admin-id",
                username="test_admin",
                email="admin@test.internal",
                hashed_password=hash_password(secrets.token_urlsafe(24)),  # random; tests use tokens
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(adm)
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def auto_inject_auth_headers(monkeypatch):
    """
    Seamlessly inject operator authorization header into standard TestClient requests
    unless the client has explicitly set _unauthenticated = True or provided custom headers.
    """
    token = create_access_token(
        user_id="test-operator-id",
        username="test_operator",
        role=UserRole.OPERATOR
    )
    orig_request = TestClient.request

    def authenticated_request(self, method, url, *args, **kwargs):
        headers = kwargs.get("headers")
        if headers is None:
            headers = {}
        else:
            headers = dict(headers)

        client_auth = getattr(self, "headers", {}).get("Authorization") or getattr(self, "headers", {}).get("authorization")
        if "Authorization" not in headers and "authorization" not in headers:
            if client_auth:
                headers["Authorization"] = client_auth
            elif not getattr(self, "_unauthenticated", False):
                headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        return orig_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", authenticated_request)
