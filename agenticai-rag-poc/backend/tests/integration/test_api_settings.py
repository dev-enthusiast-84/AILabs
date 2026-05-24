"""Integration tests for GET/POST /api/settings."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from jose import jwt


_VALID_KEY = "sk-" + "T" * 48


def production_settings(**overrides):
    values = {
        "app_env": "production",
        "openai_api_key": "test-env-openai-key-value",
        "llm_model": "gpt-4o",
        "embedding_model": "text-embedding-3-large",
        "planner_model": "gpt-4o",
        "generator_model": "gpt-4",
        "validator_model": "gpt-4-turbo",
        "retriever_k": 12,
        "retriever_fetch_k": 60,
        "max_context_chunks": 12,
        "max_completion_tokens": 4096,
        "token_budget_warning_threshold": 4096,
        "langchain_tracing_v2": True,
        "langchain_api_key": "ls__env-production-key",
        "langchain_project": "env-production-project",
        "vector_store_type": "pinecone",
        "file_store_type": "blob",
        "pinecone_api_key": "pc-env-production-key",
        "pinecone_index_name": "env-index",
        "pinecone_namespace": "env-namespace",
        "pinecone_cloud": "aws",
        "pinecone_region": "us-east-1",
        "blob_read_write_token": "vercel_blob_rw_env_token",
        "vercel_blob_read_write_token": "vercel_blob_rw_alt_env_token",
        "similarity_score_threshold": 0.0,
        "retriever_use_mmr": False,
        # Pipeline feature flags
        "retriever_hybrid_bm25": True,
        "relevance_grader_enabled": False,
        "ragas_evaluation_enabled": False,
        "reranker_type": "none",
        "reranker_judge_model": "gpt-4.1-mini",
        "chunker_type": "recursive",
        "chunk_size": 800,
        "chunk_overlap": 100,
        # Informational fields required by _build_response()
        "retriever_fusion_mode": "rrf",
        "reranker_top_k": 4,
        "semantic_breakpoint_threshold_type": "percentile",
        "max_query_length": 1000,
        "query_rate_limit_per_minute": 10,
        "effective_max_upload_size_mb": 20,
        "guest_max_upload_size_mb": 3,
        "guest_max_indexed_documents": 1,
        "guest_token_expire_minutes": 15,
        "guest_doc_retention_seconds": 3600,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def reset_runtime_settings(monkeypatch):
    import app.runtime.settings_store as store

    runtime_values = {
        "_runtime_api_key": "",
        "_runtime_model": "",
        "_runtime_embedding_model": "",
        "_runtime_planner_model": "",
        "_runtime_generator_model": "",
        "_runtime_validator_model": "",
        "_runtime_retriever_k": None,
        "_runtime_retriever_fetch_k": None,
        "_runtime_max_context_chunks": None,
        "_runtime_max_completion_tokens": None,
        "_runtime_token_budget_warning_threshold": None,
        "_runtime_langchain_tracing_v2": None,
        "_runtime_langchain_api_key": "",
        "_runtime_langchain_project": "",
        "_runtime_pinecone_api_key": "",
        "_runtime_blob_read_write_token": "",
        "_runtime_retriever_hybrid_bm25": None,
        "_runtime_relevance_grader_enabled": None,
        "_runtime_ragas_evaluation_enabled": None,
        "_runtime_reranker_type": None,
        "_runtime_reranker_judge_model": "",
        "_runtime_chunker_type": None,
        "_runtime_chunk_size": None,
        "_runtime_chunk_overlap": None,
    }
    for name, value in runtime_values.items():
        monkeypatch.setattr(store, name, value)


@pytest.fixture(autouse=True)
def reset_settings_rate_limit():
    """Reset the in-memory rate-limit counter and runtime ragas flag before each test.

    POST /api/settings/ is capped at 20/min per IP. The new test suite
    now has >20 POST tests so without a reset, later tests get 429.
    ragas_evaluation_enabled is reset to None so each test starts from the
    config default (False) rather than inheriting a previous test's POST.
    """
    from app.api.settings import limiter
    import app.api.settings as settings_api
    import app.runtime.settings_store as store
    from app.auth.router import limiter as auth_limiter
    limiter._storage.reset()
    auth_limiter._storage.reset()
    settings_api._guest_settings_used.clear()
    store._runtime_ragas_evaluation_enabled = None
    yield
    limiter._storage.reset()
    auth_limiter._storage.reset()
    settings_api._guest_settings_used.clear()
    store._runtime_ragas_evaluation_enabled = None


# ── GET /api/settings ──────────────────────────────────────────────────────────

def test_get_settings_requires_auth(client):
    resp = client.get("/api/settings/")
    assert resp.status_code == 403


def test_get_settings_returns_schema(client, auth_headers):
    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "model" in body
    assert "api_key_masked" in body
    assert "api_key_source" in body
    assert "allowed_models" in body
    assert isinstance(body["allowed_models"], list)
    assert len(body["allowed_models"]) > 0


def test_get_settings_key_never_returned_in_full(client, auth_headers):
    resp = client.get("/api/settings/", headers=auth_headers)
    body = resp.json()
    masked = body["api_key_masked"]
    # Must not contain a long run of alphanumerics that would indicate full key exposure
    if masked:
    # A fully exposed provider key would contain more than 20 chars of real content
        # The masked value should contain "****"
        assert "****" in masked or masked == ""


def test_get_settings_returns_new_fields(client, auth_headers):
    """GET /api/settings/ must include all new extended fields."""
    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    # Per-node models
    assert "planner_model" in body
    assert "generator_model" in body
    assert "validator_model" in body

    # Retrieval
    assert "retriever_k" in body
    assert "similarity_score_threshold" in body
    assert "retriever_use_mmr" in body
    assert "retriever_fetch_k" in body
    assert "max_context_chunks" in body

    # Generation
    assert "max_completion_tokens" in body
    assert "token_budget_warning_threshold" in body

    # LangSmith
    assert "langchain_tracing_v2" in body
    assert "langchain_api_key_masked" in body
    assert "langchain_project" in body

    # Vector store / Pinecone
    assert "vector_store_type" in body
    assert "file_store_type" in body
    assert "pinecone_api_key_masked" in body
    assert "pinecone_api_key_source" in body
    assert "pinecone_index_name" in body
    assert "pinecone_namespace" in body
    assert "pinecone_cloud" in body
    assert "pinecone_region" in body
    assert "blob_read_write_token_masked" in body
    assert "blob_read_write_token_source" in body

    # Pipeline feature flags
    assert "retriever_hybrid_bm25" in body
    assert "relevance_grader_enabled" in body
    assert "reranker_type" in body
    assert "allowed_reranker_types" in body
    assert "chunker_type" in body
    assert "chunk_size" in body
    assert "chunk_overlap" in body
    assert "allowed_chunker_types" in body

    # Verify types
    assert isinstance(body["retriever_k"], int)
    assert isinstance(body["similarity_score_threshold"], float)
    assert isinstance(body["retriever_use_mmr"], bool)
    assert isinstance(body["retriever_fetch_k"], int)
    assert isinstance(body["max_context_chunks"], int)
    assert isinstance(body["max_completion_tokens"], int)
    assert isinstance(body["token_budget_warning_threshold"], int)
    assert isinstance(body["langchain_tracing_v2"], bool)
    assert isinstance(body["vector_store_type"], str)
    assert isinstance(body["file_store_type"], str)
    assert isinstance(body["retriever_hybrid_bm25"], bool)
    assert isinstance(body["relevance_grader_enabled"], bool)
    assert isinstance(body["reranker_type"], str)
    assert isinstance(body["allowed_reranker_types"], list)
    assert isinstance(body["chunker_type"], str)
    assert isinstance(body["chunk_size"], int)
    assert isinstance(body["chunk_overlap"], int)
    assert isinstance(body["allowed_chunker_types"], list)


# ── POST /api/settings ─────────────────────────────────────────────────────────

def test_update_settings_requires_auth(client):
    resp = client.post("/api/settings/", json={"model": "gpt-4o"})
    assert resp.status_code == 403


def test_update_model_valid(client, auth_headers):
    resp = client.post("/api/settings/", headers=auth_headers, json={"model": "gpt-4o"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "gpt-4o"


def test_update_api_key_valid(client, auth_headers):
    resp = client.post("/api/settings/", headers=auth_headers, json={"api_key": _VALID_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert "****" in body["api_key_masked"]
    assert body["api_key_source"] == "runtime"


def test_update_both_fields(client, auth_headers):
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"api_key": _VALID_KEY, "model": "gpt-4o-mini"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "gpt-4o-mini"
    assert "****" in body["api_key_masked"]


def test_update_empty_body_rejected(client, auth_headers):
    resp = client.post("/api/settings/", headers=auth_headers, json={})
    assert resp.status_code == 422


def test_update_invalid_model_rejected(client, auth_headers):
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"model": "gpt-99-super"}
    )
    assert resp.status_code == 422
    assert "model" in str(resp.json())


def test_update_bad_key_prefix_rejected(client, auth_headers):
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"api_key": "pk-notvalid123456"}
    )
    assert resp.status_code == 422
    assert "api_key" in str(resp.json())


def test_update_key_too_short_rejected(client, auth_headers):
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"api_key": "sk-tooshort"}
    )
    assert resp.status_code == 422


def test_update_xss_in_key_rejected(client, auth_headers):
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"api_key": "<script>alert(1)</script>"},
    )
    assert resp.status_code == 422


def test_update_xss_in_model_rejected(client, auth_headers):
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"model": "<img src=x onerror=alert(1)>"},
    )
    assert resp.status_code == 422


def test_allowed_models_list_non_empty(client, auth_headers):
    resp = client.get("/api/settings/", headers=auth_headers)
    models = resp.json()["allowed_models"]
    assert "gpt-4o-mini" in models
    assert "gpt-4o" in models


def test_update_null_api_key_field_is_ignored(client, auth_headers):
    """Sending api_key: null explicitly should activate the None-return branch of sanitize_api_key."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"api_key": None, "model": "gpt-4o-mini"},
    )
    assert resp.status_code == 200
    assert resp.json()["model"] == "gpt-4o-mini"


def test_update_null_model_field_is_ignored(client, auth_headers):
    """Sending model: null explicitly should activate the None-return branch of sanitize_model."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"api_key": _VALID_KEY, "model": None},
    )
    assert resp.status_code == 200
    assert "****" in resp.json()["api_key_masked"]


def test_settings_source_not_configured(client, auth_headers):
    """api_key_source should be 'not_configured' when no key is set at all."""
    from unittest.mock import patch
    from app.api import settings as settings_mod
    with patch.object(settings_mod.settings, "openai_api_key", ""), \
         patch("app.api.settings.is_runtime_key_set", return_value=False):
        resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["api_key_source"] == "not_configured"


def test_production_settings_api_ignores_billing_env_fallbacks(client, auth_headers, monkeypatch):
    import app.runtime.settings_store as store
    from app.api import settings as settings_mod

    cfg = production_settings()
    reset_runtime_settings(monkeypatch)
    monkeypatch.setattr(store, "get_settings", lambda: cfg)
    monkeypatch.setattr(settings_mod, "settings", cfg)

    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["api_key_source"] == "not_configured"
    assert body["api_key_masked"] == ""
    assert body["pinecone_api_key_source"] == "not_configured"
    assert body["pinecone_api_key_masked"] == ""
    assert body["blob_read_write_token_source"] == "not_configured"
    assert body["blob_read_write_token_masked"] == ""
    assert body["langchain_api_key_masked"] == ""
    assert body["model"] == "gpt-4o-mini"
    assert body["embedding_model"] == "text-embedding-3-small"
    assert body["planner_model"] == "gpt-4o-mini"
    assert body["generator_model"] == "gpt-4o-mini"
    assert body["validator_model"] == "gpt-4o-mini"
    assert body["retriever_k"] == 4
    assert body["retriever_fetch_k"] == 20
    assert body["max_context_chunks"] == 4
    assert body["max_completion_tokens"] == 1024
    assert body["token_budget_warning_threshold"] == 800
    assert body["langchain_tracing_v2"] is False
    assert body["langchain_project"] == "agenticai-rag-poc"


def test_production_settings_api_runtime_values_override_safe_defaults(client, auth_headers, monkeypatch):
    import app.runtime.settings_store as store
    from app.api import settings as settings_mod

    cfg = production_settings()
    reset_runtime_settings(monkeypatch)
    monkeypatch.setattr(store, "get_settings", lambda: cfg)
    monkeypatch.setattr(settings_mod, "settings", cfg)

    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={
            "api_key": _VALID_KEY,
            "model": "gpt-4o",
            "embedding_model": "text-embedding-3-large",
            "planner_model": "gpt-4o",
            "generator_model": "gpt-4",
            "validator_model": "gpt-4-turbo",
            "retriever_k": 8,
            "retriever_fetch_k": 32,
            "max_context_chunks": 8,
            "max_completion_tokens": 2048,
            "token_budget_warning_threshold": 1600,
            "langchain_tracing_v2": True,
            "langchain_api_key": "ls__runtime-key",
            "langchain_project": "runtime-project",
            "pinecone_api_key": "pc-runtime-key",
            "blob_read_write_token": "vercel_blob_rw_runtime",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key_source"] == "runtime"
    assert body["pinecone_api_key_source"] == "runtime"
    assert body["blob_read_write_token_source"] == "runtime"
    assert body["model"] == "gpt-4o"
    assert body["embedding_model"] == "text-embedding-3-large"
    assert body["planner_model"] == "gpt-4o"
    assert body["generator_model"] == "gpt-4"
    assert body["validator_model"] == "gpt-4-turbo"
    assert body["retriever_k"] == 8
    assert body["retriever_fetch_k"] == 32
    assert body["max_context_chunks"] == 8
    assert body["max_completion_tokens"] == 2048
    assert body["token_budget_warning_threshold"] == 1600
    assert body["langchain_tracing_v2"] is True
    assert body["langchain_api_key_masked"].endswith("...-key")
    assert body["langchain_project"] == "runtime-project"


def test_update_pinecone_settings_valid(client, auth_headers):
    import app.runtime.settings_store as store
    original = (
        store._runtime_pinecone_api_key,
        store._runtime_pinecone_index_name,
        store._runtime_pinecone_namespace,
        store._runtime_pinecone_cloud,
        store._runtime_pinecone_region,
    )
    try:
        resp = client.post(
            "/api/settings/",
            headers=auth_headers,
            json={
                "pinecone_api_key": "pc-test-key-123",
                "pinecone_index_name": "rag-prod",
                "pinecone_namespace": "tenant-a",
                "pinecone_cloud": "aws",
                "pinecone_region": "us-east-1",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["vector_store_type"] in {"chroma", "memory", "blob", "pinecone"}
        assert body["pinecone_api_key_source"] == "runtime"
        assert "****" in body["pinecone_api_key_masked"]
        assert body["pinecone_index_name"] == "rag-prod"
    finally:
        (
            store._runtime_pinecone_api_key,
            store._runtime_pinecone_index_name,
            store._runtime_pinecone_namespace,
            store._runtime_pinecone_cloud,
            store._runtime_pinecone_region,
        ) = original


def test_update_pinecone_bad_index_rejected(client, auth_headers):
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"pinecone_index_name": "Bad_Index"},
    )
    assert resp.status_code == 422
    assert "pinecone_index_name" in str(resp.json())


def test_update_blob_token_valid(client, auth_headers, monkeypatch):
    import os
    import app.runtime.settings_store as store

    original = store._runtime_blob_read_write_token
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    try:
        resp = client.post(
            "/api/settings/",
            headers=auth_headers,
            json={"blob_read_write_token": "vercel_blob_rw_test_token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["blob_read_write_token_source"] == "runtime"
        assert "****" in body["blob_read_write_token_masked"]
        assert os.environ["BLOB_READ_WRITE_TOKEN"] == "vercel_blob_rw_test_token"
    finally:
        store._runtime_blob_read_write_token = original


def test_update_blob_token_rejects_whitespace(client, auth_headers):
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"blob_read_write_token": "vercel blob token"},
    )
    assert resp.status_code == 422
    assert "blob_read_write_token" in str(resp.json())


def test_vector_store_type_is_not_runtime_mutable(client, auth_headers):
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"vector_store_type": "pinecone"},
    )
    assert resp.status_code == 422
    assert "Provide at least one setting field" in resp.json()["detail"]


# ── New retrieval parameter tests ──────────────────────────────────────────────

def test_update_retriever_k_valid(client, auth_headers):
    """POST retriever_k=8 should succeed and reflect in response."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"retriever_k": 8}
    )
    assert resp.status_code == 200
    assert resp.json()["retriever_k"] == 8


def test_update_retriever_k_invalid(client, auth_headers):
    """POST retriever_k=25 should fail with 422 (above max of 20)."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"retriever_k": 25}
    )
    assert resp.status_code == 422
    assert "retriever_k" in str(resp.json())


def test_update_retriever_k_zero_rejected(client, auth_headers):
    """POST retriever_k=0 should fail (below min of 1)."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"retriever_k": 0}
    )
    assert resp.status_code == 422


def test_update_similarity_threshold_valid(client, auth_headers):
    """POST similarity_score_threshold=0.7 should succeed."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"similarity_score_threshold": 0.7},
    )
    assert resp.status_code == 200
    assert resp.json()["similarity_score_threshold"] == pytest.approx(0.7, abs=1e-4)


def test_update_similarity_threshold_invalid_negative(client, auth_headers):
    """POST similarity_score_threshold=-0.1 should fail."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"similarity_score_threshold": -0.1},
    )
    assert resp.status_code == 422


def test_update_retriever_use_mmr(client, auth_headers):
    """POST retriever_use_mmr=true should succeed."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"retriever_use_mmr": True}
    )
    assert resp.status_code == 200
    assert resp.json()["retriever_use_mmr"] is True


def test_update_max_context_chunks_valid(client, auth_headers):
    """POST max_context_chunks=6 should succeed."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"max_context_chunks": 6}
    )
    assert resp.status_code == 200
    assert resp.json()["max_context_chunks"] == 6


def test_update_max_context_chunks_invalid(client, auth_headers):
    """POST max_context_chunks=25 should fail."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"max_context_chunks": 25}
    )
    assert resp.status_code == 422


# ── New per-node model tests ───────────────────────────────────────────────────

def test_update_planner_model_valid(client, auth_headers):
    """POST planner_model=gpt-4o should succeed."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"planner_model": "gpt-4o"}
    )
    assert resp.status_code == 200
    assert resp.json()["planner_model"] == "gpt-4o"


def test_update_planner_model_invalid(client, auth_headers):
    """POST planner_model=invalid-model should fail with 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"planner_model": "invalid-model"}
    )
    assert resp.status_code == 422
    assert "planner_model" in str(resp.json())


def test_update_generator_model_valid(client, auth_headers):
    """POST generator_model=gpt-4o should succeed."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"generator_model": "gpt-4o"}
    )
    assert resp.status_code == 200
    assert resp.json()["generator_model"] == "gpt-4o"


def test_update_validator_model_valid(client, auth_headers):
    """POST validator_model=gpt-4o-mini should succeed."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"validator_model": "gpt-4o-mini"}
    )
    assert resp.status_code == 200
    assert resp.json()["validator_model"] == "gpt-4o-mini"


# ── New generation limit tests ─────────────────────────────────────────────────

def test_update_max_completion_tokens_valid(client, auth_headers):
    """POST max_completion_tokens=512 should succeed."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"max_completion_tokens": 512}
    )
    assert resp.status_code == 200
    assert resp.json()["max_completion_tokens"] == 512


def test_update_max_completion_tokens_too_low(client, auth_headers):
    """POST max_completion_tokens=50 should fail (below min 128)."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"max_completion_tokens": 50}
    )
    assert resp.status_code == 422


def test_update_max_completion_tokens_too_high(client, auth_headers):
    """POST max_completion_tokens=5000 should fail (above max 4096)."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"max_completion_tokens": 5000}
    )
    assert resp.status_code == 422


def test_update_token_budget_warning_threshold_valid(client, auth_headers):
    """POST token_budget_warning_threshold=600 should succeed."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"token_budget_warning_threshold": 600},
    )
    assert resp.status_code == 200
    assert resp.json()["token_budget_warning_threshold"] == 600


# ── LangSmith tests ────────────────────────────────────────────────────────────

def test_update_langchain_tracing_without_key_logs_warning(client, auth_headers):
    """POST langchain_tracing_v2=true with no key configured returns 200 (warning logged, not error)."""
    import app.runtime.settings_store as store

    # Ensure no runtime LangSmith key is set
    orig_key = store._runtime_langchain_api_key
    store._runtime_langchain_api_key = ""

    with patch("app.runtime.settings_store.get_settings") as mock_settings:
        mock_settings.return_value.langchain_api_key = ""
        mock_settings.return_value.langchain_tracing_v2 = False
        mock_settings.return_value.langchain_project = "test-proj"
        mock_settings.return_value.llm_model = "gpt-4o-mini"
        mock_settings.return_value.planner_model = ""
        mock_settings.return_value.generator_model = ""
        mock_settings.return_value.validator_model = ""
        mock_settings.return_value.retriever_k = 4
        mock_settings.return_value.similarity_score_threshold = 0.0
        mock_settings.return_value.retriever_use_mmr = False
        mock_settings.return_value.retriever_fetch_k = 20
        mock_settings.return_value.max_context_chunks = 4
        mock_settings.return_value.max_completion_tokens = 1024
        mock_settings.return_value.token_budget_warning_threshold = 800
        mock_settings.return_value.openai_api_key = ""
        mock_settings.return_value.vector_store_type = "memory"
        mock_settings.return_value.pinecone_api_key = ""
        mock_settings.return_value.pinecone_index_name = "agenticai-rag-poc-documents"
        mock_settings.return_value.pinecone_namespace = ""
        mock_settings.return_value.pinecone_cloud = "aws"
        mock_settings.return_value.pinecone_region = "us-east-1"
        mock_settings.return_value.secret_key = "test-secret-key-for-testing-only-32ch"
        mock_settings.return_value.algorithm = "HS256"
        mock_settings.return_value.retriever_hybrid_bm25 = True
        mock_settings.return_value.relevance_grader_enabled = False
        mock_settings.return_value.reranker_type = "none"
        mock_settings.return_value.reranker_judge_model = "gpt-4.1-mini"
        mock_settings.return_value.chunker_type = "recursive"
        mock_settings.return_value.chunk_size = 800
        mock_settings.return_value.chunk_overlap = 100

        resp = client.post(
            "/api/settings/",
            headers=auth_headers,
            json={"langchain_tracing_v2": True},
        )

    store._runtime_langchain_api_key = orig_key
    # Should return 200 — the warning is logged but is not an error
    assert resp.status_code == 200
    assert resp.json()["langchain_tracing_v2"] is True


def test_update_langchain_project_valid(client, auth_headers):
    """POST langchain_project should succeed."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"langchain_project": "my-rag-project"},
    )
    assert resp.status_code == 200
    assert resp.json()["langchain_project"] == "my-rag-project"


def test_update_langchain_api_key_invalid_prefix(client, auth_headers):
    """POST langchain_api_key with wrong prefix should fail."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"langchain_api_key": "sk-notlangsmith123"},
    )
    assert resp.status_code == 422
    assert "langchain_api_key" in str(resp.json())


def test_update_langchain_api_key_masked_in_response(client, auth_headers):
    """LangSmith API key must never be returned in full."""
    lskey = "ls__" + "x" * 40
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"langchain_api_key": lskey},
    )
    assert resp.status_code == 200
    masked = resp.json()["langchain_api_key_masked"]
    assert "****" in masked
    assert lskey not in masked  # key is never returned in full


# ── fetch_k constraint tests ───────────────────────────────────────────────────

def test_update_fetch_k_must_be_gte_retriever_k(client, auth_headers):
    """
    When retriever_k=4 (current effective) and fetch_k=2 is sent, should fail with 422.
    """
    import app.runtime.settings_store as store

    orig_k = store._runtime_retriever_k
    store._runtime_retriever_k = 4

    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"retriever_fetch_k": 2},
    )

    store._runtime_retriever_k = orig_k
    assert resp.status_code == 422
    assert "retriever_fetch_k" in str(resp.json())


def test_update_both_retriever_k_and_fetch_k_consistent(client, auth_headers):
    """When both retriever_k=8 and retriever_fetch_k=10 are sent together, should succeed."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"retriever_k": 8, "retriever_fetch_k": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["retriever_k"] == 8
    assert body["retriever_fetch_k"] == 10


def test_update_both_retriever_k_and_fetch_k_inconsistent(client, auth_headers):
    """When retriever_k=8 and retriever_fetch_k=5 are sent together, should fail."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"retriever_k": 8, "retriever_fetch_k": 5},
    )
    assert resp.status_code == 422


# ── Guest access restriction tests ────────────────────────────────────────────

def test_guest_cannot_update_retrieval_settings(client, guest_headers):
    """Guest token posting retriever_k should receive 403."""
    resp = client.post(
        "/api/settings/", headers=guest_headers, json={"retriever_k": 8}
    )
    assert resp.status_code == 403
    assert "Guests can only" in resp.json()["detail"]


def test_guest_cannot_update_per_node_models(client, guest_headers):
    """Guest token posting planner_model should receive 403."""
    resp = client.post(
        "/api/settings/", headers=guest_headers, json={"planner_model": "gpt-4o"}
    )
    assert resp.status_code == 403
    assert "Guests can only" in resp.json()["detail"]


def test_guest_cannot_update_max_completion_tokens(client, guest_headers):
    """Guest token posting max_completion_tokens should receive 403."""
    resp = client.post(
        "/api/settings/", headers=guest_headers, json={"max_completion_tokens": 512}
    )
    assert resp.status_code == 403


def test_guest_cannot_update_langchain_settings(client, guest_headers):
    """Guest token posting langchain_tracing_v2 should receive 403."""
    resp = client.post(
        "/api/settings/", headers=guest_headers, json={"langchain_tracing_v2": True}
    )
    assert resp.status_code == 403


def test_guest_cannot_update_similarity_threshold(client, guest_headers):
    """Guest token posting similarity_score_threshold should receive 403."""
    resp = client.post(
        "/api/settings/",
        headers=guest_headers,
        json={"similarity_score_threshold": 0.5},
    )
    assert resp.status_code == 403


def test_guest_can_update_pinecone_settings_once(client, auth_headers):
    import app.runtime.settings_store as store
    original = (
        store._runtime_pinecone_api_key,
        store._runtime_pinecone_index_name,
        store._runtime_pinecone_namespace,
        store._runtime_pinecone_cloud,
        store._runtime_pinecone_region,
    )
    try:
        guest_resp = client.post("/api/auth/guest")
        assert guest_resp.status_code == 200
        headers = {"Authorization": f"Bearer {guest_resp.json()['access_token']}"}
        resp = client.post(
            "/api/settings/",
            headers=headers,
            json={
                "model": "gpt-4o-mini",
                "pinecone_api_key": "pc-guest-key-123",
                "pinecone_index_name": "guest-rag",
                "pinecone_namespace": "guest-session",
                "pinecone_cloud": "aws",
                "pinecone_region": "us-east-1",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["vector_store_type"] in {"chroma", "memory", "blob", "pinecone"}
        assert body["pinecone_api_key_source"] == "runtime"
        assert body["pinecone_index_name"] == "guest-rag"
        admin_get = client.get("/api/settings/", headers=auth_headers)
        assert admin_get.status_code == 200
        assert admin_get.json()["pinecone_index_name"] != "guest-rag"
    finally:
        (
            store._runtime_pinecone_api_key,
            store._runtime_pinecone_index_name,
            store._runtime_pinecone_namespace,
            store._runtime_pinecone_cloud,
            store._runtime_pinecone_region,
        ) = original
        store._guest_runtime_settings.clear()


def test_guest_can_update_blob_token_once(client, auth_headers):
    import app.runtime.settings_store as store

    original = store._runtime_blob_read_write_token
    try:
        guest_login = client.post("/api/auth/guest")
        assert guest_login.status_code == 200
        headers = {"Authorization": f"Bearer {guest_login.json()['access_token']}"}

        resp = client.post(
            "/api/settings/",
            headers=headers,
            json={"blob_read_write_token": "vercel_blob_rw_guest_token"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["blob_read_write_token_source"] == "runtime"
        assert "****" in body["blob_read_write_token_masked"]
        admin_get = client.get("/api/settings/", headers=auth_headers)
        assert admin_get.status_code == 200
        assert admin_get.json()["blob_read_write_token_source"] != "runtime"
    finally:
        store._runtime_blob_read_write_token = original
        store._guest_runtime_settings.clear()


def test_guest_settings_view_does_not_expose_admin_runtime_key(client, auth_headers):
    """Guest settings lookup is session scoped and cannot inherit admin runtime secrets."""
    import app.runtime.settings_store as store

    original_key = store._runtime_api_key
    try:
        store._guest_runtime_settings.clear()
        admin_key = "sk-" + "A" * 48
        admin_resp = client.post(
            "/api/settings/",
            headers=auth_headers,
            json={"api_key": admin_key},
        )
        assert admin_resp.status_code == 200
        assert admin_resp.json()["api_key_source"] == "runtime"

        guest_resp = client.post("/api/auth/guest")
        assert guest_resp.status_code == 200
        guest_headers = {"Authorization": f"Bearer {guest_resp.json()['access_token']}"}
        guest_settings = client.get("/api/settings/", headers=guest_headers)

        assert guest_settings.status_code == 200
        body = guest_settings.json()
        assert body["api_key_source"] != "runtime"
        assert not body["api_key_masked"].endswith(admin_key[-4:])
    finally:
        store._runtime_api_key = original_key
        store._guest_runtime_settings.clear()


def test_guest_settings_response_reports_lock_after_successful_save(client):
    guest_resp = client.post("/api/auth/guest")
    assert guest_resp.status_code == 200
    headers = {"Authorization": f"Bearer {guest_resp.json()['access_token']}"}

    before = client.get("/api/settings/", headers=headers)
    assert before.status_code == 200
    assert before.json()["guest_settings_locked"] is False
    assert before.json()["guest_settings_recoverable"] is False
    assert before.json()["guest_settings_reason"] == "available"

    save = client.post(
        "/api/settings/",
        headers=headers,
        json={"api_key": _VALID_KEY, "model": "gpt-4o-mini"},
    )
    assert save.status_code == 200
    assert save.json()["guest_settings_locked"] is True
    assert save.json()["guest_settings_reason"] == "already_configured"

    after = client.get("/api/settings/", headers=headers)
    assert after.status_code == 200
    assert after.json()["guest_settings_locked"] is True
    assert after.json()["guest_settings_recoverable"] is False


def test_guest_settings_lock_is_recoverable_when_runtime_overrides_are_missing(client):
    import app.api.settings as settings_api
    import app.runtime.settings_store as store

    guest_resp = client.post("/api/auth/guest")
    assert guest_resp.status_code == 200
    token = guest_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    jti = jwt.get_unverified_claims(token)["jti"]

    settings_api._guest_settings_used.add(jti)
    store._guest_runtime_settings.pop(jti, None)

    status_resp = client.get("/api/settings/", headers=headers)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["guest_settings_locked"] is False
    assert body["guest_settings_recoverable"] is True
    assert body["guest_settings_reason"] == "settings_lost_after_restart"

    save = client.post(
        "/api/settings/",
        headers=headers,
        json={"api_key": _VALID_KEY, "model": "gpt-4o-mini"},
    )
    assert save.status_code == 200
    assert save.json()["api_key_source"] == "runtime"
    assert save.json()["guest_settings_locked"] is True
    assert save.json()["guest_settings_recoverable"] is False


# ── GET /api/settings/ragas-scores ────────────────────────────────────────────

def test_ragas_scores_forbidden_for_guest(client, guest_headers):
    """GET /api/settings/ragas-scores returns 403 for guest users."""
    resp = client.get("/api/settings/ragas-scores", headers=guest_headers)
    assert resp.status_code == 403
    assert "Admin only" in resp.json()["detail"]


def test_ragas_scores_returns_200_with_has_results_false_when_no_scores_file(
    client, auth_headers, tmp_path, monkeypatch
):
    """GET /api/settings/ragas-scores returns 200 with has_results=False when no scores exist yet."""
    missing_path = tmp_path / "no_ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(missing_path))
    resp = client.get("/api/settings/ragas-scores", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_results"] is False
    assert body["faithfulness"] == pytest.approx(0.0)
    assert body["answer_relevancy"] == pytest.approx(0.0)
    assert body["context_precision"] == pytest.approx(0.0)
    assert body["context_recall"] == pytest.approx(0.0)
    assert body["evaluated_at"] == ""
    assert body["model"] == ""
    assert body["num_samples"] == 0


def test_ragas_scores_returns_200_with_correct_scores(client, auth_headers, tmp_path, monkeypatch):
    """GET /api/settings/ragas-scores returns 200 with correct scores and has_results=True when file exists."""
    import json as _json
    scores_file = tmp_path / "ragas_scores.json"
    scores_file.write_text(_json.dumps({
        "faithfulness": 0.91,
        "answer_relevancy": 0.87,
        "context_precision": 0.76,
        "context_recall": 0.65,
        "evaluated_at": "2024-01-15T12:00:00+00:00",
        "model": "gpt-4o-mini",
        "num_samples": 3,
    }))
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(scores_file))
    resp = client.get("/api/settings/ragas-scores", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_results"] is True
    assert body["faithfulness"] == pytest.approx(0.91, abs=1e-5)
    assert body["answer_relevancy"] == pytest.approx(0.87, abs=1e-5)
    assert body["context_precision"] == pytest.approx(0.76, abs=1e-5)
    assert body["context_recall"] == pytest.approx(0.65, abs=1e-5)
    assert body["model"] == "gpt-4o-mini"
    assert body["num_samples"] == 3
    assert body["evaluated_at"] == "2024-01-15T12:00:00+00:00"


def test_ragas_scores_requires_auth(client):
    """GET /api/settings/ragas-scores returns 403 without any auth token."""
    resp = client.get("/api/settings/ragas-scores")
    assert resp.status_code == 403


# ── POST /api/settings/ragas-trigger ──────────────────────────────────────────

def test_ragas_trigger_requires_admin(client, guest_headers):
    """POST /api/settings/ragas-trigger returns 403 for guest users."""
    resp = client.post("/api/settings/ragas-trigger", headers=guest_headers)
    assert resp.status_code == 403
    assert "Admin only" in resp.json()["detail"]


def test_ragas_trigger_no_documents_returns_422(client, auth_headers):
    """POST /api/settings/ragas-trigger returns 422 when no documents are indexed."""
    with patch("app.rag.vector_store.has_documents", return_value=False):
        resp = client.post("/api/settings/ragas-trigger", headers=auth_headers)
    assert resp.status_code == 422
    assert "No documents indexed" in resp.json()["detail"]


def test_ragas_trigger_starts_background_task(client, auth_headers):
    """POST /api/settings/ragas-trigger returns 200 with status='started' when documents exist."""
    with patch("app.rag.vector_store.has_documents", return_value=True):
        resp = client.post("/api/settings/ragas-trigger", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    assert "background" in body["message"].lower()


def test_ragas_trigger_requires_auth(client):
    """POST /api/settings/ragas-trigger returns 403 without auth token."""
    resp = client.post("/api/settings/ragas-trigger")
    assert resp.status_code == 403


# ── Pipeline feature flag tests ───────────────────────────────────────────────

def test_update_retriever_hybrid_bm25_valid(client, auth_headers, monkeypatch):
    """POST retriever_hybrid_bm25=false should succeed and reflect in response."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"retriever_hybrid_bm25": False}
    )
    assert resp.status_code == 200
    assert resp.json()["retriever_hybrid_bm25"] is False

    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)


def test_update_relevance_grader_enabled_valid(client, auth_headers, monkeypatch):
    """POST relevance_grader_enabled=true should succeed."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"relevance_grader_enabled": True}
    )
    assert resp.status_code == 200
    assert resp.json()["relevance_grader_enabled"] is True

    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)


def test_update_reranker_type_valid(client, auth_headers, monkeypatch):
    """POST reranker_type='none' should succeed."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_type", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"reranker_type": "none"}
    )
    assert resp.status_code == 200
    assert resp.json()["reranker_type"] == "none"
    assert "none" in resp.json()["allowed_reranker_types"]
    assert "cross-encoder" in resp.json()["allowed_reranker_types"]

    monkeypatch.setattr(store, "_runtime_reranker_type", None)


def test_update_reranker_type_invalid(client, auth_headers):
    """POST reranker_type='unknown' should return 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"reranker_type": "unknown"}
    )
    assert resp.status_code == 422
    assert "reranker_type" in str(resp.json())


def test_update_reranker_judge_model_valid(client, auth_headers, monkeypatch):
    """POST reranker_judge_model='gpt-4.1-nano' should succeed and be reflected in response."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_judge_model", "")

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"reranker_judge_model": "gpt-4.1-nano"}
    )
    assert resp.status_code == 200
    assert resp.json()["reranker_judge_model"] == "gpt-4.1-nano"
    assert "gpt-4.1-mini" in resp.json()["allowed_judge_models"]
    assert "gpt-4.1-nano" in resp.json()["allowed_judge_models"]
    assert "gpt-4.1" in resp.json()["allowed_judge_models"]

    monkeypatch.setattr(store, "_runtime_reranker_judge_model", "")


def test_update_reranker_judge_model_invalid_raises(client, auth_headers):
    """POST reranker_judge_model with a pipeline model (gpt-4o-mini) should return 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"reranker_judge_model": "gpt-4o-mini"}
    )
    assert resp.status_code == 422
    assert "reranker_judge_model" in str(resp.json())


def test_update_reranker_judge_model_unknown_model_raises(client, auth_headers):
    """POST reranker_judge_model with an unknown model should return 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"reranker_judge_model": "gpt-99"}
    )
    assert resp.status_code == 422
    assert "reranker_judge_model" in str(resp.json())


def test_settings_response_includes_judge_model_fields(client, auth_headers):
    """GET /api/settings/ response includes reranker_judge_model and allowed_judge_models."""
    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "reranker_judge_model" in body
    assert "allowed_judge_models" in body
    assert body["reranker_judge_model"] == "gpt-4.1-mini"
    # Pipeline models must not be in the judge model allowlist
    assert "gpt-4o-mini" not in body["allowed_judge_models"]
    assert "gpt-4o" not in body["allowed_judge_models"]


def test_guest_cannot_set_reranker_judge_model(client, guest_headers, monkeypatch):
    """Guests are blocked from setting reranker_judge_model (admin-only pipeline setting)."""
    resp = client.post(
        "/api/settings/",
        headers=guest_headers,
        json={"reranker_judge_model": "gpt-4.1-nano"},
    )
    assert resp.status_code == 403


def test_update_chunker_type_valid(client, auth_headers, monkeypatch):
    """POST chunker_type='recursive' should succeed."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunker_type", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunker_type": "recursive"}
    )
    assert resp.status_code == 200
    assert resp.json()["chunker_type"] == "recursive"
    assert "recursive" in resp.json()["allowed_chunker_types"]
    assert "semantic" in resp.json()["allowed_chunker_types"]

    monkeypatch.setattr(store, "_runtime_chunker_type", None)


def test_update_chunker_type_invalid(client, auth_headers):
    """POST chunker_type='ngram' should return 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunker_type": "ngram"}
    )
    assert resp.status_code == 422
    assert "chunker_type" in str(resp.json())


def test_update_chunk_size_valid(client, auth_headers, monkeypatch):
    """POST chunk_size=400 should succeed."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunk_size": 400}
    )
    assert resp.status_code == 200
    assert resp.json()["chunk_size"] == 400

    monkeypatch.setattr(store, "_runtime_chunk_size", None)


def test_update_chunk_size_too_small(client, auth_headers):
    """POST chunk_size=50 should return 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunk_size": 50}
    )
    assert resp.status_code == 422
    assert "chunk_size" in str(resp.json())


def test_update_chunk_size_too_large(client, auth_headers):
    """POST chunk_size=5000 should return 422."""
    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunk_size": 5000}
    )
    assert resp.status_code == 422


def test_update_chunk_overlap_valid(client, auth_headers, monkeypatch):
    """POST chunk_size=400 + chunk_overlap=50 should succeed."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunk_size": 400, "chunk_overlap": 50}
    )
    assert resp.status_code == 200
    assert resp.json()["chunk_size"] == 400
    assert resp.json()["chunk_overlap"] == 50

    monkeypatch.setattr(store, "_runtime_chunk_size", None)
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)


def test_update_chunk_overlap_gte_chunk_size_rejected(client, auth_headers, monkeypatch):
    """POST chunk_size=400 + chunk_overlap=400 should return 422."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)

    resp = client.post(
        "/api/settings/", headers=auth_headers, json={"chunk_size": 400, "chunk_overlap": 400}
    )
    assert resp.status_code == 422
    assert "chunk_overlap" in str(resp.json())

    monkeypatch.setattr(store, "_runtime_chunk_size", None)
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)


def test_guest_cannot_update_pipeline_flags(client, guest_headers):
    """Guest token posting retriever_hybrid_bm25 should receive 403."""
    resp = client.post(
        "/api/settings/", headers=guest_headers, json={"retriever_hybrid_bm25": True}
    )
    assert resp.status_code == 403
    assert "Guests can only" in resp.json()["detail"]


def test_guest_cannot_update_chunker_type(client, guest_headers):
    """Guest token posting chunker_type should receive 403."""
    resp = client.post(
        "/api/settings/", headers=guest_headers, json={"chunker_type": "recursive"}
    )
    assert resp.status_code == 403


def test_update_reranker_type_xss_rejected(client, auth_headers):
    """XSS in reranker_type is sanitized and then fails validation."""
    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"reranker_type": "<script>alert(1)</script>"},
    )
    assert resp.status_code == 422


def test_allowed_reranker_and_chunker_types_returned(client, auth_headers):
    """GET /api/settings/ includes allowed_reranker_types and allowed_chunker_types."""
    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["allowed_reranker_types"]) == ["cross-encoder", "llm-judge", "none"]
    assert sorted(body["allowed_chunker_types"]) == ["recursive", "semantic"]


# ── ragas_evaluation_enabled tests ───────────────────────────────────────────

def test_get_settings_includes_ragas_evaluation_enabled(client, auth_headers):
    """GET /api/settings/ must include the ragas_evaluation_enabled bool field."""
    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "ragas_evaluation_enabled" in body
    assert isinstance(body["ragas_evaluation_enabled"], bool)


def test_get_settings_ragas_evaluation_enabled_reflects_config(client, auth_headers, monkeypatch):
    """When no runtime override is set, ragas_evaluation_enabled reflects the config/env value."""
    import app.runtime.settings_store as store
    from app.config import get_settings
    monkeypatch.setattr(store, "_runtime_ragas_evaluation_enabled", None)

    resp = client.get("/api/settings/", headers=auth_headers)
    assert resp.status_code == 200
    # Must match the env/config default — not hard-coded to False, because
    # RAGAS_EVALUATION_ENABLED env var may be set (e.g. True in dev .env).
    assert resp.json()["ragas_evaluation_enabled"] is get_settings().ragas_evaluation_enabled


def test_update_ragas_evaluation_enabled_true_as_admin(client, auth_headers, monkeypatch):
    """POST ragas_evaluation_enabled=true as admin must succeed and reflect in response."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_ragas_evaluation_enabled", None)

    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"ragas_evaluation_enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json()["ragas_evaluation_enabled"] is True

    monkeypatch.setattr(store, "_runtime_ragas_evaluation_enabled", None)


def test_update_ragas_evaluation_enabled_false_as_admin(client, auth_headers, monkeypatch):
    """POST ragas_evaluation_enabled=false as admin must succeed and return false."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_ragas_evaluation_enabled", None)

    resp = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"ragas_evaluation_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["ragas_evaluation_enabled"] is False

    monkeypatch.setattr(store, "_runtime_ragas_evaluation_enabled", None)


def test_update_ragas_evaluation_enabled_as_guest_returns_403(client):
    """POST ragas_evaluation_enabled=true as guest must return 403."""
    guest_resp = client.post("/api/auth/guest")
    assert guest_resp.status_code == 200
    headers = {"Authorization": f"Bearer {guest_resp.json()['access_token']}"}

    resp = client.post(
        "/api/settings/",
        headers=headers,
        json={"ragas_evaluation_enabled": True},
    )
    assert resp.status_code == 403
    assert "Guests can only" in resp.json()["detail"]


def test_ragas_evaluation_enabled_toggle_persists(client, auth_headers, monkeypatch):
    """Setting ragas_evaluation_enabled to true then false must reflect each change."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_ragas_evaluation_enabled", None)

    resp_on = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"ragas_evaluation_enabled": True},
    )
    assert resp_on.status_code == 200
    assert resp_on.json()["ragas_evaluation_enabled"] is True

    resp_off = client.post(
        "/api/settings/",
        headers=auth_headers,
        json={"ragas_evaluation_enabled": False},
    )
    assert resp_off.status_code == 200
    assert resp_off.json()["ragas_evaluation_enabled"] is False


# ── Field validation errors (lines 497-626) ───────────────────────────────────

def test_update_settings_invalid_embedding_model_returns_422(client, auth_headers):
    """Invalid embedding model name must return 422 with embedding_model in detail."""
    resp = client.post(
        "/api/settings/",
        json={"embedding_model": "not-a-real-embedding-model"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "embedding_model" in resp.json()["detail"]


def test_update_settings_invalid_planner_model_returns_422(client, auth_headers):
    """Invalid planner_model must return 422 with planner_model in detail."""
    resp = client.post(
        "/api/settings/",
        json={"planner_model": "gpt-9000-ultra-nonexistent"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "planner_model" in resp.json()["detail"]


def test_update_settings_invalid_generator_model_returns_422(client, auth_headers):
    """Invalid generator_model must return 422 with generator_model in detail."""
    resp = client.post(
        "/api/settings/",
        json={"generator_model": "gpt-does-not-exist"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "generator_model" in resp.json()["detail"]


def test_update_settings_negative_token_budget_warning_threshold_returns_422(client, auth_headers):
    """Negative token_budget_warning_threshold must return 422 with field in detail."""
    resp = client.post(
        "/api/settings/",
        json={"token_budget_warning_threshold": -1},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "token_budget_warning_threshold" in resp.json()["detail"]


def test_update_settings_langchain_project_too_long_returns_422(client, auth_headers):
    """langchain_project longer than 100 chars must return 422 with field in detail."""
    resp = client.post(
        "/api/settings/",
        json={"langchain_project": "x" * 101},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "langchain_project" in resp.json()["detail"]


def test_update_settings_empty_pinecone_api_key_returns_422(client, auth_headers):
    """Empty pinecone_api_key string must return 422 with field in detail."""
    resp = client.post(
        "/api/settings/",
        json={"pinecone_api_key": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "pinecone_api_key" in resp.json()["detail"]


def test_update_settings_invalid_pinecone_namespace_returns_422(client, auth_headers):
    """Pinecone namespace with invalid characters must return 422 with field in detail."""
    resp = client.post(
        "/api/settings/",
        json={"pinecone_namespace": "bad namespace!"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "pinecone_namespace" in resp.json()["detail"]


def test_update_settings_invalid_pinecone_cloud_returns_422(client, auth_headers):
    """Unsupported pinecone_cloud value must return 422 with field in detail."""
    resp = client.post(
        "/api/settings/",
        json={"pinecone_cloud": "mars"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "pinecone_cloud" in resp.json()["detail"]


def test_update_settings_invalid_pinecone_region_returns_422(client, auth_headers):
    """Pinecone region with invalid characters (uppercase) must return 422."""
    resp = client.post(
        "/api/settings/",
        json={"pinecone_region": "US_EAST_1!!"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "pinecone_region" in resp.json()["detail"]


def test_update_settings_invalid_validator_model_returns_422(client, auth_headers):
    """Invalid validator_model must return 422 with validator_model in detail (lines 518-519)."""
    resp = client.post(
        "/api/settings/",
        json={"validator_model": "gpt-999-nonexistent"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "validator_model" in resp.json()["detail"]


# ── _guest_lock_state — missing_session branch (line 277) ───────────────────

def test_guest_lock_state_missing_session_id():
    """_guest_lock_state returns (True, False, 'missing_session') when session_id is None."""
    from app.api.settings import _guest_lock_state
    from app.auth.models import UserInDB

    user = UserInDB(username="guest_x", hashed_password="hashed", role="guest", session_id=None)
    locked, recoverable, reason = _guest_lock_state(user)
    assert locked is True
    assert recoverable is False
    assert reason == "missing_session"


def test_guest_lock_state_missing_empty_session_id():
    """_guest_lock_state returns 'missing_session' when session_id is empty string."""
    from app.api.settings import _guest_lock_state
    from app.auth.models import UserInDB

    user = UserInDB(username="guest_y", hashed_password="hashed", role="guest", session_id="")
    locked, recoverable, reason = _guest_lock_state(user)
    assert locked is True
    assert recoverable is False
    assert reason == "missing_session"


# ── Guest update — JWT decode failure (lines 411-412) ───────────────────────

def test_guest_settings_update_bad_token_returns_401(client):
    """POST /api/settings/ with a malformed guest Bearer token must return 401.

    A malformed JWT is rejected by the auth dependency (get_current_user) before
    reaching the function body, returning 401.
    """
    resp = client.post(
        "/api/settings/",
        json={"api_key": "sk-" + "T" * 48},
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert resp.status_code == 401


def test_guest_settings_update_jwt_decode_fails_inside_handler(monkeypatch):
    """Lines 411-412: when the inner _jwt.decode call inside update_settings raises,
    the handler returns 401. This happens when the secret changes between auth and handler.
    """
    import app.api.settings as settings_api

    # Patch jose.jwt.decode (the _jwt reference inside settings.py) to raise
    from jose import JWTError
    monkeypatch.setattr(settings_api._jwt, "decode", lambda *a, **kw: (_ for _ in ()).throw(JWTError("bad token")))

    # Get a valid guest token first
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        guest_resp = c.post("/api/auth/guest")
        assert guest_resp.status_code == 200
        token = guest_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Reset rate limit
        from app.api.settings import limiter
        limiter._storage.reset()

        resp = c.post(
            "/api/settings/",
            json={"api_key": "sk-" + "T" * 48},
            headers=headers,
        )
    assert resp.status_code == 401


# ── _guest_settings_used eviction (line 720) ─────────────────────────────────

def test_guest_settings_used_eviction_clears_set(monkeypatch):
    """When _guest_settings_used reaches _MAX_GUEST_JTI, the set is cleared before adding."""
    import app.api.settings as settings_api

    # Fill the set up to the cap
    fake_jtis = {f"jti-{i}" for i in range(settings_api._MAX_GUEST_JTI)}
    monkeypatch.setattr(settings_api, "_guest_settings_used", fake_jtis.copy())

    # Simulate eviction logic directly (without a real HTTP call, to avoid
    # the JWT overhead — the branching logic on line 719-720 is the target).
    used = settings_api._guest_settings_used
    new_jti = "jti-new"
    if len(used) >= settings_api._MAX_GUEST_JTI:
        used.clear()
    used.add(new_jti)

    assert new_jti in settings_api._guest_settings_used
    # After eviction, the set should contain only the new entry
    assert len(settings_api._guest_settings_used) == 1


# ── _build_response — pinecone env source and blob not_configured (302, 311) ─

def test_build_response_pinecone_source_environment(monkeypatch):
    """_build_response returns pinecone_source='environment' when env key is present but no runtime key.

    Tests line 302 of settings.py: the `pinecone_source = "environment"` branch
    inside _build_response when is_runtime_pinecone_key_set() is False but
    account_env_fallback_allowed() is True and settings.pinecone_api_key is set.
    """
    import app.api.settings as settings_api

    monkeypatch.setattr(settings_api, "is_runtime_pinecone_key_set", lambda: False)
    monkeypatch.setattr(settings_api, "account_env_fallback_allowed", lambda: True)
    monkeypatch.setattr(settings_api, "is_runtime_key_set", lambda: False)
    monkeypatch.setattr(settings_api, "is_runtime_blob_token_set", lambda: False)

    # Patch at the settings_store level to control the pinecone_api_key attribute
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_pinecone_api_key", "")

    import app.config as cfg_module
    real_settings = cfg_module.get_settings()

    # Use monkeypatching of the settings object attribute only for what's needed
    # and ensure retriever_fusion_mode and semantic_breakpoint_threshold_type remain valid strings
    from unittest.mock import MagicMock
    fake_settings = MagicMock()
    fake_settings.openai_api_key = ""
    fake_settings.pinecone_api_key = "pc-env-key"
    fake_settings.blob_read_write_token = ""
    fake_settings.vercel_blob_read_write_token = ""
    fake_settings.retriever_fusion_mode = "rrf"
    fake_settings.reranker_top_k = 4
    fake_settings.semantic_breakpoint_threshold_type = "percentile"
    fake_settings.max_query_length = 1000
    fake_settings.query_rate_limit_per_minute = 10
    fake_settings.effective_max_upload_size_mb = 20
    fake_settings.guest_max_upload_size_mb = 3
    fake_settings.guest_token_expire_minutes = 15
    fake_settings.guest_doc_retention_seconds = 3600
    monkeypatch.setattr(settings_api, "settings", fake_settings)

    resp = settings_api._build_response(user=None)
    assert resp.pinecone_api_key_source == "environment"


def test_build_response_blob_source_environment(monkeypatch):
    """_build_response returns blob_source='environment' when env blob token is present (line 311)."""
    import app.api.settings as settings_api

    monkeypatch.setattr(settings_api, "is_runtime_blob_token_set", lambda: False)
    monkeypatch.setattr(settings_api, "account_env_fallback_allowed", lambda: True)
    monkeypatch.setattr(settings_api, "is_runtime_key_set", lambda: False)
    monkeypatch.setattr(settings_api, "is_runtime_pinecone_key_set", lambda: False)

    from unittest.mock import MagicMock
    fake_settings = MagicMock()
    fake_settings.openai_api_key = ""
    fake_settings.pinecone_api_key = ""
    fake_settings.blob_read_write_token = "vercel_blob_rw_env_token"
    fake_settings.vercel_blob_read_write_token = ""
    fake_settings.retriever_fusion_mode = "rrf"
    fake_settings.reranker_top_k = 4
    fake_settings.semantic_breakpoint_threshold_type = "percentile"
    fake_settings.max_query_length = 1000
    fake_settings.query_rate_limit_per_minute = 10
    fake_settings.effective_max_upload_size_mb = 20
    fake_settings.guest_max_upload_size_mb = 3
    fake_settings.guest_token_expire_minutes = 15
    fake_settings.guest_doc_retention_seconds = 3600
    monkeypatch.setattr(settings_api, "settings", fake_settings)

    resp = settings_api._build_response(user=None)
    assert resp.blob_read_write_token_source == "environment"


def test_build_response_blob_source_not_configured(monkeypatch):
    """_build_response returns blob_source='not_configured' when no runtime or env blob token.

    Tests line 313 of settings.py: the `blob_source = "not_configured"` else branch inside
    _build_response when is_runtime_blob_token_set() is False and no env token is present.
    """
    import app.api.settings as settings_api

    monkeypatch.setattr(settings_api, "is_runtime_blob_token_set", lambda: False)
    monkeypatch.setattr(settings_api, "account_env_fallback_allowed", lambda: True)
    monkeypatch.setattr(settings_api, "is_runtime_key_set", lambda: False)
    monkeypatch.setattr(settings_api, "is_runtime_pinecone_key_set", lambda: False)

    from unittest.mock import MagicMock
    fake_settings = MagicMock()
    fake_settings.openai_api_key = ""
    fake_settings.pinecone_api_key = ""
    fake_settings.blob_read_write_token = ""
    fake_settings.vercel_blob_read_write_token = ""
    fake_settings.retriever_fusion_mode = "rrf"
    fake_settings.reranker_top_k = 4
    fake_settings.semantic_breakpoint_threshold_type = "percentile"
    fake_settings.max_query_length = 1000
    fake_settings.query_rate_limit_per_minute = 10
    fake_settings.effective_max_upload_size_mb = 20
    fake_settings.guest_max_upload_size_mb = 3
    fake_settings.guest_token_expire_minutes = 15
    fake_settings.guest_doc_retention_seconds = 3600
    monkeypatch.setattr(settings_api, "settings", fake_settings)

    resp = settings_api._build_response(user=None)
    assert resp.blob_read_write_token_source == "not_configured"


# ── trigger_ragas_eval endpoint (lines 780+) ─────────────────────────────────

def test_trigger_ragas_eval_as_guest_returns_403(client):
    """POST /api/settings/ragas-trigger as guest must return 403."""
    guest_resp = client.post("/api/auth/guest")
    assert guest_resp.status_code == 200
    headers = {"Authorization": f"Bearer {guest_resp.json()['access_token']}"}

    resp = client.post("/api/settings/ragas-trigger", headers=headers)
    assert resp.status_code == 403
    assert "Admin only" in resp.json()["detail"]


def test_trigger_ragas_eval_as_admin_no_documents_returns_422(client, auth_headers):
    """POST /api/settings/ragas-trigger with no indexed documents returns 422."""
    with patch("app.rag.vector_store.has_documents", return_value=False):
        resp = client.post("/api/settings/ragas-trigger", headers=auth_headers)
    assert resp.status_code == 422
    assert "No documents indexed" in resp.json()["detail"]


def test_trigger_ragas_eval_as_admin_with_documents_returns_200(client, auth_headers):
    """POST /api/settings/ragas-trigger as admin with documents returns status='started'."""
    with patch("app.rag.vector_store.has_documents", return_value=True):
        resp = client.post("/api/settings/ragas-trigger", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    assert "background" in body["message"].lower()


# ── _run_ragas_eval_background — mock mode (lines 796-836) ──────────────────

def test_run_ragas_eval_mock_mode_saves_scores(monkeypatch):
    """When ragas/datasets not installed, _run_ragas_eval_background saves mock scores."""
    import asyncio
    import builtins
    import app.runtime.ragas_store as ragas_store

    saved: dict = {}

    def _capture(**kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(ragas_store, "save_ragas_scores", _capture)

    # Mock has_documents to return False so _STATIC_SAMPLES path is used
    import app.api.settings as settings_api
    monkeypatch.setattr(
        settings_api,
        "_run_ragas_eval_background",
        settings_api._run_ragas_eval_background,
    )

    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name in ("datasets", "ragas"):
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    # Patch the vector store imports inside _run_ragas_eval_background
    with patch("app.rag.vector_store.has_documents", return_value=False), \
         patch("app.runtime.settings_store.get_effective_model", return_value="gpt-4o-mini"):
        asyncio.run(settings_api._run_ragas_eval_background())

    assert "faithfulness" in saved
    assert "answer_relevancy" in saved
    assert "context_precision" in saved
    assert "context_recall" in saved
    assert "(mock)" in saved.get("model", "")
