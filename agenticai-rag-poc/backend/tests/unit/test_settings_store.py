"""Unit tests for settings_store — pure validation logic, no HTTP."""
from types import SimpleNamespace

import pytest
from app.runtime.settings_store import (
    ALLOWED_MODELS,
    ALLOWED_RERANKER_TYPES,
    ALLOWED_CHUNKER_TYPES,
    ALLOWED_JUDGE_MODELS,
    validate_api_key,
    validate_model,
    validate_retriever_k,
    validate_similarity_score_threshold,
    validate_max_completion_tokens,
    validate_token_budget_warning_threshold,
    validate_retriever_fetch_k,
    validate_max_context_chunks,
    validate_langchain_api_key,
    validate_langchain_project,
    validate_pinecone_api_key,
    validate_pinecone_index_name,
    validate_pinecone_namespace,
    validate_pinecone_cloud,
    validate_pinecone_region,
    validate_blob_read_write_token,
    validate_reranker_type,
    validate_reranker_judge_model,
    validate_chunker_type,
    validate_chunk_size,
    validate_chunk_overlap,
    get_masked_api_key,
    get_masked_langchain_api_key,
    get_masked_pinecone_api_key,
    get_masked_blob_read_write_token,
    get_effective_api_key,
    get_effective_model,
    get_effective_embedding_model,
    get_effective_planner_model,
    get_effective_generator_model,
    get_effective_validator_model,
    get_effective_retriever_k,
    get_effective_similarity_score_threshold,
    get_effective_retriever_use_mmr,
    get_effective_retriever_fetch_k,
    get_effective_max_context_chunks,
    get_effective_max_completion_tokens,
    get_effective_token_budget_warning_threshold,
    get_effective_langchain_tracing_v2,
    get_effective_langchain_api_key,
    get_effective_langchain_project,
    get_effective_vector_store_type,
    get_effective_pinecone_api_key,
    get_effective_pinecone_index_name,
    get_effective_pinecone_namespace,
    get_effective_pinecone_cloud,
    get_effective_pinecone_region,
    get_effective_blob_read_write_token,
    get_effective_retriever_hybrid_bm25,
    get_effective_relevance_grader_enabled,
    get_effective_reranker_type,
    get_effective_reranker_judge_model,
    get_effective_chunker_type,
    get_effective_chunk_size,
    get_effective_chunk_overlap,
    apply_runtime_settings,
    is_runtime_key_set,
    set_request_runtime_settings,
    has_request_runtime_settings,
    has_guest_runtime_settings,
    set_runtime_scope,
)


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
        "reranker_type": "none",
        "reranker_judge_model": "gpt-4.1-mini",
        "chunker_type": "recursive",
        "chunk_size": 800,
        "chunk_overlap": 100,
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
        "_runtime_reranker_type": None,
        "_runtime_reranker_judge_model": "",
        "_runtime_chunker_type": None,
        "_runtime_chunk_size": None,
        "_runtime_chunk_overlap": None,
    }
    for name, value in runtime_values.items():
        monkeypatch.setattr(store, name, value)


# ── API key validation ─────────────────────────────────────────────────────────

def test_valid_standard_key():
    key = "sk-" + "a" * 48
    assert validate_api_key(key) == key


def test_valid_project_key():
    key = "sk-proj-" + "B" * 40
    assert validate_api_key(key) == key


def test_key_stripped_of_whitespace():
    key = "  sk-" + "x" * 30 + "  "
    result = validate_api_key(key)
    assert not result.startswith(" ")


def test_key_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        validate_api_key("")


def test_key_wrong_prefix_raises():
    with pytest.raises(ValueError, match="format"):
        validate_api_key("pk-" + "a" * 30)


def test_key_too_short_raises():
    with pytest.raises(ValueError, match="format"):
        validate_api_key("sk-short")


def test_key_too_long_raises():
    with pytest.raises(ValueError, match="maximum"):
        validate_api_key("sk-" + "a" * 300)


def test_key_with_special_injection_chars_raises():
    with pytest.raises(ValueError, match="format"):
        validate_api_key("sk-<script>alert(1)</script>")


# ── Model validation ───────────────────────────────────────────────────────────

def test_valid_model():
    assert validate_model("gpt-4o-mini") == "gpt-4o-mini"


def test_all_allowed_models_pass():
    for m in ALLOWED_MODELS:
        assert validate_model(m) == m


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="not in the allowed list"):
        validate_model("gpt-99-turbo-ultra")


def test_empty_model_raises():
    with pytest.raises(ValueError, match="empty"):
        validate_model("")


def test_model_stripped():
    result = validate_model("  gpt-4o  ")
    assert result == "gpt-4o"


# ── Retriever K validation ─────────────────────────────────────────────────────

def test_validate_retriever_k_valid():
    assert validate_retriever_k(4) == 4
    assert validate_retriever_k(1) == 1
    assert validate_retriever_k(20) == 20


def test_validate_retriever_k_rejects_zero():
    with pytest.raises(ValueError, match="between 1 and 20"):
        validate_retriever_k(0)


def test_validate_retriever_k_rejects_above_20():
    with pytest.raises(ValueError, match="between 1 and 20"):
        validate_retriever_k(21)


def test_validate_retriever_k_rejects_negative():
    with pytest.raises(ValueError, match="between 1 and 20"):
        validate_retriever_k(-1)


# ── Similarity score threshold validation ─────────────────────────────────────

def test_validate_similarity_score_threshold_valid():
    assert validate_similarity_score_threshold(0.0) == 0.0
    assert validate_similarity_score_threshold(1.0) == 1.0
    assert validate_similarity_score_threshold(0.7) == 0.7


def test_validate_similarity_score_threshold_rejects_negative():
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        validate_similarity_score_threshold(-0.1)


def test_validate_similarity_score_threshold_rejects_above_one():
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        validate_similarity_score_threshold(1.1)


def test_validate_similarity_score_threshold_rounds_to_4_decimals():
    result = validate_similarity_score_threshold(0.12345678)
    assert result == round(0.12345678, 4)


# ── Max completion tokens validation ──────────────────────────────────────────

def test_validate_max_completion_tokens_valid():
    assert validate_max_completion_tokens(128) == 128
    assert validate_max_completion_tokens(1024) == 1024
    assert validate_max_completion_tokens(4096) == 4096


def test_validate_max_completion_tokens_bounds():
    with pytest.raises(ValueError, match="between 128 and 4096"):
        validate_max_completion_tokens(100)
    with pytest.raises(ValueError, match="between 128 and 4096"):
        validate_max_completion_tokens(5000)


# ── Token budget warning threshold validation ─────────────────────────────────

def test_validate_token_budget_warning_threshold_valid():
    assert validate_token_budget_warning_threshold(0) == 0
    assert validate_token_budget_warning_threshold(800) == 800


def test_validate_token_budget_warning_threshold_rejects_negative():
    with pytest.raises(ValueError, match=">= 0"):
        validate_token_budget_warning_threshold(-1)


# ── Retriever fetch_k validation ──────────────────────────────────────────────

def test_validate_retriever_fetch_k_valid():
    assert validate_retriever_fetch_k(20, 4) == 20
    assert validate_retriever_fetch_k(4, 4) == 4


def test_validate_retriever_fetch_k_rejects_less_than_retriever_k():
    with pytest.raises(ValueError, match="must be >= retriever_k"):
        validate_retriever_fetch_k(2, 4)


def test_validate_retriever_fetch_k_rejects_above_100():
    with pytest.raises(ValueError, match="<= 100"):
        validate_retriever_fetch_k(101, 4)


# ── Max context chunks validation ─────────────────────────────────────────────

def test_validate_max_context_chunks_valid():
    assert validate_max_context_chunks(1) == 1
    assert validate_max_context_chunks(20) == 20


def test_validate_max_context_chunks_rejects_zero():
    with pytest.raises(ValueError, match="between 1 and 20"):
        validate_max_context_chunks(0)


def test_validate_max_context_chunks_rejects_above_20():
    with pytest.raises(ValueError, match="between 1 and 20"):
        validate_max_context_chunks(21)


# ── LangSmith API key validation ──────────────────────────────────────────────

def test_validate_langchain_api_key_valid_ls_prefix():
    key = "ls__" + "a" * 40
    assert validate_langchain_api_key(key) == key


def test_validate_langchain_api_key_valid_lsv2_prefix():
    key = "lsv2_" + "b" * 40
    assert validate_langchain_api_key(key) == key


def test_validate_langchain_api_key_empty_allowed():
    # Empty means "clear / use .env"
    assert validate_langchain_api_key("") == ""


def test_validate_langchain_api_key_rejects_bad_prefix():
    with pytest.raises(ValueError, match="must start with"):
        validate_langchain_api_key("sk-notlangsmith")


def test_validate_langchain_api_key_rejects_too_long():
    with pytest.raises(ValueError, match="maximum length"):
        validate_langchain_api_key("ls__" + "x" * 200)


# ── LangSmith project validation ──────────────────────────────────────────────

def test_validate_langchain_project_valid():
    assert validate_langchain_project("my-project") == "my-project"


def test_validate_langchain_project_strips_whitespace():
    assert validate_langchain_project("  proj  ") == "proj"


def test_validate_langchain_project_rejects_too_long():
    with pytest.raises(ValueError, match="<= 100 characters"):
        validate_langchain_project("x" * 101)


# ── Pinecone validation ───────────────────────────────────────────────────────

def test_validate_pinecone_api_key_valid():
    assert validate_pinecone_api_key("pc-test-key") == "pc-test-key"


def test_validate_pinecone_api_key_rejects_whitespace():
    with pytest.raises(ValueError, match="whitespace"):
        validate_pinecone_api_key("pc test")


def test_validate_pinecone_index_name_valid():
    assert validate_pinecone_index_name("RAG-Prod") == "rag-prod"


def test_validate_pinecone_index_name_rejects_bad_chars():
    with pytest.raises(ValueError, match="lowercase"):
        validate_pinecone_index_name("rag_prod")


def test_validate_pinecone_namespace_allows_empty():
    assert validate_pinecone_namespace("") == ""


def test_validate_pinecone_namespace_rejects_bad_chars():
    with pytest.raises(ValueError, match="namespace"):
        validate_pinecone_namespace("tenant/a")


def test_validate_pinecone_cloud_accepts_aws():
    assert validate_pinecone_cloud("AWS") == "aws"


def test_validate_pinecone_region_valid():
    assert validate_pinecone_region("US-East-1") == "us-east-1"


def test_validate_blob_read_write_token_valid():
    assert validate_blob_read_write_token("vercel_blob_rw_test") == "vercel_blob_rw_test"


def test_validate_blob_read_write_token_rejects_whitespace():
    with pytest.raises(ValueError, match="whitespace"):
        validate_blob_read_write_token("vercel blob token")


# ── Runtime store behaviour ───────────────────────────────────────────────────

def test_apply_and_read_back(monkeypatch):
    # isolate: clear any previously applied key
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    key = "sk-" + "t" * 40
    apply_runtime_settings(api_key=key, model="gpt-4o")

    assert get_effective_model() == "gpt-4o"
    assert get_effective_api_key() == key
    assert is_runtime_key_set() is True


def test_apply_and_read_back_pinecone_settings(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_pinecone_api_key", "")
    monkeypatch.setattr(store, "_runtime_pinecone_index_name", "")

    apply_runtime_settings(
        pinecone_api_key="pc-test-key",
        pinecone_index_name="rag-prod",
    )

    assert get_effective_pinecone_api_key() == "pc-test-key"
    assert get_effective_pinecone_index_name() == "rag-prod"
    assert "****" in get_masked_pinecone_api_key()


def test_apply_and_read_back_blob_token(monkeypatch):
    import os
    import app.runtime.settings_store as store

    monkeypatch.setattr(store, "_runtime_blob_read_write_token", "")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)

    apply_runtime_settings(blob_read_write_token="vercel_blob_rw_test")

    assert get_effective_blob_read_write_token() == "vercel_blob_rw_test"
    assert os.environ["BLOB_READ_WRITE_TOKEN"] == "vercel_blob_rw_test"
    assert "****" in get_masked_blob_read_write_token()


def test_masked_key_hides_secret(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "sk-abcdefghij1234")

    masked = get_masked_api_key()
    assert "abcdefghij1234"[:-4] not in masked  # middle is hidden
    assert masked.endswith("1234")              # only last 4 visible
    assert "****" in masked


def test_env_fallback_when_no_runtime(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    cfg_key = get_effective_api_key()
    # Should return whatever is in the .env / default config
    assert isinstance(cfg_key, str)


def test_apply_none_does_not_overwrite(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "sk-" + "x" * 40)
    monkeypatch.setattr(store, "_runtime_model", "gpt-4o")

    apply_runtime_settings(api_key=None, model="gpt-4")
    assert get_effective_model() == "gpt-4"
    assert "x" * 40 in get_effective_api_key()  # key unchanged


def test_apply_runtime_settings_does_not_clear_vector_store(monkeypatch):
    """Updating settings must NOT discard indexed documents (bug fix for Vercel)."""
    import app.runtime.settings_store as store
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(store, "_runtime_api_key", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    mock_vs = MagicMock()
    # Patch get_vector_store so we can detect if cache_clear is called
    with patch("app.rag.vector_store.get_vector_store") as mock_gvs:
        apply_runtime_settings(api_key="sk-" + "z" * 40, model="gpt-4o-mini")
        # cache_clear must NOT be called — documents survive the settings update
        mock_gvs.cache_clear.assert_not_called()


# ── New accessor tests ────────────────────────────────────────────────────────

def test_get_effective_retriever_k_falls_back_to_config(monkeypatch):
    """When no runtime override is set, returns the config value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_k", None)

    from app.config import get_settings
    expected = get_settings().retriever_k
    assert get_effective_retriever_k() == expected


def test_get_effective_retriever_k_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(retriever_k=8), returns 8."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_k", None)

    apply_runtime_settings(retriever_k=8)
    assert get_effective_retriever_k() == 8

    # Restore
    monkeypatch.setattr(store, "_runtime_retriever_k", None)


def test_get_effective_planner_model_chains_through_fallbacks(monkeypatch):
    """
    Override chain: runtime planner → runtime global → env planner → env global.
    With no runtime values set, should fall back to config.
    """
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_planner_model", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    from app.config import get_settings
    cfg = get_settings()
    # Falls back through env planner (empty by default) to env global
    expected = cfg.planner_model or cfg.llm_model
    assert get_effective_planner_model() == expected


def test_get_effective_planner_model_uses_runtime_planner_override(monkeypatch):
    """Runtime planner_model takes precedence over global model."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_model", "gpt-4o-mini")
    monkeypatch.setattr(store, "_runtime_planner_model", "gpt-4o")

    assert get_effective_planner_model() == "gpt-4o"

    monkeypatch.setattr(store, "_runtime_planner_model", "")
    monkeypatch.setattr(store, "_runtime_model", "")


def test_get_effective_generator_model_uses_global_runtime(monkeypatch):
    """When no per-node override, runtime global model is used."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_generator_model", "")
    monkeypatch.setattr(store, "_runtime_model", "gpt-4")

    assert get_effective_generator_model() == "gpt-4"

    monkeypatch.setattr(store, "_runtime_model", "")


def test_get_effective_similarity_threshold_falls_back(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_similarity_score_threshold", None)

    from app.config import get_settings
    assert get_effective_similarity_score_threshold() == get_settings().similarity_score_threshold


def test_get_effective_retriever_use_mmr_falls_back(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_use_mmr", None)

    from app.config import get_settings
    assert get_effective_retriever_use_mmr() == get_settings().retriever_use_mmr


def test_get_effective_max_completion_tokens_returns_runtime(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)

    apply_runtime_settings(max_completion_tokens=512)
    assert get_effective_max_completion_tokens() == 512

    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)


def test_get_effective_token_budget_warning_threshold_falls_back(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_token_budget_warning_threshold", None)

    from app.config import get_settings
    assert get_effective_token_budget_warning_threshold() == get_settings().token_budget_warning_threshold


def test_get_effective_langchain_tracing_v2_falls_back(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_tracing_v2", None)

    from app.config import get_settings
    assert get_effective_langchain_tracing_v2() == get_settings().langchain_tracing_v2


def test_get_effective_langchain_project_falls_back(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_project", "")

    from app.config import get_settings
    assert get_effective_langchain_project() == get_settings().langchain_project


def test_get_effective_langchain_project_returns_runtime(monkeypatch):
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_project", "my-test-project")

    assert get_effective_langchain_project() == "my-test-project"

    monkeypatch.setattr(store, "_runtime_langchain_project", "")


def test_get_masked_langchain_api_key_returns_empty_when_unset(monkeypatch):
    """When no LangSmith key is set in runtime or env, returns empty string."""
    import app.runtime.settings_store as store
    from unittest.mock import patch
    monkeypatch.setattr(store, "_runtime_langchain_api_key", "")

    # Patch config to have no key
    with patch("app.runtime.settings_store.get_settings") as mock_settings:
        mock_settings.return_value.langchain_api_key = ""
        result = get_masked_langchain_api_key()
    assert result == ""


def test_get_masked_langchain_api_key_masks_runtime_key(monkeypatch):
    """When a LangSmith key is set, it is masked."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_api_key", "ls__abcdef1234")

    masked = get_masked_langchain_api_key()
    assert "****" in masked
    assert masked.endswith("1234")
    assert "abcdef" not in masked

    monkeypatch.setattr(store, "_runtime_langchain_api_key", "")


def test_apply_runtime_settings_resets_agent_singleton(monkeypatch):
    """Agent singleton is reset when model-affecting settings change."""
    import app.agents.rag_agent as agent_mod
    import app.runtime.settings_store as store

    # Set a sentinel value
    agent_mod._AGENT = object()
    monkeypatch.setattr(store, "_runtime_model", "")

    apply_runtime_settings(model="gpt-4o")
    assert agent_mod._AGENT is None

    monkeypatch.setattr(store, "_runtime_model", "")


def test_apply_runtime_settings_no_reset_on_non_model_change(monkeypatch):
    """Agent singleton is NOT reset when only retrieval settings change."""
    import app.agents.rag_agent as agent_mod
    import app.runtime.settings_store as store

    sentinel = object()
    agent_mod._AGENT = sentinel
    monkeypatch.setattr(store, "_runtime_retriever_k", None)

    apply_runtime_settings(retriever_k=8)
    # _AGENT should NOT have been cleared since no model-affecting field changed
    assert agent_mod._AGENT is sentinel

    monkeypatch.setattr(store, "_runtime_retriever_k", None)


# ── Request-scope override paths ──────────────────────────────────────────────

def test_has_request_runtime_settings_true_when_set():
    """has_request_runtime_settings returns True when overrides are bound."""
    from app.runtime.settings_store import set_request_runtime_settings, has_request_runtime_settings
    set_request_runtime_settings({"model": "gpt-4o"})
    try:
        assert has_request_runtime_settings() is True
    finally:
        set_request_runtime_settings(None)


def test_has_request_runtime_settings_false_when_empty():
    """has_request_runtime_settings returns False when no overrides are set."""
    from app.runtime.settings_store import set_request_runtime_settings, has_request_runtime_settings
    set_request_runtime_settings(None)
    assert has_request_runtime_settings() is False


def test_has_guest_runtime_settings_returns_false_for_none_session():
    """has_guest_runtime_settings returns False when session_id is None."""
    from app.runtime.settings_store import has_guest_runtime_settings
    assert has_guest_runtime_settings(None) is False


def test_get_effective_api_key_uses_request_override():
    """get_effective_api_key returns the request-level override key."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_api_key
    set_request_runtime_settings({"api_key": "sk-testrequest1234567890123456789012"})
    try:
        result = get_effective_api_key()
        assert result == "sk-testrequest1234567890123456789012"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_model_uses_request_override():
    """get_effective_model returns the request-level override model."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_model
    set_request_runtime_settings({"model": "gpt-4o-mini"})
    try:
        result = get_effective_model()
        assert result == "gpt-4o-mini"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_embedding_model_uses_request_override():
    """get_effective_embedding_model returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_embedding_model
    set_request_runtime_settings({"embedding_model": "text-embedding-3-large"})
    try:
        result = get_effective_embedding_model()
        assert result == "text-embedding-3-large"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_langchain_api_key_uses_request_override():
    """get_effective_langchain_api_key returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_langchain_api_key
    set_request_runtime_settings({"langchain_api_key": "ls__test-request-key"})
    try:
        result = get_effective_langchain_api_key()
        assert result == "ls__test-request-key"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_pinecone_api_key_uses_request_override():
    """get_effective_pinecone_api_key returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_pinecone_api_key
    set_request_runtime_settings({"pinecone_api_key": "pc-request-key-xyz"})
    try:
        result = get_effective_pinecone_api_key()
        assert result == "pc-request-key-xyz"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_pinecone_index_name_uses_request_override():
    """get_effective_pinecone_index_name returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_pinecone_index_name
    set_request_runtime_settings({"pinecone_index_name": "request-index"})
    try:
        result = get_effective_pinecone_index_name()
        assert result == "request-index"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_pinecone_namespace_uses_request_override():
    """get_effective_pinecone_namespace returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_pinecone_namespace
    set_request_runtime_settings({"pinecone_namespace": "request-ns"})
    try:
        result = get_effective_pinecone_namespace()
        assert result == "request-ns"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_pinecone_cloud_uses_request_override():
    """get_effective_pinecone_cloud returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_pinecone_cloud
    set_request_runtime_settings({"pinecone_cloud": "gcp"})
    try:
        result = get_effective_pinecone_cloud()
        assert result == "gcp"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_pinecone_region_uses_request_override():
    """get_effective_pinecone_region returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_pinecone_region
    set_request_runtime_settings({"pinecone_region": "us-west-2"})
    try:
        result = get_effective_pinecone_region()
        assert result == "us-west-2"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_blob_token_uses_request_override():
    """get_effective_blob_read_write_token returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_blob_read_write_token
    set_request_runtime_settings({"blob_read_write_token": "vercel_blob_rw_requesttoken"})
    try:
        result = get_effective_blob_read_write_token()
        assert result == "vercel_blob_rw_requesttoken"
    finally:
        set_request_runtime_settings(None)


def test_get_effective_retriever_k_uses_request_override():
    """get_effective_retriever_k returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_retriever_k
    set_request_runtime_settings({"retriever_k": 7})
    try:
        result = get_effective_retriever_k()
        assert result == 7
    finally:
        set_request_runtime_settings(None)


def test_get_effective_similarity_threshold_uses_request_override():
    """get_effective_similarity_score_threshold returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_similarity_score_threshold
    set_request_runtime_settings({"similarity_score_threshold": 0.75})
    try:
        result = get_effective_similarity_score_threshold()
        assert result == 0.75
    finally:
        set_request_runtime_settings(None)


def test_get_effective_retriever_use_mmr_uses_request_override():
    """get_effective_retriever_use_mmr returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_retriever_use_mmr
    set_request_runtime_settings({"retriever_use_mmr": True})
    try:
        result = get_effective_retriever_use_mmr()
        assert result is True
    finally:
        set_request_runtime_settings(None)


def test_get_effective_retriever_fetch_k_uses_request_override():
    """get_effective_retriever_fetch_k returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_retriever_fetch_k
    set_request_runtime_settings({"retriever_fetch_k": 15})
    try:
        result = get_effective_retriever_fetch_k()
        assert result == 15
    finally:
        set_request_runtime_settings(None)


def test_get_effective_max_context_chunks_uses_request_override():
    """get_effective_max_context_chunks returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_max_context_chunks
    set_request_runtime_settings({"max_context_chunks": 10})
    try:
        result = get_effective_max_context_chunks()
        assert result == 10
    finally:
        set_request_runtime_settings(None)


def test_get_effective_max_completion_tokens_uses_request_override():
    """get_effective_max_completion_tokens returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_max_completion_tokens
    set_request_runtime_settings({"max_completion_tokens": 2048})
    try:
        result = get_effective_max_completion_tokens()
        assert result == 2048
    finally:
        set_request_runtime_settings(None)


def test_get_effective_retriever_hybrid_bm25_uses_request_override():
    """get_effective_retriever_hybrid_bm25 returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_retriever_hybrid_bm25
    set_request_runtime_settings({"retriever_hybrid_bm25": True})
    try:
        result = get_effective_retriever_hybrid_bm25()
        assert result is True
    finally:
        set_request_runtime_settings(None)


def test_get_effective_relevance_grader_enabled_uses_request_override():
    """get_effective_relevance_grader_enabled returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_relevance_grader_enabled
    set_request_runtime_settings({"relevance_grader_enabled": True})
    try:
        result = get_effective_relevance_grader_enabled()
        assert result is True
    finally:
        set_request_runtime_settings(None)


def test_get_effective_reranker_type_uses_request_override():
    """get_effective_reranker_type returns request-level override."""
    from app.runtime.settings_store import set_request_runtime_settings, get_effective_reranker_type
    set_request_runtime_settings({"reranker_type": "llm-judge"})
    try:
        result = get_effective_reranker_type()
        assert result == "llm-judge"
    finally:
        set_request_runtime_settings(None)


# ── Guest-scope override paths ────────────────────────────────────────────────

def test_guest_value_returns_default_when_not_guest_role():
    """_guest_value returns the default when the active role is not guest."""
    from app.runtime.settings_store import set_runtime_scope, _guest_value
    set_runtime_scope("admin", None)
    result = _guest_value("api_key", "fallback")
    assert result == "fallback"
    # Cleanup
    set_runtime_scope(None, None)


def test_guest_value_returns_value_when_guest_has_settings():
    """_guest_value returns the stored value when guest session has settings."""
    from app.runtime.settings_store import (
        set_runtime_scope, apply_runtime_settings, _guest_value
    )
    session_id = "test-guest-session-001"
    apply_runtime_settings(api_key="sk-guestkey1234567890123456789012", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    try:
        result = _guest_value("api_key", "")
        assert result == "sk-guestkey1234567890123456789012"
    finally:
        set_runtime_scope(None, None)
        # Clean up guest settings
        import app.runtime.settings_store as store
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_get_effective_api_key_uses_guest_override():
    """get_effective_api_key returns guest session override when no request override."""
    from app.runtime.settings_store import (
        set_runtime_scope, apply_runtime_settings, get_effective_api_key,
        set_request_runtime_settings
    )
    session_id = "test-guest-session-002"
    apply_runtime_settings(api_key="sk-guestoverride1234567890123456", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    try:
        result = get_effective_api_key()
        assert result == "sk-guestoverride1234567890123456"
    finally:
        set_runtime_scope(None, None)
        import app.runtime.settings_store as store
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_get_effective_model_uses_guest_override():
    """get_effective_model returns guest session model when no request override."""
    from app.runtime.settings_store import (
        set_runtime_scope, apply_runtime_settings, get_effective_model,
        set_request_runtime_settings
    )
    import app.runtime.settings_store as store
    session_id = "test-guest-session-003"
    apply_runtime_settings(model="gpt-4o", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev_model = store._runtime_model
    store._runtime_model = ""
    try:
        result = get_effective_model()
        assert result == "gpt-4o"
    finally:
        store._runtime_model = prev_model
        set_runtime_scope(None, None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_get_effective_pinecone_api_key_uses_guest_override():
    """get_effective_pinecone_api_key returns guest session override."""
    from app.runtime.settings_store import (
        set_runtime_scope, apply_runtime_settings, get_effective_pinecone_api_key,
        set_request_runtime_settings
    )
    import app.runtime.settings_store as store
    session_id = "test-guest-session-004"
    apply_runtime_settings(pinecone_api_key="pc-guestpineconekey", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_api_key
    store._runtime_pinecone_api_key = ""
    try:
        result = get_effective_pinecone_api_key()
        assert result == "pc-guestpineconekey"
    finally:
        store._runtime_pinecone_api_key = prev
        set_runtime_scope(None, None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_has_guest_runtime_settings_true_after_apply():
    """has_guest_runtime_settings is True after applying settings for a session."""
    from app.runtime.settings_store import (
        apply_runtime_settings, has_guest_runtime_settings
    )
    import app.runtime.settings_store as store
    session_id = "test-guest-session-005"
    apply_runtime_settings(model="gpt-4o", scope_session_id=session_id)
    try:
        assert has_guest_runtime_settings(session_id) is True
    finally:
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


# ── Validator edge cases ──────────────────────────────────────────────────────

def test_validate_embedding_model_empty_raises():
    """validate_embedding_model raises on empty string."""
    from app.runtime.settings_store import validate_embedding_model
    with pytest.raises(ValueError, match="empty"):
        validate_embedding_model("")


def test_validate_embedding_model_unknown_raises():
    """validate_embedding_model raises on an unknown model name."""
    from app.runtime.settings_store import validate_embedding_model
    with pytest.raises(ValueError, match="not in the allowed list"):
        validate_embedding_model("bad-embedding-model-xyz")


def test_validate_pinecone_api_key_empty_raises():
    """validate_pinecone_api_key raises on empty string."""
    with pytest.raises(ValueError, match="empty"):
        validate_pinecone_api_key("")


def test_validate_pinecone_api_key_with_whitespace_raises():
    """validate_pinecone_api_key raises when key contains spaces."""
    with pytest.raises(ValueError, match="whitespace"):
        validate_pinecone_api_key("pc key with spaces")


def test_validate_pinecone_api_key_too_long_raises():
    """validate_pinecone_api_key raises when key exceeds max length."""
    with pytest.raises(ValueError, match="maximum length"):
        validate_pinecone_api_key("pc-" + "x" * 300)


def test_validate_pinecone_cloud_invalid_raises():
    """validate_pinecone_cloud raises for unsupported cloud providers."""
    with pytest.raises(ValueError, match="pinecone_cloud"):
        validate_pinecone_cloud("azure-invalid")


def test_validate_pinecone_cloud_valid():
    """validate_pinecone_cloud accepts valid providers."""
    from app.runtime.settings_store import validate_pinecone_cloud
    assert validate_pinecone_cloud("aws") == "aws"
    assert validate_pinecone_cloud("GCP") == "gcp"
    assert validate_pinecone_cloud("azure") == "azure"


def test_validate_pinecone_region_empty_raises():
    """validate_pinecone_region raises on empty string."""
    with pytest.raises(ValueError, match="empty"):
        validate_pinecone_region("")


def test_validate_pinecone_region_bad_chars_raises():
    """validate_pinecone_region raises when region contains bad characters."""
    with pytest.raises(ValueError, match="hyphens"):
        validate_pinecone_region("bad region!")


def test_validate_pinecone_region_too_long_raises():
    """validate_pinecone_region raises when region exceeds max length."""
    with pytest.raises(ValueError, match="<="):
        validate_pinecone_region("us-" + "x" * 50)


def test_validate_pinecone_index_name_empty_raises():
    """validate_pinecone_index_name raises on empty string."""
    from app.runtime.settings_store import validate_pinecone_index_name
    with pytest.raises(ValueError, match="empty"):
        validate_pinecone_index_name("")


def test_validate_pinecone_index_name_too_long_raises():
    """validate_pinecone_index_name raises when name exceeds 45 chars."""
    from app.runtime.settings_store import validate_pinecone_index_name
    with pytest.raises(ValueError, match="45"):
        validate_pinecone_index_name("x" * 46)


def test_validate_pinecone_namespace_too_long_raises():
    """validate_pinecone_namespace raises when namespace exceeds 100 chars."""
    from app.runtime.settings_store import validate_pinecone_namespace
    with pytest.raises(ValueError, match="100"):
        validate_pinecone_namespace("n" * 101)


def test_validate_pinecone_namespace_bad_chars_raises():
    """validate_pinecone_namespace raises when namespace contains invalid chars."""
    from app.runtime.settings_store import validate_pinecone_namespace
    with pytest.raises(ValueError, match="letters"):
        validate_pinecone_namespace("bad namespace!")


# ── apply_runtime_settings cache-invalidation paths ──────────────────────────

def test_apply_runtime_settings_embedding_model_clears_vector_store_cache(monkeypatch):
    """Setting embedding_model should clear the vector store cache and doc cache."""
    import app.rag.vector_store as vs_mod
    import app.runtime.settings_store as store

    cache_clear_called = []
    invalidate_called = []

    monkeypatch.setattr(vs_mod.get_vector_store, "cache_clear", lambda: cache_clear_called.append(1))
    monkeypatch.setattr(vs_mod, "invalidate_doc_cache", lambda: invalidate_called.append(1))
    monkeypatch.setattr(store, "_runtime_embedding_model", "")

    apply_runtime_settings(embedding_model="text-embedding-3-large")

    assert len(cache_clear_called) > 0, "cache_clear should have been called"
    assert len(invalidate_called) > 0, "invalidate_doc_cache should have been called"

    # Cleanup
    monkeypatch.setattr(store, "_runtime_embedding_model", "")


def test_apply_runtime_settings_pinecone_key_clears_vector_store_cache(monkeypatch):
    """Setting pinecone_api_key should clear the vector store cache."""
    import app.rag.vector_store as vs_mod
    import app.runtime.settings_store as store

    cache_clear_called = []
    invalidate_called = []

    monkeypatch.setattr(vs_mod.get_vector_store, "cache_clear", lambda: cache_clear_called.append(1))
    monkeypatch.setattr(vs_mod, "invalidate_doc_cache", lambda: invalidate_called.append(1))
    monkeypatch.setattr(store, "_runtime_pinecone_api_key", "")

    apply_runtime_settings(pinecone_api_key="pc-new-key-for-cache-clear")

    assert len(cache_clear_called) > 0, "cache_clear should have been called for pinecone key change"
    assert len(invalidate_called) > 0, "invalidate_doc_cache should have been called for pinecone key change"

    # Cleanup
    monkeypatch.setattr(store, "_runtime_pinecone_api_key", "")


def test_apply_runtime_settings_pinecone_index_name_clears_vector_store_cache(monkeypatch):
    """Setting pinecone_index_name should trigger cache invalidation."""
    import app.rag.vector_store as vs_mod
    import app.runtime.settings_store as store

    cache_clear_called = []
    invalidate_called = []

    monkeypatch.setattr(vs_mod.get_vector_store, "cache_clear", lambda: cache_clear_called.append(1))
    monkeypatch.setattr(vs_mod, "invalidate_doc_cache", lambda: invalidate_called.append(1))
    monkeypatch.setattr(store, "_runtime_pinecone_index_name", "")

    apply_runtime_settings(pinecone_index_name="new-index")

    assert len(cache_clear_called) > 0
    assert len(invalidate_called) > 0

    monkeypatch.setattr(store, "_runtime_pinecone_index_name", "")


def test_apply_runtime_settings_no_reset_on_max_completion_tokens(monkeypatch):
    """Agent singleton is NOT reset when max_completion_tokens changes.

    Nodes read max_completion_tokens at call time via get_effective_max_completion_tokens(),
    so the compiled graph does not need to be rebuilt (P5 optimisation).
    """
    import app.agents.rag_agent as agent_mod
    import app.runtime.settings_store as store

    sentinel = object()
    agent_mod._AGENT = sentinel
    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)

    apply_runtime_settings(max_completion_tokens=256)
    assert agent_mod._AGENT is sentinel  # unchanged

    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)


def test_production_ignores_provider_env_fallbacks(monkeypatch):
    import app.runtime.settings_store as store

    reset_runtime_settings(monkeypatch)
    monkeypatch.setattr(store, "get_settings", lambda: production_settings())

    assert get_effective_api_key() == ""
    assert get_effective_pinecone_api_key() == ""
    assert get_effective_blob_read_write_token() == ""
    assert get_effective_langchain_api_key() == ""
    assert get_masked_api_key() == ""
    assert get_masked_pinecone_api_key() == ""
    assert get_masked_blob_read_write_token() == ""
    assert get_masked_langchain_api_key() == ""


def test_production_ignores_env_model_and_token_cost_controls(monkeypatch):
    import app.runtime.settings_store as store

    reset_runtime_settings(monkeypatch)
    monkeypatch.setattr(store, "get_settings", lambda: production_settings())

    assert get_effective_model() == "gpt-4o-mini"
    assert get_effective_embedding_model() == "text-embedding-3-small"
    assert get_effective_planner_model() == "gpt-4o-mini"
    assert get_effective_generator_model() == "gpt-4o-mini"
    assert get_effective_validator_model() == "gpt-4o-mini"
    assert get_effective_retriever_k() == 4
    assert get_effective_retriever_fetch_k() == 20
    assert get_effective_max_context_chunks() == 4
    assert get_effective_max_completion_tokens() == 1024
    assert get_effective_token_budget_warning_threshold() == 800
    assert get_effective_langchain_tracing_v2() is False
    assert get_effective_langchain_project() == "agenticai-rag-poc"


def test_production_runtime_settings_override_safe_defaults(monkeypatch):
    import app.runtime.settings_store as store

    reset_runtime_settings(monkeypatch)
    monkeypatch.setattr(store, "get_settings", lambda: production_settings())

    apply_runtime_settings(
        api_key="sk-" + "r" * 40,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        planner_model="gpt-4o",
        generator_model="gpt-4",
        validator_model="gpt-4-turbo",
        retriever_k=8,
        retriever_fetch_k=32,
        max_context_chunks=8,
        max_completion_tokens=2048,
        token_budget_warning_threshold=1600,
        langchain_tracing_v2=True,
        langchain_api_key="ls__runtime-key",
        langchain_project="runtime-project",
        pinecone_api_key="pc-runtime-key",
        blob_read_write_token="vercel_blob_rw_runtime",
    )

    assert get_effective_api_key() == "sk-" + "r" * 40
    assert get_effective_model() == "gpt-4o"
    assert get_effective_embedding_model() == "text-embedding-3-large"
    assert get_effective_planner_model() == "gpt-4o"
    assert get_effective_generator_model() == "gpt-4"
    assert get_effective_validator_model() == "gpt-4-turbo"
    assert get_effective_retriever_k() == 8
    assert get_effective_retriever_fetch_k() == 32
    assert get_effective_max_context_chunks() == 8
    assert get_effective_max_completion_tokens() == 2048
    assert get_effective_token_budget_warning_threshold() == 1600
    assert get_effective_langchain_tracing_v2() is True
    assert get_effective_langchain_api_key() == "ls__runtime-key"
    assert get_effective_langchain_project() == "runtime-project"
    assert get_effective_pinecone_api_key() == "pc-runtime-key"
    assert get_effective_blob_read_write_token() == "vercel_blob_rw_runtime"


# ── Pipeline feature flag validator tests ─────────────────────────────────────

def test_validate_reranker_type_valid():
    assert validate_reranker_type("none") == "none"
    assert validate_reranker_type("cross-encoder") == "cross-encoder"


def test_validate_reranker_type_case_insensitive():
    assert validate_reranker_type("None") == "none"
    assert validate_reranker_type("Cross-Encoder") == "cross-encoder"


def test_validate_reranker_type_invalid():
    with pytest.raises(ValueError, match="reranker_type must be one of"):
        validate_reranker_type("unknown-reranker")


def test_validate_chunker_type_valid():
    assert validate_chunker_type("recursive") == "recursive"
    assert validate_chunker_type("semantic") == "semantic"


def test_validate_chunker_type_case_insensitive():
    assert validate_chunker_type("Recursive") == "recursive"
    assert validate_chunker_type("Semantic") == "semantic"


def test_validate_chunker_type_invalid():
    with pytest.raises(ValueError, match="chunker_type must be one of"):
        validate_chunker_type("ngram")


def test_validate_chunk_size_valid():
    assert validate_chunk_size(100) == 100
    assert validate_chunk_size(800) == 800
    assert validate_chunk_size(4000) == 4000


def test_validate_chunk_size_too_small():
    with pytest.raises(ValueError, match="between 100 and 4000"):
        validate_chunk_size(99)


def test_validate_chunk_size_too_large():
    with pytest.raises(ValueError, match="between 100 and 4000"):
        validate_chunk_size(4001)


def test_validate_chunk_overlap_valid():
    assert validate_chunk_overlap(100, 800) == 100
    assert validate_chunk_overlap(0, 800) == 0


def test_validate_chunk_overlap_negative():
    with pytest.raises(ValueError, match=">= 0"):
        validate_chunk_overlap(-1, 800)


def test_validate_chunk_overlap_gte_chunk_size():
    with pytest.raises(ValueError, match="must be less than chunk_size"):
        validate_chunk_overlap(800, 800)


def test_validate_chunk_overlap_exceeds_chunk_size():
    with pytest.raises(ValueError, match="must be less than chunk_size"):
        validate_chunk_overlap(900, 800)


def test_allowed_reranker_types_frozenset():
    assert "none" in ALLOWED_RERANKER_TYPES
    assert "cross-encoder" in ALLOWED_RERANKER_TYPES


# ── Judge model validation ─────────────────────────────────────────────────────

def test_validate_reranker_judge_model_valid():
    assert validate_reranker_judge_model("gpt-4.1-mini") == "gpt-4.1-mini"
    assert validate_reranker_judge_model("gpt-4.1-nano") == "gpt-4.1-nano"
    assert validate_reranker_judge_model("gpt-4.1") == "gpt-4.1"


def test_validate_reranker_judge_model_strips_whitespace():
    assert validate_reranker_judge_model("  gpt-4.1-mini  ") == "gpt-4.1-mini"


def test_validate_reranker_judge_model_empty_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_reranker_judge_model("")


def test_validate_reranker_judge_model_invalid_raises():
    with pytest.raises(ValueError, match="not allowed"):
        validate_reranker_judge_model("gpt-5-turbo")


def test_validate_reranker_judge_model_pipeline_models_rejected():
    """Pipeline models must not be allowed as judge models — circular reasoning guard."""
    with pytest.raises(ValueError, match="not allowed"):
        validate_reranker_judge_model("gpt-4o-mini")
    with pytest.raises(ValueError, match="not allowed"):
        validate_reranker_judge_model("gpt-4o")


def test_allowed_judge_models_frozenset():
    assert "gpt-4.1-mini" in ALLOWED_JUDGE_MODELS
    assert "gpt-4.1-nano" in ALLOWED_JUDGE_MODELS
    assert "gpt-4.1" in ALLOWED_JUDGE_MODELS
    # Must not overlap with pipeline-selectable models (circular reasoning guard)
    assert "gpt-4o-mini" not in ALLOWED_JUDGE_MODELS
    assert "gpt-4o" not in ALLOWED_JUDGE_MODELS


def test_get_effective_reranker_judge_model_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config default (gpt-4.1-mini)."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_judge_model", "")
    assert get_effective_reranker_judge_model() == "gpt-4.1-mini"


def test_get_effective_reranker_judge_model_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(reranker_judge_model='gpt-4.1-nano'), returns that model."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_judge_model", "")
    apply_runtime_settings(reranker_judge_model="gpt-4.1-nano")
    assert get_effective_reranker_judge_model() == "gpt-4.1-nano"
    monkeypatch.setattr(store, "_runtime_reranker_judge_model", "")


def test_allowed_chunker_types_frozenset():
    assert "recursive" in ALLOWED_CHUNKER_TYPES
    assert "semantic" in ALLOWED_CHUNKER_TYPES


# ── Pipeline feature flag accessor tests ──────────────────────────────────────

def test_get_effective_retriever_hybrid_bm25_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)

    from app.config import get_settings
    assert get_effective_retriever_hybrid_bm25() == get_settings().retriever_hybrid_bm25


def test_get_effective_retriever_hybrid_bm25_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(retriever_hybrid_bm25=False), returns False."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)

    apply_runtime_settings(retriever_hybrid_bm25=False)
    assert get_effective_retriever_hybrid_bm25() is False

    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)


def test_get_effective_relevance_grader_enabled_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)

    from app.config import get_settings
    assert get_effective_relevance_grader_enabled() == get_settings().relevance_grader_enabled


def test_get_effective_relevance_grader_enabled_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(relevance_grader_enabled=True), returns True."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)

    apply_runtime_settings(relevance_grader_enabled=True)
    assert get_effective_relevance_grader_enabled() is True

    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)


def test_get_effective_reranker_type_falls_back_to_smart_default(monkeypatch):
    """When no runtime override and no RERANKER_TYPE env var, uses smart default."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_type", None)
    monkeypatch.delenv("RERANKER_TYPE", raising=False)

    expected = store._smart_default_reranker_type()
    assert get_effective_reranker_type() == expected


def test_get_effective_reranker_type_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(reranker_type='cross-encoder'), returns 'cross-encoder'."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_type", None)

    apply_runtime_settings(reranker_type="cross-encoder")
    assert get_effective_reranker_type() == "cross-encoder"

    monkeypatch.setattr(store, "_runtime_reranker_type", None)


def test_get_effective_chunker_type_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunker_type", None)

    from app.config import get_settings
    assert get_effective_chunker_type() == get_settings().chunker_type


def test_get_effective_chunker_type_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(chunker_type='semantic'), returns 'semantic'."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunker_type", None)

    apply_runtime_settings(chunker_type="semantic")
    assert get_effective_chunker_type() == "semantic"

    monkeypatch.setattr(store, "_runtime_chunker_type", None)


def test_get_effective_chunk_size_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)

    from app.config import get_settings
    assert get_effective_chunk_size() == get_settings().chunk_size


def test_get_effective_chunk_size_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(chunk_size=400), returns 400."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)

    apply_runtime_settings(chunk_size=400)
    assert get_effective_chunk_size() == 400

    monkeypatch.setattr(store, "_runtime_chunk_size", None)


def test_get_effective_chunk_overlap_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)

    from app.config import get_settings
    assert get_effective_chunk_overlap() == get_settings().chunk_overlap


def test_get_effective_chunk_overlap_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(chunk_overlap=50), returns 50."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)

    apply_runtime_settings(chunk_overlap=50)
    assert get_effective_chunk_overlap() == 50

    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)


def test_pipeline_flags_do_not_reset_agent_singleton(monkeypatch):
    """Pipeline flag changes must NOT reset the compiled agent graph."""
    import app.agents.rag_agent as agent_mod
    import app.runtime.settings_store as store

    sentinel = object()
    agent_mod._AGENT = sentinel
    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)
    monkeypatch.setattr(store, "_runtime_reranker_type", None)

    apply_runtime_settings(
        retriever_hybrid_bm25=True,
        relevance_grader_enabled=True,
        reranker_type="none",
    )
    assert agent_mod._AGENT is sentinel  # graph must NOT be cleared

    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)
    monkeypatch.setattr(store, "_runtime_reranker_type", None)


# ── validate_blob_read_write_token edge cases ─────────────────────────────────

def test_validate_blob_read_write_token_empty_raises():
    """validate_blob_read_write_token raises on empty string."""
    with pytest.raises(ValueError, match="empty"):
        validate_blob_read_write_token("")


def test_validate_blob_read_write_token_too_long_raises():
    """validate_blob_read_write_token raises when token exceeds 500 chars."""
    with pytest.raises(ValueError, match="maximum length"):
        validate_blob_read_write_token("t" * 501)


# ── _guest_value with guest role but no session_id (line 148) ─────────────────

def test_guest_value_returns_default_when_guest_but_no_session_id():
    """_guest_value returns default when role is guest but session_id is None."""
    from app.runtime.settings_store import _guest_value
    set_runtime_scope("guest", None)
    try:
        result = _guest_value("api_key", "my-default")
        assert result == "my-default"
    finally:
        set_runtime_scope(None, None)


# ── Guest scope falls through to env/runtime (lines 403, 416, 427, etc.) ─────

def test_get_effective_api_key_guest_scope_no_guest_settings():
    """When guest scope active but no guest settings, falls through to env default."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-001"
    # Ensure no guest settings exist for this session
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    try:
        # Should not raise; returns env fallback (may be empty string in test env)
        result = get_effective_api_key()
        assert isinstance(result, str)
    finally:
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_model_guest_scope_no_guest_settings():
    """When guest scope active but no guest settings, falls through to safe default."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-002"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev_model = store._runtime_model
    store._runtime_model = ""
    try:
        result = get_effective_model()
        assert isinstance(result, str)
        assert len(result) > 0  # always returns a model name
    finally:
        store._runtime_model = prev_model
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_embedding_model_guest_scope_no_guest_settings():
    """When guest scope active but no guest settings, returns safe default model."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-003"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_embedding_model
    store._runtime_embedding_model = ""
    try:
        result = get_effective_embedding_model()
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        store._runtime_embedding_model = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_pinecone_api_key_guest_scope_no_guest_settings():
    """get_effective_pinecone_api_key returns runtime/env value when guest has no settings."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-004"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_api_key
    store._runtime_pinecone_api_key = "pc-runtime-guest-fallthrough"
    try:
        result = get_effective_pinecone_api_key()
        assert result == "pc-runtime-guest-fallthrough"
    finally:
        store._runtime_pinecone_api_key = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_pinecone_index_name_guest_scope_no_guest_settings():
    """get_effective_pinecone_index_name falls through to runtime when guest has no settings."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-005"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_index_name
    store._runtime_pinecone_index_name = "fallthrough-index"
    try:
        result = get_effective_pinecone_index_name()
        assert result == "fallthrough-index"
    finally:
        store._runtime_pinecone_index_name = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_pinecone_namespace_guest_scope_no_guest_settings():
    """get_effective_pinecone_namespace falls through to runtime when guest has no settings."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-006"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_namespace
    store._runtime_pinecone_namespace = "fallthrough-ns"
    try:
        result = get_effective_pinecone_namespace()
        assert result == "fallthrough-ns"
    finally:
        store._runtime_pinecone_namespace = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_pinecone_cloud_guest_scope_no_guest_settings():
    """get_effective_pinecone_cloud falls through to runtime when guest has no settings."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-007"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_cloud
    store._runtime_pinecone_cloud = "gcp"
    try:
        result = get_effective_pinecone_cloud()
        assert result == "gcp"
    finally:
        store._runtime_pinecone_cloud = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_pinecone_region_guest_scope_no_guest_settings():
    """get_effective_pinecone_region falls through to runtime when guest has no settings."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-008"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_region
    store._runtime_pinecone_region = "us-west-1"
    try:
        result = get_effective_pinecone_region()
        assert result == "us-west-1"
    finally:
        store._runtime_pinecone_region = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_blob_token_guest_scope_no_guest_settings():
    """get_effective_blob_read_write_token falls through to runtime when guest has no settings."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-fallthrough-009"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_blob_read_write_token
    store._runtime_blob_read_write_token = "vercel_blob_rw_fallthrough"
    try:
        result = get_effective_blob_read_write_token()
        assert result == "vercel_blob_rw_fallthrough"
    finally:
        store._runtime_blob_read_write_token = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_effective_blob_token_uses_guest_override():
    """get_effective_blob_read_write_token returns guest session blob token."""
    import app.runtime.settings_store as store
    session_id = "guest-scope-blob-010"
    apply_runtime_settings(blob_read_write_token="vercel_blob_rw_guestsession", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_blob_read_write_token
    store._runtime_blob_read_write_token = ""
    try:
        result = get_effective_blob_read_write_token()
        assert result == "vercel_blob_rw_guestsession"
    finally:
        store._runtime_blob_read_write_token = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_apply_runtime_settings_guest_scope_embedding_model_clears_cache(monkeypatch):
    """When applying guest-scoped settings with embedding_model, cache is cleared."""
    import app.rag.vector_store as vs_mod
    import app.runtime.settings_store as store

    cache_clear_called = []
    invalidate_called = []

    monkeypatch.setattr(vs_mod.get_vector_store, "cache_clear", lambda: cache_clear_called.append(1))
    monkeypatch.setattr(vs_mod, "invalidate_doc_cache", lambda: invalidate_called.append(1))

    session_id = "guest-embedding-cache-011"
    apply_runtime_settings(embedding_model="text-embedding-3-small", scope_session_id=session_id)

    assert len(cache_clear_called) > 0
    assert len(invalidate_called) > 0

    # Cleanup
    store._guest_runtime_settings.pop(session_id, None)


def test_apply_runtime_settings_guest_scope_pinecone_settings_clears_cache(monkeypatch):
    """When applying guest-scoped Pinecone settings, cache is cleared."""
    import app.rag.vector_store as vs_mod
    import app.runtime.settings_store as store

    cache_clear_called = []
    invalidate_called = []

    monkeypatch.setattr(vs_mod.get_vector_store, "cache_clear", lambda: cache_clear_called.append(1))
    monkeypatch.setattr(vs_mod, "invalidate_doc_cache", lambda: invalidate_called.append(1))

    session_id = "guest-pinecone-cache-012"
    apply_runtime_settings(pinecone_api_key="pc-guestcache", scope_session_id=session_id)

    assert len(cache_clear_called) > 0
    assert len(invalidate_called) > 0

    # Cleanup
    store._guest_runtime_settings.pop(session_id, None)


# ── validate_embedding_model valid model returns value (line 224) ─────────────

def test_validate_embedding_model_valid_returns_model():
    """validate_embedding_model returns the model name when it is valid."""
    from app.runtime.settings_store import validate_embedding_model, ALLOWED_EMBEDDING_MODELS
    for model in ALLOWED_EMBEDDING_MODELS:
        assert validate_embedding_model(model) == model


# ── Guest Pinecone overrides returning actual value (lines 682, 696, etc.) ────

def test_get_effective_pinecone_index_name_uses_guest_override():
    """get_effective_pinecone_index_name returns guest session override when set."""
    import app.runtime.settings_store as store
    session_id = "guest-pinecone-idx-013"
    apply_runtime_settings(pinecone_index_name="guest-idx", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_index_name
    store._runtime_pinecone_index_name = ""
    try:
        result = get_effective_pinecone_index_name()
        assert result == "guest-idx"
    finally:
        store._runtime_pinecone_index_name = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_get_effective_pinecone_namespace_uses_guest_override():
    """get_effective_pinecone_namespace returns guest session override when set."""
    import app.runtime.settings_store as store
    session_id = "guest-pinecone-ns-014"
    apply_runtime_settings(pinecone_namespace="guest-ns", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_namespace
    store._runtime_pinecone_namespace = ""
    try:
        result = get_effective_pinecone_namespace()
        assert result == "guest-ns"
    finally:
        store._runtime_pinecone_namespace = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_get_effective_pinecone_cloud_uses_guest_override():
    """get_effective_pinecone_cloud returns guest session override when set."""
    import app.runtime.settings_store as store
    session_id = "guest-pinecone-cloud-015"
    apply_runtime_settings(pinecone_cloud="aws", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_cloud
    store._runtime_pinecone_cloud = ""
    try:
        result = get_effective_pinecone_cloud()
        assert result == "aws"
    finally:
        store._runtime_pinecone_cloud = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_get_effective_pinecone_region_uses_guest_override():
    """get_effective_pinecone_region returns guest session override when set."""
    import app.runtime.settings_store as store
    session_id = "guest-pinecone-region-016"
    apply_runtime_settings(pinecone_region="eu-west-1", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_region
    store._runtime_pinecone_region = ""
    try:
        result = get_effective_pinecone_region()
        assert result == "eu-west-1"
    finally:
        store._runtime_pinecone_region = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


# ── is_runtime_pinecone_key_set guest paths (lines 749, 751, 754) ─────────────

def test_is_runtime_pinecone_key_set_true_via_request_override():
    """is_runtime_pinecone_key_set returns True when request override has a key."""
    from app.runtime.settings_store import is_runtime_pinecone_key_set
    set_request_runtime_settings({"pinecone_api_key": "pc-requestkey"})
    try:
        assert is_runtime_pinecone_key_set() is True
    finally:
        set_request_runtime_settings(None)


def test_is_runtime_pinecone_key_set_true_via_guest_override():
    """is_runtime_pinecone_key_set returns True when guest session has a key."""
    from app.runtime.settings_store import is_runtime_pinecone_key_set
    import app.runtime.settings_store as store
    session_id = "guest-pinecone-isset-017"
    apply_runtime_settings(pinecone_api_key="pc-guestsetkey", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    try:
        assert is_runtime_pinecone_key_set() is True
    finally:
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


def test_is_runtime_pinecone_key_set_guest_scope_checks_runtime():
    """is_runtime_pinecone_key_set checks _runtime_pinecone_api_key in guest scope."""
    from app.runtime.settings_store import is_runtime_pinecone_key_set
    import app.runtime.settings_store as store
    session_id = "guest-pinecone-isset-018"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_pinecone_api_key
    store._runtime_pinecone_api_key = "pc-runtime-for-guest"
    try:
        assert is_runtime_pinecone_key_set() is True
    finally:
        store._runtime_pinecone_api_key = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


# ── get_masked_api_key guest scope paths (lines 443-444, 451-452) ─────────────

def test_get_masked_api_key_guest_scope_returns_string():
    """get_masked_api_key in guest scope without guest settings returns a string."""
    import app.runtime.settings_store as store
    session_id = "guest-masked-key-019"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_api_key
    store._runtime_api_key = ""
    try:
        result = get_masked_api_key()
        assert isinstance(result, str)
    finally:
        store._runtime_api_key = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


def test_get_masked_api_key_request_override_shows_masked():
    """get_masked_api_key shows masked request-level key."""
    set_request_runtime_settings({"api_key": "sk-requestmasktest12345678901234"})
    try:
        result = get_masked_api_key()
        assert "****" in result
        assert result.endswith("1234")
    finally:
        set_request_runtime_settings(None)


def test_get_masked_api_key_guest_override_shows_masked():
    """get_masked_api_key shows masked guest-level key."""
    import app.runtime.settings_store as store
    session_id = "guest-masked-key-020"
    apply_runtime_settings(api_key="sk-guestmasktest12345678901234", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    try:
        result = get_masked_api_key()
        assert "****" in result
        assert result.endswith("1234")
    finally:
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


# ── Smart default reranker / RERANKER_TYPE env var (lines 880, 883, 897) ──────

def test_smart_default_reranker_returns_llm_judge_on_vercel(monkeypatch):
    """_smart_default_reranker_type returns 'llm-judge' when VERCEL env is set."""
    import app.runtime.settings_store as store
    monkeypatch.setenv("VERCEL", "1")
    result = store._smart_default_reranker_type()
    assert result == "llm-judge"


def test_get_effective_reranker_type_uses_env_var(monkeypatch):
    """get_effective_reranker_type returns the RERANKER_TYPE env var value."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_type", None)
    monkeypatch.setenv("RERANKER_TYPE", "none")
    set_request_runtime_settings(None)
    result = get_effective_reranker_type()
    assert result == "none"
    monkeypatch.setattr(store, "_runtime_reranker_type", None)


# ── LangSmith tracing warning (line 1068) ─────────────────────────────────────

def test_apply_runtime_settings_langsmith_tracing_without_key_does_not_raise(monkeypatch):
    """apply_runtime_settings completes without raising when tracing=True but no API key."""
    import app.runtime.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_tracing_v2", None)
    monkeypatch.setattr(store, "_runtime_langchain_api_key", "")

    from unittest.mock import patch
    with patch("app.runtime.settings_store.get_settings") as mock_settings:
        mock_settings.return_value.langchain_tracing_v2 = False
        mock_settings.return_value.langchain_api_key = ""
        mock_settings.return_value.langchain_project = "test-project"
        mock_settings.return_value.app_env = "test"
        mock_settings.return_value.openai_api_key = "sk-test"
        # Set tracing=True but no API key should trigger the warning log branch
        apply_runtime_settings(langchain_tracing_v2=True)

    monkeypatch.setattr(store, "_runtime_langchain_tracing_v2", None)
    monkeypatch.setattr(store, "_runtime_langchain_api_key", "")


# ── is_runtime_key_set guest and request paths (lines 459, 463) ──────────────

def test_is_runtime_key_set_true_via_request_override():
    """is_runtime_key_set returns True when request override has a key."""
    set_request_runtime_settings({"api_key": "sk-requestkeyisset1234567890abcde"})
    try:
        assert is_runtime_key_set() is True
    finally:
        set_request_runtime_settings(None)


def test_is_runtime_key_set_false_in_guest_scope_without_key(monkeypatch):
    """is_runtime_key_set returns False in guest scope when no API key is set."""
    import app.runtime.settings_store as store
    session_id = "guest-key-not-set-021"
    store._guest_runtime_settings.pop(session_id, None)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_api_key
    store._runtime_api_key = ""
    try:
        # No guest settings, no request override — guest scope returns False
        result = is_runtime_key_set()
        assert result is False
    finally:
        store._runtime_api_key = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)


# ── get_effective_embedding_model guest override returning actual value (line 427) ─

def test_get_effective_embedding_model_uses_guest_override():
    """get_effective_embedding_model returns guest session embedding model override."""
    import app.runtime.settings_store as store
    session_id = "guest-emb-model-022"
    apply_runtime_settings(embedding_model="text-embedding-3-large", scope_session_id=session_id)
    set_runtime_scope("guest", session_id)
    set_request_runtime_settings(None)
    prev = store._runtime_embedding_model
    store._runtime_embedding_model = ""
    try:
        result = get_effective_embedding_model()
        assert result == "text-embedding-3-large"
    finally:
        store._runtime_embedding_model = prev
        set_runtime_scope(None, None)
        set_request_runtime_settings(None)
        store._guest_runtime_settings.pop(session_id, None)
        store._guest_runtime_settings_ts.pop(session_id, None)


# ── get_masked_api_key env fallback with runtime key unset (lines 451-452) ───

def test_get_masked_api_key_env_fallback_masked_when_no_runtime_key(monkeypatch):
    """get_masked_api_key returns masked env key when no runtime key is set."""
    import app.runtime.settings_store as store
    from unittest.mock import patch
    set_request_runtime_settings(None)
    set_runtime_scope(None, None)
    prev = store._runtime_api_key
    store._runtime_api_key = ""
    with patch("app.runtime.settings_store.get_settings") as mock_settings:
        mock_settings.return_value.app_env = "test"  # allow env fallback
        mock_settings.return_value.openai_api_key = "sk-envkey1234567890abcdef1234"
        result = get_masked_api_key()
    store._runtime_api_key = prev
    # With env key set, should return masked with "(from environment)"
    assert "from environment" in result or "****" in result
