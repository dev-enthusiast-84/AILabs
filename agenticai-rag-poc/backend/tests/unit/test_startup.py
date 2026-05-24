"""Unit tests for the startup credential banner and secret-key guard."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from app.main import _INSECURE_SECRET, _WEAK_SECRETS, _print_startup_banner, lifespan


def _mock_settings(app_env: str, username: str = "admin", password: str = "S3cr3t!xYz") -> MagicMock:
    s = MagicMock()
    s.app_env = app_env
    s.admin_username = username
    s.admin_password = password
    return s


def test_banner_shows_credentials_in_development(capsys):
    _print_startup_banner(_mock_settings("development"))
    out = capsys.readouterr().out
    assert "admin" in out
    assert "S3cr3t!xYz" in out


def test_banner_suppressed_in_production(capsys):
    """Credentials must NOT appear in production logs (OWASP A09)."""
    _print_startup_banner(_mock_settings("production", password="ProdP@ss99"))
    out = capsys.readouterr().out
    assert out == ""
    assert "ProdP@ss99" not in out


def test_banner_suppressed_in_test_mode(capsys):
    _print_startup_banner(_mock_settings("test"))
    out = capsys.readouterr().out
    assert out == ""


def test_banner_includes_docs_url(capsys):
    _print_startup_banner(_mock_settings("development"))
    out = capsys.readouterr().out
    assert "api/docs" in out
    assert "api/health" in out


def test_banner_includes_env_file_reminder(capsys):
    _print_startup_banner(_mock_settings("development"))
    out = capsys.readouterr().out
    assert "backend/.env" in out


# ── _WEAK_SECRETS guard ────────────────────────────────────────────────────────

def _make_lifespan_settings(secret_key: str, app_env: str) -> MagicMock:
    s = MagicMock()
    s.secret_key = secret_key
    s.app_env = app_env
    s.langchain_tracing_v2 = False
    s.admin_username = "admin"
    s.admin_password = "test-only"
    return s


async def _run_lifespan(mock_settings) -> None:
    app = FastAPI()
    with patch("app.main.settings", mock_settings):
        async with lifespan(app):
            pass


def test_weak_secrets_contains_empty_string():
    assert "" in _WEAK_SECRETS


def test_weak_secrets_contains_insecure_default():
    assert _INSECURE_SECRET in _WEAK_SECRETS


def test_lifespan_raises_for_empty_secret_in_production():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        asyncio.run(_run_lifespan(_make_lifespan_settings("", "production")))


def test_lifespan_raises_for_insecure_default_in_production():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        asyncio.run(_run_lifespan(_make_lifespan_settings(_INSECURE_SECRET, "production")))


def test_lifespan_does_not_raise_for_empty_secret_in_development():
    """Dev mode must not crash on a weak key — only logs a warning."""
    asyncio.run(_run_lifespan(_make_lifespan_settings("", "development")))


def test_lifespan_strong_secret_does_not_raise():
    asyncio.run(_run_lifespan(_make_lifespan_settings("a" * 32, "production")))


# ── LangSmith tracing env-var branch (lines 90-95) ───────────────────────────

def _make_lifespan_settings_with_langsmith(
    secret_key: str,
    app_env: str,
    tracing: bool = True,
    api_key: str = "ls__testkey",
    project: str = "test-project",
) -> MagicMock:
    s = MagicMock()
    s.secret_key = secret_key
    s.app_env = app_env
    s.langchain_tracing_v2 = tracing
    s.langchain_api_key = api_key
    s.langchain_project = project
    s.admin_username = "admin"
    s.admin_password = "test-only"
    return s


def test_lifespan_sets_langchain_env_vars_in_development():
    """When app_env != 'production', langchain_tracing_v2=True, and langchain_api_key set,
    LANGCHAIN_TRACING_V2 and LANGCHAIN_PROJECT env vars are set during lifespan startup."""
    import os

    mock_settings = _make_lifespan_settings_with_langsmith(
        secret_key="a" * 32,
        app_env="development",
        tracing=True,
        api_key="ls__testkey1234",
        project="my-test-project",
    )

    # Clear any pre-existing values so we can detect the write
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    os.environ.pop("LANGCHAIN_PROJECT", None)

    asyncio.run(_run_lifespan(mock_settings))

    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_PROJECT") == "my-test-project"

    # Clean up
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    os.environ.pop("LANGCHAIN_PROJECT", None)


def test_lifespan_does_not_set_langchain_env_vars_when_tracing_false():
    """LANGCHAIN_TRACING_V2 must NOT be set when langchain_tracing_v2 is False."""
    import os

    mock_settings = _make_lifespan_settings_with_langsmith(
        secret_key="a" * 32,
        app_env="development",
        tracing=False,
        api_key="ls__testkey1234",
        project="my-test-project",
    )

    os.environ.pop("LANGCHAIN_TRACING_V2", None)

    asyncio.run(_run_lifespan(mock_settings))

    # Should NOT have been set
    assert os.environ.get("LANGCHAIN_TRACING_V2") is None


def test_lifespan_does_not_set_langchain_env_vars_in_production():
    """LANGCHAIN_TRACING_V2 must NOT be set from startup when app_env is 'production'."""
    import os

    mock_settings = _make_lifespan_settings_with_langsmith(
        secret_key="a" * 32,
        app_env="production",
        tracing=True,
        api_key="ls__testkey1234",
        project="my-test-project",
    )

    os.environ.pop("LANGCHAIN_TRACING_V2", None)

    asyncio.run(_run_lifespan(mock_settings))

    assert os.environ.get("LANGCHAIN_TRACING_V2") is None
