"""Unit tests for the guest upload rate-limit key function in documents.py."""
import os
from unittest.mock import MagicMock

import pytest
from jose import jwt

# Must set env vars before importing app modules
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32ch")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass@99!")


def _make_request(token: str | None = None, ip: str = "1.2.3.4") -> MagicMock:
    req = MagicMock()
    req.client.host = ip
    req.headers = {"Authorization": f"Bearer {token}"} if token else {}
    return req


def _make_token(role: str) -> str:
    from app.config import get_settings
    s = get_settings()
    return jwt.encode({"sub": role, "role": role}, s.secret_key, algorithm=s.algorithm)


def test_guest_key_is_remote_address():
    from app.api.documents import _guest_upload_key
    token = _make_token("guest")
    key = _guest_upload_key(_make_request(token))
    assert key == "1.2.3.4"


def test_admin_key_is_unique_per_request():
    """Admin gets a UUID key per request so each request has its own fresh bucket."""
    from app.api.documents import _guest_upload_key
    token = _make_token("admin")
    key1 = _guest_upload_key(_make_request(token))
    key2 = _guest_upload_key(_make_request(token))
    assert key1.startswith("admin-exempt-")
    assert key2.startswith("admin-exempt-")
    assert key1 != key2  # unique per request


def test_no_token_key_is_remote_address():
    from app.api.documents import _guest_upload_key
    key = _guest_upload_key(_make_request(None))
    assert key == "1.2.3.4"


def test_invalid_token_key_falls_back_to_ip():
    from app.api.documents import _guest_upload_key
    key = _guest_upload_key(_make_request("not-a-valid-jwt"))
    assert key == "1.2.3.4"


def test_malformed_bearer_key_falls_back_to_ip():
    from app.api.documents import _guest_upload_key
    req = _make_request()
    req.headers = {"Authorization": "Bearer "}
    key = _guest_upload_key(req)
    assert key == "1.2.3.4"


def test_different_ips_get_different_keys():
    from app.api.documents import _guest_upload_key
    token = _make_token("guest")
    key_a = _guest_upload_key(_make_request(token, ip="10.0.0.1"))
    key_b = _guest_upload_key(_make_request(token, ip="10.0.0.2"))
    assert key_a != key_b


def test_admin_keys_always_start_with_exempt_prefix():
    """Admin keys always start with 'admin-exempt-' regardless of IP."""
    from app.api.documents import _guest_upload_key
    token = _make_token("admin")
    key_a = _guest_upload_key(_make_request(token, ip="10.0.0.1"))
    key_b = _guest_upload_key(_make_request(token, ip="10.0.0.2"))
    assert key_a.startswith("admin-exempt-")
    assert key_b.startswith("admin-exempt-")
