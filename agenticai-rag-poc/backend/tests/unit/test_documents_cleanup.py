"""Unit tests for document cleanup API endpoints.

Covers:
- T012: POST /api/documents/cleanup (CleanupResult schema, auth, rate-limit)
- T020: POST /api/documents/cleanup with force=True sets force_mode=True
"""
import datetime
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Function-scoped TestClient so each test gets a clean limiter state."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def admin_token(client):
    """Obtain an admin JWT using the session-level ADMIN_PASSWORD env var."""
    pwd = os.environ.get("ADMIN_PASSWORD", "")
    if not pwd:
        pytest.skip("ADMIN_PASSWORD not set")
    res = client.post("/api/auth/login", json={"username": "admin", "password": pwd})
    if res.status_code != 200:
        pytest.skip("Admin login failed — credentials not configured for test")
    return res.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def guest_headers(client):
    res = client.post("/api/auth/guest")
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _make_cleanup_result(force: bool = False) -> "CleanupResult":  # type: ignore[name-defined]
    from app.rag.cleanup import CleanupResult
    return CleanupResult(
        trigger="manual",
        scope="admin",
        force_mode=force,
        deleted_count=1 if not force else 3,
        eligible_count=1 if not force else 3,
        cadence="monthly" if not force else None,
        retention_hours=720 if not force else None,
        deleted_sources=["file.txt"] if not force else ["a.txt", "b.txt", "c.txt"],
        errors=[],
        ran_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


class TestCleanupEndpoints:
    """Tests for POST /api/documents/cleanup and GET /api/documents/cleanup/status."""

    # ── POST /api/documents/cleanup ─────────────────────────────────────────────

    @patch("app.rag.cleanup.CleanupService")
    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_post_cleanup_returns_cleanup_result(
        self, mock_restore, mock_service_class, client, admin_headers
    ):
        mock_service_class.return_value.sweep_admin.return_value = _make_cleanup_result()

        res = client.post("/api/documents/cleanup", json={"force": False}, headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["trigger"] == "manual"
        assert data["scope"] == "admin"
        assert data["force_mode"] is False
        assert data["deleted_count"] == 1
        assert "ran_at" in data

    def test_cleanup_requires_auth(self, client):
        """No token → 401."""
        res = client.post("/api/documents/cleanup", json={"force": False})
        assert res.status_code in (401, 403)

    def test_cleanup_guest_gets_403(self, client, guest_headers):
        """Guest JWT → 403 (require_full_access blocks guests)."""
        res = client.post("/api/documents/cleanup", json={"force": False}, headers=guest_headers)
        assert res.status_code == 403

    @patch("app.rag.cleanup.CleanupService")
    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_force_false_calls_sweep_admin_with_force_false(
        self, mock_restore, mock_service_class, client, admin_headers
    ):
        mock_svc = mock_service_class.return_value
        mock_svc.sweep_admin.return_value = _make_cleanup_result(force=False)

        client.post("/api/documents/cleanup", json={"force": False}, headers=admin_headers)
        mock_svc.sweep_admin.assert_called_once_with(force=False)

    # ── T020: force=True ───────────────────────────────────────────────────────

    @patch("app.rag.cleanup.CleanupService")
    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_force_true_sets_force_mode_in_response(
        self, mock_restore, mock_service_class, client, admin_headers
    ):
        mock_service_class.return_value.sweep_admin.return_value = _make_cleanup_result(force=True)

        res = client.post("/api/documents/cleanup", json={"force": True}, headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["force_mode"] is True
        assert data["retention_hours"] is None
        assert data["cadence"] is None

    @patch("app.rag.cleanup.CleanupService")
    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_force_true_calls_sweep_admin_with_force_true(
        self, mock_restore, mock_service_class, client, admin_headers
    ):
        mock_svc = mock_service_class.return_value
        mock_svc.sweep_admin.return_value = _make_cleanup_result(force=True)

        client.post("/api/documents/cleanup", json={"force": True}, headers=admin_headers)
        mock_svc.sweep_admin.assert_called_once_with(force=True)

    # ── GET /api/documents/cleanup/status ─────────────────────────────────────

    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_status_returns_no_result_initially(self, mock_restore, client, admin_headers):
        """Before any cleanup, _last_cleanup_result is None → has_result=False."""
        import app.rag.cleanup as cleanup_mod
        original = cleanup_mod._last_cleanup_result
        cleanup_mod._last_cleanup_result = None
        try:
            res = client.get("/api/documents/cleanup/status", headers=admin_headers)
            assert res.status_code == 200
            data = res.json()
            assert "has_result" in data
            assert data["has_result"] is False
        finally:
            cleanup_mod._last_cleanup_result = original

    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_status_returns_result_after_cleanup(self, mock_restore, client, admin_headers):
        """After setting _last_cleanup_result, status returns has_result=True."""
        import app.rag.cleanup as cleanup_mod
        original = cleanup_mod._last_cleanup_result
        mock_result = _make_cleanup_result()
        cleanup_mod._last_cleanup_result = mock_result
        try:
            res = client.get("/api/documents/cleanup/status", headers=admin_headers)
            assert res.status_code == 200
            data = res.json()
            assert data["has_result"] is True
            assert data["result"]["trigger"] == "manual"
        finally:
            cleanup_mod._last_cleanup_result = original

    def test_status_requires_admin(self, client, guest_headers):
        """Guest JWT → 403."""
        res = client.get("/api/documents/cleanup/status", headers=guest_headers)
        assert res.status_code == 403

    # ── Rate limiting ─────────────────────────────────────────────────────────

    @patch("app.rag.cleanup.CleanupService")
    @patch("app.runtime.runtime_settings_cookie.restore_runtime_settings_from_cookie")
    def test_cleanup_rate_limited_at_third_call(
        self, mock_restore, mock_service_class, client, admin_token
    ):
        """The cleanup endpoint is rate-limited to 2/minute; 3rd call → 429."""
        from app.auth.router import limiter
        limiter._storage.reset()

        mock_service_class.return_value.sweep_admin.return_value = _make_cleanup_result()
        headers = {"Authorization": f"Bearer {admin_token}"}

        r1 = client.post("/api/documents/cleanup", json={"force": False}, headers=headers)
        r2 = client.post("/api/documents/cleanup", json={"force": False}, headers=headers)
        r3 = client.post("/api/documents/cleanup", json={"force": False}, headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429

        limiter._storage.reset()
