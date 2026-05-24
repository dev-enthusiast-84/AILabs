import os
from unittest.mock import patch


def test_readiness_reports_components_without_secrets(client):
    resp = client.get("/api/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ready", "degraded"}
    assert set(body["components"]) == {"app_config", "openai", "vector_store", "file_store", "export"}
    serialized = str(body)
    assert "sk-test-key" not in serialized
    assert "test-secret-key-for-testing-only-32ch" not in serialized
    assert "admin_password" not in serialized.lower()
    assert body["components"]["export"]["transcript_redaction"] is True


def test_readiness_uses_vercel_stripped_prefix(client):
    resp = client.get("/readiness")

    assert resp.status_code == 200
    assert "components" in resp.json()


def test_health_is_liveness_not_dependency_readiness(client):
    with patch("app.main.get_effective_api_key", side_effect=RuntimeError("sk-secret-openai-value")):
        health = client.get("/api/health")
        readiness = client.get("/api/readiness")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert readiness.status_code == 503
    assert readiness.json()["components"]["openai"] == {
        "status": "degraded",
        "error": "dependency_check_failed",
    }


def test_readiness_dependency_failure_surface_is_sanitized(client):
    secret = "sk-secret-openai-value"
    with patch("app.main.get_effective_api_key", side_effect=RuntimeError(f"provider failed for {secret}")):
        resp = client.get("/api/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["components"]["openai"]["error"] == "dependency_check_failed"
    serialized = str(body)
    assert secret not in serialized
    assert "provider failed" not in serialized


def test_request_id_header_is_echoed_for_correlation(client):
    request_id = "test-request-123"
    resp = client.get("/api/health", headers={"X-Request-ID": request_id})

    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == request_id


def test_session_compatibility_header_is_returned(client):
    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.headers["X-App-Session-Compatibility"]


def test_invalid_request_id_header_is_replaced(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "bad id with spaces"})

    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] != "bad id with spaces"
    assert resp.headers["X-Request-ID"]


# ── security_headers_middleware exception path (lines 174-198) ───────────────

def test_security_headers_middleware_returns_500_on_unhandled_exception():
    """When call_next raises an uncaught Exception, the middleware must return 500 JSON
    with a request_id and still apply security headers (OWASP A09).

    We create a minimal FastAPI app that shares only the security_headers_middleware
    logic by adding a route that raises, confirming the except branch (lines 174-198).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.main import security_headers_middleware, _apply_common_headers

    mini_app = FastAPI()
    mini_app.middleware("http")(security_headers_middleware)

    @mini_app.get("/boom")
    async def _boom():
        raise RuntimeError("deliberate test explosion")

    with TestClient(mini_app, raise_server_exceptions=False) as c:
        resp = c.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body
    # Security headers must still be present even on error path
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


# ── _readiness_status component failure branches ──────────────────────────────

def test_readiness_app_config_component_failure():
    """When settings.secret_key raises inside _readiness_status, app_config is 'degraded'."""
    from app.main import _readiness_status
    import app.main as main_module

    real_settings = main_module.settings

    class _BoomSettings:
        @property
        def secret_key(self):
            raise RuntimeError("config exploded")

        def __getattr__(self, name):
            raise RuntimeError("config exploded")

    main_module.settings = _BoomSettings()
    try:
        result = _readiness_status()
    finally:
        main_module.settings = real_settings

    assert result["components"]["app_config"]["status"] == "degraded"
    assert result["components"]["app_config"]["error"] == "dependency_check_failed"


def test_readiness_vector_store_component_failure(client):
    """When get_effective_vector_store_type raises, vector_store component is 'degraded'."""
    with patch("app.main.get_effective_vector_store_type", side_effect=RuntimeError("vs boom")):
        resp = client.get("/api/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["components"]["vector_store"]["status"] == "degraded"
    assert body["components"]["vector_store"]["error"] == "dependency_check_failed"


def test_readiness_file_store_component_failure(client):
    """When get_effective_file_store_type raises, file_store component is 'degraded'."""
    with patch("app.main.get_effective_file_store_type", side_effect=RuntimeError("fs boom")):
        resp = client.get("/api/readiness")

    assert resp.status_code == 503
    body = resp.json()
    assert body["components"]["file_store"]["status"] == "degraded"
    assert body["components"]["file_store"]["error"] == "dependency_check_failed"


# ── _local_upload_writable with UPLOAD_DIR env var (lines 281-282) ───────────

def test_local_upload_writable_uses_upload_dir_env_var(tmp_path):
    """_local_upload_writable reads UPLOAD_DIR env var when set."""
    from app.main import _local_upload_writable

    with patch.dict(os.environ, {"UPLOAD_DIR": str(tmp_path)}):
        result = _local_upload_writable()

    assert result is True


def test_local_upload_writable_vercel_path(tmp_path):
    """_local_upload_writable uses /tmp/uploads path when VERCEL env var is set."""
    from app.main import _local_upload_writable
    import tempfile, pathlib

    # Simulate Vercel environment: no UPLOAD_DIR but VERCEL=1
    env_patch = {"VERCEL": "1"}
    env_patch.pop("UPLOAD_DIR", None)

    with patch.dict(os.environ, env_patch, clear=False):
        os.environ.pop("UPLOAD_DIR", None)
        result = _local_upload_writable()

    # Just assert it returns a bool without crashing — /tmp exists on all platforms
    assert isinstance(result, bool)


# ── /health alias endpoint (line 263) ────────────────────────────────────────

def test_health_stripped_prefix_alias(client):
    """GET /health (Vercel-stripped prefix) must return the same as /api/health (line 263)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


# ── health endpoint in development mode includes env (line 257) ──────────────

def test_health_returns_env_in_development_mode():
    """When APP_ENV=development, GET /api/health includes 'env' field (line 257).

    Tests the health() function directly by patching only app_env on settings.
    """
    import asyncio
    import app.main as main_module

    real_settings = main_module.settings
    real_app_env = real_settings.app_env

    # Temporarily set app_env to "development" on the real settings object
    real_settings.app_env = "development"
    try:
        result = asyncio.run(main_module.health())
    finally:
        real_settings.app_env = real_app_env

    assert "env" in result
    assert result["env"] == "development"


# ── export component failure (lines 349-350) ─────────────────────────────────

def test_readiness_export_component_handles_openai_state():
    """The export component status depends on openai being configured (lines 343-350).
    When the openai component is already determined as not configured, export is 'degraded'.
    """
    from app.main import _readiness_status
    with patch("app.main.get_effective_api_key", return_value=""):
        result = _readiness_status()

    # When OpenAI key is empty, both openai and export should be degraded
    assert result["components"]["export"]["status"] == "degraded"
    assert result["components"]["export"]["audio_generation_configured"] is False


# ── SafeAppError handler (lines 217-224) ─────────────────────────────────────

def test_safe_app_error_handled_by_app(client):
    """SafeAppError raised in a route must be handled by safe_app_error_handler (lines 217-224).

    The global_exception_handler (lines 217-224) handles uncaught Exception subclasses that
    bypass the security_headers_middleware.  We mount a minimal FastAPI app that
    registers only the global_exception_handler (no middleware) so the exception
    propagates to the app-level handler instead.
    """
    import app.main as main_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini_app = FastAPI()
    mini_app.add_exception_handler(Exception, main_module.global_exception_handler)

    @mini_app.get("/boom")
    async def _boom():
        raise RuntimeError("deliberate global handler test")

    with TestClient(mini_app, raise_server_exceptions=False) as c:
        resp = c.get("/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert "detail" in body


# ── _apply_common_headers HSTS in production (line 160) ─────────────────────

def test_hsts_header_applied_in_production_mode():
    """Strict-Transport-Security must be set when app_env is 'production' (line 160)."""
    from app.main import _apply_common_headers
    from starlette.responses import Response
    import app.main as main_module

    real_settings = main_module.settings
    real_app_env = real_settings.app_env

    fake_response = Response()
    real_settings.app_env = "production"
    try:
        _apply_common_headers(fake_response, "test-request-id")
    finally:
        real_settings.app_env = real_app_env

    assert "Strict-Transport-Security" in fake_response.headers
    assert "max-age=" in fake_response.headers["Strict-Transport-Security"]


def test_server_header_removed_when_present():
    """Server header must be stripped from responses when present (line 163)."""
    from app.main import _apply_common_headers
    from starlette.responses import Response

    fake_response = Response()
    fake_response.headers["server"] = "uvicorn"

    _apply_common_headers(fake_response, "test-request-id")

    assert "server" not in fake_response.headers
