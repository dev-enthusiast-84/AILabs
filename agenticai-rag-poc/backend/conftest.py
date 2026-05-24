import os
import secrets
import warnings
from unittest.mock import MagicMock, patch
import pytest

# Suppress third-party deprecation warnings that are not actionable.
# These must be registered here — in the root conftest — before any test
# module or langgraph/langchain_core module is imported.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
# LangChain/LangGraph allowed_objects change: not actionable until langgraph
# releases a version that sets the default explicitly.
warnings.filterwarnings(
    "ignore",
    message=r".*allowed_objects.*",
    category=Warning,
)
from fastapi.testclient import TestClient

# ── Live-test guard ────────────────────────────────────────────────────────────
# When LIVE_TESTS=1 the mocks are not applied so real services are exercised.
_LIVE_MODE = os.getenv("LIVE_TESTS", "0") == "1"

if not _LIVE_MODE:
    # Must be set before any app module is imported
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32ch")
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("VECTOR_STORE_TYPE", "memory")
    # Generate a fresh admin password each test session — never hardcoded in source.
    # 'TestPass' prefix keeps the pre-commit scanner's safe_pattern satisfied.
    os.environ.setdefault("ADMIN_PASSWORD", f"TestPass_{secrets.token_hex(8)}")

# ── Vector-store mock (unit/integration tests only) ────────────────────────────
_mock_store = MagicMock()
_mock_store.add_documents.return_value = ["id-1", "id-2"]
_mock_store.similarity_search.return_value = []
_mock_store._collection.get.return_value = {"metadatas": [], "ids": []}

_vs_patch = patch("app.rag.vector_store.get_vector_store", return_value=_mock_store)


def pytest_sessionstart(session):
    if not _LIVE_MODE:
        mock_gvs = _vs_patch.start()
        # Explicitly attach cache_clear so that test-level patches of this attribute
        # can restore it correctly (patch with create=True deletes it on stop otherwise).
        mock_gvs.cache_clear = MagicMock()


def pytest_sessionfinish(session, exitstatus):
    if not _LIVE_MODE:
        _vs_patch.stop()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_auth_rate_limiter():
    """Reset the auth rate-limiter storage before and after every test.

    The auth limiter uses a module-level Limiter instance. Without this reset,
    rate-limit counts from inline /api/auth/guest calls bleed across tests and
    exhaust the 10/minute budget before session-scoped fixtures can run.
    """
    from app.auth.router import limiter
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client):
    """Session-scoped: login once per test run to avoid hitting rate limit."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": os.environ["ADMIN_PASSWORD"]})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def guest_headers(client):
    """Session-scoped: get guest token once per run to avoid hitting rate limit."""
    resp = client.post("/api/auth/guest")
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def sample_txt_file():
    content = b"Acme Corp remote work policy: Employees may work from home up to 3 days per week."
    return ("sample.txt", content, "text/plain")


@pytest.fixture
def sample_csv_file():
    content = b"name,department,salary\nAlice,Engineering,95000\nBob,Marketing,75000\n"
    return ("sample.csv", content, "text/csv")
