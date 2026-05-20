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
