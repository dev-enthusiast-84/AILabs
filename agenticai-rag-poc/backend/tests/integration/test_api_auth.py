"""Integration tests for auth endpoints (admin login + guest mode)."""
import os

import pytest

_ADMIN_PWD = os.environ["ADMIN_PASSWORD"]


# ── Admin login ───────────────────────────────────────────────────────────────

def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPass!"})
    assert resp.status_code == 401


def test_admin_password_rotation_invalidates_old_password_and_token(client, monkeypatch):
    login = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    assert login.status_code == 200
    old_token = login.json()["access_token"]

    new_password = "NewRotatedPass@123"
    monkeypatch.setenv("ADMIN_PASSWORD", new_password)

    old_login = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    assert old_login.status_code == 401

    old_token_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_token_me.status_code == 401

    new_login = client.post("/api/auth/login", json={"username": "admin", "password": new_password})
    assert new_login.status_code == 200


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": _ADMIN_PWD})
    assert resp.status_code == 401


def test_login_short_password_rejected(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "short"})
    assert resp.status_code == 422


def test_me_with_valid_token(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"


def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 403


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "x-request-id" in resp.headers


# ── Guest mode ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def guest_headers(client):
    resp = client.post("/api/auth/guest")
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_guest_login_returns_token(client):
    resp = client.post("/api/auth/guest")
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_guest_me_shows_guest_role(client, guest_headers):
    resp = client.get("/api/auth/me", headers=guest_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "guest"
    assert body["role"] == "guest"


def test_guest_can_query(client, guest_headers):
    """Guests may use the query endpoint (chat functionality)."""
    from unittest.mock import patch
    mock_result = {"answer": "Test answer", "sources": [], "validation": "VALID", "tokens_used": 10, "mode": "agentic"}
    with patch("app.api.query.run_agent", return_value=mock_result), \
         patch("app.api.query._has_visible_documents", return_value=True):
        resp = client.post("/api/query/", json={"question": "What is the policy?"}, headers=guest_headers)
    assert resp.status_code == 200


def test_guest_can_list_documents(client, guest_headers):
    """Guests may list indexed documents (read-only)."""
    resp = client.get("/api/documents/", headers=guest_headers)
    assert resp.status_code == 200


def test_guest_can_upload_single_file(client, guest_headers):
    """Guests may upload a single document (one file at a time)."""
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("guest_doc.txt", b"Hello guest world", "text/plain")},
        headers=guest_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "guest_doc.txt"
    assert body["chunks_indexed"] >= 1


def test_guest_cannot_delete(client, guest_headers):
    """Delete is blocked for guests — HTTP 403."""
    resp = client.delete("/api/documents/any.txt", headers=guest_headers)
    assert resp.status_code == 403


def test_guest_settings_limited_to_once(client):
    """Guests get exactly one settings save per session (both api_key and model locked together)."""
    token = client.post("/api/auth/guest").json()["access_token"]
    hdrs = {"Authorization": f"Bearer {token}"}
    key = "sk-" + "a" * 48
    # First save (api_key + model together) succeeds
    resp1 = client.post("/api/settings/", json={"model": "gpt-4o-mini", "api_key": key}, headers=hdrs)
    assert resp1.status_code == 200
    # Second attempt — any combination — is rejected with 409
    resp2 = client.post("/api/settings/", json={"model": "gpt-4o"}, headers=hdrs)
    assert resp2.status_code == 409
    assert "session" in resp2.json()["detail"].lower()
    # API key update also blocked after first save
    resp3 = client.post("/api/settings/", json={"api_key": key}, headers=hdrs)
    assert resp3.status_code == 409


def test_guest_cannot_login_with_password(client):
    """Attempting to log in as 'guest' via username/password is rejected."""
    resp = client.post("/api/auth/login", json={"username": "guest", "password": "anything"})
    assert resp.status_code == 401


def test_token_with_unknown_username_rejected(client):
    """A validly signed JWT whose username doesn't exist must return 401."""
    from app.auth.utils import create_access_token
    token = create_access_token({"sub": "ghost_user_that_does_not_exist"})
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── Dev credentials endpoint (removed for security) ───────────────────────────
# The /api/auth/dev-credentials endpoint was removed. Credentials are shown in
# the terminal startup banner. Exposing them via HTTP — even localhost-only —
# allows any page at localhost:3000 to harvest them without CORS restrictions.

def test_dev_credentials_endpoint_removed(client):
    """Confirm the dev-credentials endpoint no longer exists."""
    resp = client.get("/api/auth/dev-credentials")
    assert resp.status_code == 404


# ── Logout / JTI revocation (S5) ─────────────────────────────────────────────

def test_logout_returns_200(client):
    """Logout uses a fresh token to avoid revoking the session-scoped auth_headers."""
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/auth/logout", headers=headers)
    assert resp.status_code == 200
    assert "Logged out" in resp.json()["message"]


def test_revoked_token_rejected_on_subsequent_request(client):
    """After logout, the same token must be rejected with 401."""
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Logout revokes the JTI
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    # Subsequent request with the same token should fail
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 401


def test_health_does_not_expose_env_in_test_mode(client):
    """In non-development mode (APP_ENV=test), 'env' field must be absent."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "env" not in body
