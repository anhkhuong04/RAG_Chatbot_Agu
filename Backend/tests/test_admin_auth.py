import os
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# security.py unit tests
# ---------------------------------------------------------------------------

class TestSecurity:
    """Pure unit tests for core/security.py helpers (no FastAPI needed)."""

    def setup_method(self):
        # Re-import each time to get fresh module state
        from app.core.security import (
            create_access_token,
            decode_access_token,
            verify_password,
            hash_password,
        )
        self.create_access_token = create_access_token
        self.decode_access_token = decode_access_token
        self.verify_password = verify_password
        self.hash_password = hash_password

    # -- password hashing --

    def test_hash_and_verify_correct_password(self):
        hashed = self.hash_password("secret123")
        assert self.verify_password("secret123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = self.hash_password("secret123")
        assert self.verify_password("wrong", hashed) is False

    def test_hash_is_not_plaintext(self):
        hashed = self.hash_password("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$2b$")  # bcrypt prefix

    # -- JWT tokens --

    def test_create_and_decode_token(self):
        token = self.create_access_token({"sub": "admin"})
        payload = self.decode_access_token(token)
        assert payload["sub"] == "admin"
        assert "exp" in payload

    def test_token_with_custom_expiry(self):
        token = self.create_access_token(
            {"sub": "admin"},
            expires_delta=timedelta(minutes=5),
        )
        payload = self.decode_access_token(token)
        assert payload["sub"] == "admin"

    def test_decode_invalid_token_raises(self):
        from jose import JWTError
        with pytest.raises(JWTError):
            self.decode_access_token("not.a.valid.token")

    def test_decode_tampered_token_raises(self):
        from jose import JWTError
        token = self.create_access_token({"sub": "admin"})
        # Flip a character in the signature part
        parts = token.rsplit(".", 1)
        tampered = parts[0] + ".TAMPERED"
        with pytest.raises(JWTError):
            self.decode_access_token(tampered)

def _build_test_app():
    app = FastAPI()
    from app.api.v1.endpoints.admin import router
    app.include_router(router, prefix="/api/v1")
    return app


class TestAdminLogin:
    """Tests for POST /api/v1/admin/login."""

    def setup_method(self):
        self.app = _build_test_app()
        self.client = TestClient(self.app)
        from app.core.security import get_admin_credentials
        self.admin_username, self.admin_password = get_admin_credentials(refresh_env=True)

    def test_login_success(self):
        resp = self.client.post(
            "/api/v1/admin/login",
            json={"username": self.admin_username, "password": self.admin_password},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self):
        resp = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_wrong_username(self):
        resp = self.client.post(
            "/api/v1/admin/login",
            json={"username": "hacker", "password": self.admin_password},
        )
        assert resp.status_code == 401

    def test_login_missing_fields(self):
        resp = self.client.post("/api/v1/admin/login", json={})
        assert resp.status_code == 422  # validation error


class TestProtectedRoutes:
    """Ensure protected admin routes return 401/403 without a valid token."""

    PROTECTED_ROUTES = [
        ("GET",    "/api/v1/admin/documents"),
        ("POST",  "/api/v1/admin/clear-cache"),
        ("GET",   "/api/v1/admin/prompts"),
    ]

    def setup_method(self):
        self.app = _build_test_app()
        self.client = TestClient(self.app)
        from app.core.security import get_admin_credentials
        self.admin_username, self.admin_password = get_admin_credentials(refresh_env=True)

    @pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
    def test_no_token_returns_401(self, method, path):
        resp = self.client.request(method, path)
        assert resp.status_code in (401, 403)

    @pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
    def test_invalid_token_returns_401(self, method, path):
        resp = self.client.request(
            method, path, headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401

    def test_valid_token_passes_auth(self):
        login_resp = self.client.post(
            "/api/v1/admin/login",
            json={"username": self.admin_username, "password": self.admin_password},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # GET /documents will likely fail with 500 (no real DB),
        # but it should NOT be 401 or 403.
        resp = self.client.get("/api/v1/admin/documents", headers=headers)
        assert resp.status_code not in (401, 403)

    def test_upload_without_token_rejected(self):
        resp = self.client.post("/api/v1/admin/upload")
        assert resp.status_code in (401, 403)
