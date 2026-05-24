"""Production browser/deployment security header checks."""
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _parse_csp(value: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for raw_part in value.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        name, *tokens = part.split()
        directives[name] = tokens
    return directives


def _headers_for(path: Path, source: str) -> dict[str, str]:
    config = json.loads(path.read_text())
    for rule in config["headers"]:
        if rule["source"] == source:
            return {header["key"].lower(): header["value"] for header in rule["headers"]}
    raise AssertionError(f"{path} does not define headers for {source}")


def test_backend_security_headers_are_minimal_for_api(client):
    resp = client.get("/api/health")

    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"
    assert resp.headers["x-request-id"]

    csp = _parse_csp(resp.headers["content-security-policy"])
    assert csp["default-src"] == ["'none'"]
    assert csp["base-uri"] == ["'none'"]
    assert csp["frame-ancestors"] == ["'none'"]
    assert csp["form-action"] == ["'none'"]
    assert csp["object-src"] == ["'none'"]


def test_backend_adds_hsts_only_for_production(client, monkeypatch):
    from app import main as app_main

    test_resp = client.get("/api/health")
    assert "strict-transport-security" not in test_resp.headers

    monkeypatch.setattr(app_main.settings, "app_env", "production")
    prod_resp = client.get("/api/health")

    assert prod_resp.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_vercel_production_headers_cover_browser_features():
    for relative_path in ("vercel.json", "frontend/vercel.json"):
        headers = _headers_for(REPO_ROOT / relative_path, "/(.*)")

        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert headers["strict-transport-security"] == "max-age=63072000; includeSubDomains; preload"
        assert headers["permissions-policy"] == "geolocation=(), microphone=(self), camera=()"

        csp = _parse_csp(headers["content-security-policy"])
        assert csp["default-src"] == ["'self'"]
        assert csp["base-uri"] == ["'self'"]
        assert csp["script-src"] == ["'self'"]
        assert "'unsafe-inline'" not in csp["script-src"]
        assert "'unsafe-eval'" not in csp["script-src"]
        assert csp["connect-src"] == ["'self'"]
        assert csp["frame-src"] == ["'self'", "blob:"]
        assert csp["object-src"] == ["'none'"]
        assert csp["frame-ancestors"] == ["'none'"]
        assert csp["form-action"] == ["'self'"]
        assert csp["media-src"] == ["'self'", "blob:"]
        assert csp["worker-src"] == ["'self'", "blob:"]
        assert "upgrade-insecure-requests" in csp


def test_frontend_vercel_keeps_immutable_asset_caching():
    headers = _headers_for(REPO_ROOT / "frontend/vercel.json", "/assets/(.*)")

    assert headers["cache-control"] == "public, max-age=31536000, immutable"
