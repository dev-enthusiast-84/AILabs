"""Unit tests for runtime_settings_cookie — _build_token payload filtering
and restore_runtime_settings_from_token validation logic.

These tests exercise the fix that excludes ``reranker_type='none'`` from the
cookie token payload so a previously-disabled reranker cannot override the
.env default ``llm-judge`` on subsequent requests.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app.auth.models import UserInDB
from app.runtime.runtime_settings_cookie import (
    _ALLOWED_KEYS,
    _build_token,
    _fernet,
    COOKIE_MAX_AGE_SECONDS,
    restore_runtime_settings_from_token,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(
    username: str = "testuser",
    role: str = "admin",
    session_id: str | None = None,
) -> UserInDB:
    """Return a minimal UserInDB instance suitable for cookie tests."""
    return UserInDB(
        username=username,
        hashed_password="$2b$12$fakehash",
        role=role,
        session_id=session_id,
    )


def _decrypt_token(token: str) -> dict:
    """Decrypt a Fernet token produced by _build_token and return the payload."""
    raw = _fernet().decrypt(token.encode("utf-8"), ttl=COOKIE_MAX_AGE_SECONDS)
    return json.loads(raw)


# ── _build_token: reranker_type exclusion (the bug-fix) ──────────────────────

def test_build_token_excludes_reranker_type_none():
    """reranker_type='none' must NOT appear in the encrypted settings payload."""
    user = _make_user()
    token = _build_token(user=user, settings_values={"reranker_type": "none", "retriever_k": 4})
    payload = _decrypt_token(token)

    assert "reranker_type" not in payload["settings"], (
        "reranker_type='none' should be stripped to avoid overriding the .env default"
    )


def test_build_token_includes_reranker_type_llm_judge():
    """reranker_type='llm-judge' is a real selection and must survive into the payload."""
    user = _make_user()
    token = _build_token(user=user, settings_values={"reranker_type": "llm-judge"})
    payload = _decrypt_token(token)

    assert payload["settings"].get("reranker_type") == "llm-judge"


def test_build_token_includes_reranker_type_cross_encoder():
    """reranker_type='cross-encoder' is a real selection and must survive into the payload."""
    user = _make_user()
    token = _build_token(user=user, settings_values={"reranker_type": "cross-encoder"})
    payload = _decrypt_token(token)

    assert payload["settings"].get("reranker_type") == "cross-encoder"


# ── _build_token: generic filtering rules ────────────────────────────────────

def test_build_token_excludes_none_values():
    """Keys whose value is None must be omitted from the settings payload."""
    user = _make_user()
    token = _build_token(user=user, settings_values={"api_key": None, "model": "gpt-4o"})
    payload = _decrypt_token(token)

    assert "api_key" not in payload["settings"]
    assert payload["settings"].get("model") == "gpt-4o"


def test_build_token_excludes_empty_string_values():
    """Keys whose value is an empty string must be omitted from the settings payload."""
    user = _make_user()
    token = _build_token(user=user, settings_values={"api_key": "", "model": "gpt-4o-mini"})
    payload = _decrypt_token(token)

    assert "api_key" not in payload["settings"]
    assert payload["settings"].get("model") == "gpt-4o-mini"


def test_build_token_excludes_keys_not_in_allowed_keys():
    """Keys absent from _ALLOWED_KEYS must be silently dropped."""
    user = _make_user()
    token = _build_token(
        user=user,
        settings_values={
            "unknown_field": "value",
            "another_unknown": 42,
            "model": "gpt-4o",
        },
    )
    payload = _decrypt_token(token)

    assert "unknown_field" not in payload["settings"]
    assert "another_unknown" not in payload["settings"]
    assert payload["settings"].get("model") == "gpt-4o"


# ── _build_token: payload structure ──────────────────────────────────────────

def test_build_token_encodes_user_identity():
    """The token payload must carry sub, role, and session_id."""
    user = _make_user(username="alice", role="admin", session_id="sess-abc")
    token = _build_token(user=user, settings_values={})
    payload = _decrypt_token(token)

    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"
    assert payload["session_id"] == "sess-abc"


def test_build_token_session_id_none_becomes_empty_string():
    """When session_id is None the payload must store an empty string, not None."""
    user = _make_user(session_id=None)
    token = _build_token(user=user, settings_values={})
    payload = _decrypt_token(token)

    assert payload["session_id"] == ""


def test_build_token_settings_dict_is_present_when_empty():
    """Even with no valid settings, the 'settings' key must be an empty dict."""
    user = _make_user()
    token = _build_token(user=user, settings_values={})
    payload = _decrypt_token(token)

    assert isinstance(payload["settings"], dict)
    assert payload["settings"] == {}


def test_build_token_allowed_keys_pass_through():
    """A sampling of _ALLOWED_KEYS with valid values must all appear in the payload."""
    user = _make_user()
    sample = {
        "model": "gpt-4o",
        "embedding_model": "text-embedding-3-small",
        "retriever_k": 6,
        "retriever_use_mmr": True,
        "relevance_grader_enabled": False,
    }
    token = _build_token(user=user, settings_values=sample)
    payload = _decrypt_token(token)

    for key, value in sample.items():
        assert payload["settings"][key] == value


# ── restore_runtime_settings_from_token: early-exit guards ───────────────────

def test_restore_returns_false_for_none_input():
    """None raw value must return False immediately without raising."""
    user = _make_user()
    result = restore_runtime_settings_from_token(None, user)
    assert result is False


def test_restore_returns_false_for_tampered_token():
    """A token that fails Fernet decryption must return False."""
    user = _make_user()
    result = restore_runtime_settings_from_token("this-is-not-a-valid-fernet-token", user)
    assert result is False


def test_restore_returns_false_for_empty_string():
    """An empty-string raw value must return False (falsy guard)."""
    user = _make_user()
    result = restore_runtime_settings_from_token("", user)
    assert result is False


# ── restore_runtime_settings_from_token: identity mismatch ───────────────────

def test_restore_returns_false_when_username_does_not_match():
    """Token issued for 'alice' must be rejected when presented as 'bob'."""
    alice = _make_user(username="alice")
    bob = _make_user(username="bob")
    token = _build_token(user=alice, settings_values={"model": "gpt-4o"})

    result = restore_runtime_settings_from_token(token, bob)
    assert result is False


def test_restore_returns_false_when_role_does_not_match():
    """Token issued for 'admin' role must be rejected when the user's role is 'guest'."""
    admin_user = _make_user(username="testuser", role="admin")
    guest_user = _make_user(username="testuser", role="guest")
    token = _build_token(user=admin_user, settings_values={"model": "gpt-4o"})

    result = restore_runtime_settings_from_token(token, guest_user)
    assert result is False


def test_restore_returns_false_when_session_id_does_not_match():
    """Token issued with session_id 'sess-A' must be rejected when session_id is 'sess-B'."""
    user_a = _make_user(session_id="sess-A")
    user_b = _make_user(session_id="sess-B")
    token = _build_token(user=user_a, settings_values={"model": "gpt-4o"})

    result = restore_runtime_settings_from_token(token, user_b)
    assert result is False


# ── restore_runtime_settings_from_token: successful round-trip ───────────────

def test_restore_calls_set_request_runtime_settings_with_correct_values(monkeypatch):
    """A valid token must result in set_request_runtime_settings being called
    with exactly the settings that were encoded, excluding reranker_type='none'."""
    captured: list[dict] = []

    monkeypatch.setattr(
        "app.runtime.runtime_settings_cookie.set_request_runtime_settings",
        lambda d: captured.append(d),
    )

    user = _make_user(username="carol", role="admin")
    settings_in = {
        "model": "gpt-4o",
        "retriever_k": 8,
        "reranker_type": "llm-judge",
    }
    token = _build_token(user=user, settings_values=settings_in)

    result = restore_runtime_settings_from_token(token, user)

    assert result is True
    assert len(captured) == 1
    restored = captured[0]
    assert restored["model"] == "gpt-4o"
    assert restored["retriever_k"] == 8
    assert restored["reranker_type"] == "llm-judge"


def test_restore_returns_true_on_valid_token():
    """restore_runtime_settings_from_token must return True on a well-formed token."""
    user = _make_user()
    token = _build_token(user=user, settings_values={"model": "gpt-4o"})

    with patch("app.runtime.runtime_settings_cookie.set_request_runtime_settings"):
        result = restore_runtime_settings_from_token(token, user)

    assert result is True


def test_restore_does_not_pass_disallowed_keys_to_store(monkeypatch):
    """Even if the token somehow contains non-allowed keys they must be filtered
    before being forwarded to set_request_runtime_settings."""
    user = _make_user()

    # Manually craft and encrypt a payload with a rogue key
    import json
    import time
    rogue_payload = {
        "sub": user.username,
        "role": user.role,
        "session_id": user.session_id or "",
        "iat": int(time.time()),
        "settings": {
            "model": "gpt-4o",
            "__rogue__": "injected",
        },
    }
    raw_token = (
        _fernet()
        .encrypt(json.dumps(rogue_payload, separators=(",", ":")).encode("utf-8"))
        .decode("utf-8")
    )

    captured: list[dict] = []
    monkeypatch.setattr(
        "app.runtime.runtime_settings_cookie.set_request_runtime_settings",
        lambda d: captured.append(d),
    )

    result = restore_runtime_settings_from_token(raw_token, user)

    assert result is True
    assert "__rogue__" not in captured[0]
    assert captured[0].get("model") == "gpt-4o"


def test_restore_strips_none_and_empty_values_from_stored_settings(monkeypatch):
    """restore_runtime_settings_from_token must not forward None or empty-string
    values to the store, even if they appear inside the token's settings dict."""
    user = _make_user()

    import json
    import time
    payload = {
        "sub": user.username,
        "role": user.role,
        "session_id": user.session_id or "",
        "iat": int(time.time()),
        "settings": {
            "model": "gpt-4o",
            "api_key": None,
            "langchain_api_key": "",
        },
    }
    raw_token = (
        _fernet()
        .encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("utf-8")
    )

    captured: list[dict] = []
    monkeypatch.setattr(
        "app.runtime.runtime_settings_cookie.set_request_runtime_settings",
        lambda d: captured.append(d),
    )

    result = restore_runtime_settings_from_token(raw_token, user)

    assert result is True
    assert "api_key" not in captured[0]
    assert "langchain_api_key" not in captured[0]
    assert captured[0].get("model") == "gpt-4o"


# ── _ALLOWED_KEYS constant ────────────────────────────────────────────────────

def test_allowed_keys_contains_reranker_type():
    """reranker_type must remain in _ALLOWED_KEYS so non-'none' values are
    still included in the cookie (the fix is value-based, not key-based)."""
    assert "reranker_type" in _ALLOWED_KEYS


def test_allowed_keys_contains_expected_credential_fields():
    """Core credential fields must be present in _ALLOWED_KEYS."""
    for key in ("api_key", "model", "embedding_model", "langchain_api_key"):
        assert key in _ALLOWED_KEYS, f"Expected '{key}' in _ALLOWED_KEYS"


# ── COOKIE_MAX_AGE_SECONDS constant ──────────────────────────────────────────

def test_cookie_max_age_is_four_hours():
    """COOKIE_MAX_AGE_SECONDS must equal 4 hours (14 400 seconds)."""
    assert COOKIE_MAX_AGE_SECONDS == 60 * 60 * 4


# ── production-mode helpers ───────────────────────────────────────────────────

def test_same_site_returns_none_in_production(monkeypatch):
    """_same_site() returns 'none' when APP_ENV=production (line 66)."""
    from app.runtime.runtime_settings_cookie import _same_site
    import app.runtime.runtime_settings_cookie as cookie_mod
    mock_settings = type("S", (), {"app_env": "production", "secret_key": "test-secret-key-for-testing-only-32ch"})()
    monkeypatch.setattr(cookie_mod, "get_settings", lambda: mock_settings)
    assert _same_site() == "none"


def test_secure_cookie_returns_true_in_production(monkeypatch):
    """_secure_cookie() returns True when APP_ENV=production (line 70)."""
    from app.runtime.runtime_settings_cookie import _secure_cookie
    import app.runtime.runtime_settings_cookie as cookie_mod
    mock_settings = type("S", (), {"app_env": "production", "secret_key": "test-secret-key-for-testing-only-32ch"})()
    monkeypatch.setattr(cookie_mod, "get_settings", lambda: mock_settings)
    assert _secure_cookie() is True


# ── set_runtime_settings_cookie ───────────────────────────────────────────────

def test_set_runtime_settings_cookie_sets_header_and_cookie():
    """set_runtime_settings_cookie writes the token to both header and cookie (lines 96-100)."""
    from fastapi.responses import JSONResponse
    from app.runtime.runtime_settings_cookie import set_runtime_settings_cookie, HEADER_NAME, COOKIE_NAME

    response = JSONResponse(content={})
    user = _make_user(username="admin", role="admin")
    set_runtime_settings_cookie(response, user=user, settings_values={"model": "gpt-4o"})

    assert HEADER_NAME in response.headers
    cookies = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in cookies


# ── clear_runtime_settings_cookie ─────────────────────────────────────────────

def test_clear_runtime_settings_cookie_deletes_cookie():
    """clear_runtime_settings_cookie removes the cookie from the response (line 112)."""
    from fastapi.responses import JSONResponse
    from app.runtime.runtime_settings_cookie import clear_runtime_settings_cookie, COOKIE_NAME

    response = JSONResponse(content={})
    clear_runtime_settings_cookie(response)

    cookies = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in cookies
    assert 'max-age=0' in cookies.lower() or 'expires=' in cookies.lower()


# ── restore_runtime_settings_from_token: non-dict settings payload ────────────

def test_restore_returns_false_when_settings_not_dict():
    """When the 'settings' key is not a dict the function returns False (line 138)."""
    import json, time
    user = _make_user()
    payload = {
        "sub": user.username,
        "role": user.role,
        "session_id": user.session_id or "",
        "iat": int(time.time()),
        "settings": "not-a-dict",
    }
    raw_token = (
        _fernet()
        .encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("utf-8")
    )
    result = restore_runtime_settings_from_token(raw_token, user)
    assert result is False


# ── restore_runtime_settings_from_cookie ─────────────────────────────────────

def test_restore_runtime_settings_from_cookie_reads_header(monkeypatch):
    """restore_runtime_settings_from_cookie reads the X-Runtime-Settings header (lines 149-150)."""
    from app.runtime.runtime_settings_cookie import restore_runtime_settings_from_cookie, HEADER_NAME

    user = _make_user()
    token = _build_token(user=user, settings_values={"model": "gpt-4o"})

    captured = []
    monkeypatch.setattr(
        "app.runtime.runtime_settings_cookie.set_request_runtime_settings",
        lambda d: captured.append(d),
    )

    mock_request = type("R", (), {
        "headers": {HEADER_NAME: token},
        "cookies": {},
    })()
    restore_runtime_settings_from_cookie(mock_request, user)
    assert len(captured) == 1
    assert captured[0].get("model") == "gpt-4o"


def test_get_settings_view_restores_cookie_before_reporting_source(monkeypatch):
    """GET /settings must restore the encrypted cookie so api_key_source reflects the
    recovered value, not 'not_configured'.

    Regression: before this fix, get_settings_view did not accept request: Request and
    never called restore_runtime_settings_from_cookie, causing the settings modal to open
    with a spurious 'restart' warning whenever in-memory runtime settings were absent
    (e.g. after a Vercel cold start) even though the browser still held a valid cookie.
    """
    from unittest.mock import MagicMock, patch
    from app.api.settings import get_settings_view
    from app.auth.models import UserInDB
    import asyncio

    user = UserInDB(username="admin", hashed_password="x", role="admin", session_id=None)
    mock_request = MagicMock()

    restore_calls: list[tuple] = []

    def fake_restore(req, usr):
        restore_calls.append((req, usr))

    monkeypatch.setattr("app.api.settings.restore_runtime_settings_from_cookie", fake_restore)
    monkeypatch.setattr("app.api.settings.set_runtime_scope", lambda *a, **kw: None)
    monkeypatch.setattr("app.api.settings._build_response", lambda *a, **kw: MagicMock())

    asyncio.run(get_settings_view(request=mock_request, _user=user))

    assert len(restore_calls) == 1, "restore_runtime_settings_from_cookie must be called once"
    assert restore_calls[0][0] is mock_request
    assert restore_calls[0][1] is user
