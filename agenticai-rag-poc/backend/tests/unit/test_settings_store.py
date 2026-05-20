"""Unit tests for settings_store — pure validation logic, no HTTP."""
from types import SimpleNamespace

import pytest
from app.settings_store import (
    ALLOWED_MODELS,
    ALLOWED_RERANKER_TYPES,
    ALLOWED_CHUNKER_TYPES,
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
    get_effective_blob_read_write_token,
    get_effective_retriever_hybrid_bm25,
    get_effective_relevance_grader_enabled,
    get_effective_reranker_type,
    get_effective_chunker_type,
    get_effective_chunk_size,
    get_effective_chunk_overlap,
    apply_runtime_settings,
    is_runtime_key_set,
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
        "chunker_type": "recursive",
        "chunk_size": 800,
        "chunk_overlap": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def reset_runtime_settings(monkeypatch):
    import app.settings_store as store

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
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    key = "sk-" + "t" * 40
    apply_runtime_settings(api_key=key, model="gpt-4o")

    assert get_effective_model() == "gpt-4o"
    assert get_effective_api_key() == key
    assert is_runtime_key_set() is True


def test_apply_and_read_back_pinecone_settings(monkeypatch):
    import app.settings_store as store
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
    import app.settings_store as store

    monkeypatch.setattr(store, "_runtime_blob_read_write_token", "")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)

    apply_runtime_settings(blob_read_write_token="vercel_blob_rw_test")

    assert get_effective_blob_read_write_token() == "vercel_blob_rw_test"
    assert os.environ["BLOB_READ_WRITE_TOKEN"] == "vercel_blob_rw_test"
    assert "****" in get_masked_blob_read_write_token()


def test_masked_key_hides_secret(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "sk-abcdefghij1234")

    masked = get_masked_api_key()
    assert "abcdefghij1234"[:-4] not in masked  # middle is hidden
    assert masked.endswith("1234")              # only last 4 visible
    assert "****" in masked


def test_env_fallback_when_no_runtime(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    cfg_key = get_effective_api_key()
    # Should return whatever is in the .env / default config
    assert isinstance(cfg_key, str)


def test_apply_none_does_not_overwrite(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_api_key", "sk-" + "x" * 40)
    monkeypatch.setattr(store, "_runtime_model", "gpt-4o")

    apply_runtime_settings(api_key=None, model="gpt-4")
    assert get_effective_model() == "gpt-4"
    assert "x" * 40 in get_effective_api_key()  # key unchanged


def test_apply_runtime_settings_does_not_clear_vector_store(monkeypatch):
    """Updating settings must NOT discard indexed documents (bug fix for Vercel)."""
    import app.settings_store as store
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
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_k", None)

    from app.config import get_settings
    expected = get_settings().retriever_k
    assert get_effective_retriever_k() == expected


def test_get_effective_retriever_k_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(retriever_k=8), returns 8."""
    import app.settings_store as store
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
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_planner_model", "")
    monkeypatch.setattr(store, "_runtime_model", "")

    from app.config import get_settings
    cfg = get_settings()
    # Falls back through env planner (empty by default) to env global
    expected = cfg.planner_model or cfg.llm_model
    assert get_effective_planner_model() == expected


def test_get_effective_planner_model_uses_runtime_planner_override(monkeypatch):
    """Runtime planner_model takes precedence over global model."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_model", "gpt-4o-mini")
    monkeypatch.setattr(store, "_runtime_planner_model", "gpt-4o")

    assert get_effective_planner_model() == "gpt-4o"

    monkeypatch.setattr(store, "_runtime_planner_model", "")
    monkeypatch.setattr(store, "_runtime_model", "")


def test_get_effective_generator_model_uses_global_runtime(monkeypatch):
    """When no per-node override, runtime global model is used."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_generator_model", "")
    monkeypatch.setattr(store, "_runtime_model", "gpt-4")

    assert get_effective_generator_model() == "gpt-4"

    monkeypatch.setattr(store, "_runtime_model", "")


def test_get_effective_similarity_threshold_falls_back(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_similarity_score_threshold", None)

    from app.config import get_settings
    assert get_effective_similarity_score_threshold() == get_settings().similarity_score_threshold


def test_get_effective_retriever_use_mmr_falls_back(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_use_mmr", None)

    from app.config import get_settings
    assert get_effective_retriever_use_mmr() == get_settings().retriever_use_mmr


def test_get_effective_max_completion_tokens_returns_runtime(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)

    apply_runtime_settings(max_completion_tokens=512)
    assert get_effective_max_completion_tokens() == 512

    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)


def test_get_effective_token_budget_warning_threshold_falls_back(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_token_budget_warning_threshold", None)

    from app.config import get_settings
    assert get_effective_token_budget_warning_threshold() == get_settings().token_budget_warning_threshold


def test_get_effective_langchain_tracing_v2_falls_back(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_tracing_v2", None)

    from app.config import get_settings
    assert get_effective_langchain_tracing_v2() == get_settings().langchain_tracing_v2


def test_get_effective_langchain_project_falls_back(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_project", "")

    from app.config import get_settings
    assert get_effective_langchain_project() == get_settings().langchain_project


def test_get_effective_langchain_project_returns_runtime(monkeypatch):
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_project", "my-test-project")

    assert get_effective_langchain_project() == "my-test-project"

    monkeypatch.setattr(store, "_runtime_langchain_project", "")


def test_get_masked_langchain_api_key_returns_empty_when_unset(monkeypatch):
    """When no LangSmith key is set in runtime or env, returns empty string."""
    import app.settings_store as store
    from unittest.mock import patch
    monkeypatch.setattr(store, "_runtime_langchain_api_key", "")

    # Patch config to have no key
    with patch("app.settings_store.get_settings") as mock_settings:
        mock_settings.return_value.langchain_api_key = ""
        result = get_masked_langchain_api_key()
    assert result == ""


def test_get_masked_langchain_api_key_masks_runtime_key(monkeypatch):
    """When a LangSmith key is set, it is masked."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_langchain_api_key", "ls__abcdef1234")

    masked = get_masked_langchain_api_key()
    assert "****" in masked
    assert masked.endswith("1234")
    assert "abcdef" not in masked

    monkeypatch.setattr(store, "_runtime_langchain_api_key", "")


def test_apply_runtime_settings_resets_agent_singleton(monkeypatch):
    """Agent singleton is reset when model-affecting settings change."""
    import app.agents.rag_agent as agent_mod
    import app.settings_store as store

    # Set a sentinel value
    agent_mod._AGENT = object()
    monkeypatch.setattr(store, "_runtime_model", "")

    apply_runtime_settings(model="gpt-4o")
    assert agent_mod._AGENT is None

    monkeypatch.setattr(store, "_runtime_model", "")


def test_apply_runtime_settings_no_reset_on_non_model_change(monkeypatch):
    """Agent singleton is NOT reset when only retrieval settings change."""
    import app.agents.rag_agent as agent_mod
    import app.settings_store as store

    sentinel = object()
    agent_mod._AGENT = sentinel
    monkeypatch.setattr(store, "_runtime_retriever_k", None)

    apply_runtime_settings(retriever_k=8)
    # _AGENT should NOT have been cleared since no model-affecting field changed
    assert agent_mod._AGENT is sentinel

    monkeypatch.setattr(store, "_runtime_retriever_k", None)


def test_apply_runtime_settings_no_reset_on_max_completion_tokens(monkeypatch):
    """Agent singleton is NOT reset when max_completion_tokens changes.

    Nodes read max_completion_tokens at call time via get_effective_max_completion_tokens(),
    so the compiled graph does not need to be rebuilt (P5 optimisation).
    """
    import app.agents.rag_agent as agent_mod
    import app.settings_store as store

    sentinel = object()
    agent_mod._AGENT = sentinel
    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)

    apply_runtime_settings(max_completion_tokens=256)
    assert agent_mod._AGENT is sentinel  # unchanged

    monkeypatch.setattr(store, "_runtime_max_completion_tokens", None)


def test_production_ignores_provider_env_fallbacks(monkeypatch):
    import app.settings_store as store

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
    import app.settings_store as store

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
    import app.settings_store as store

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


def test_allowed_chunker_types_frozenset():
    assert "recursive" in ALLOWED_CHUNKER_TYPES
    assert "semantic" in ALLOWED_CHUNKER_TYPES


# ── Pipeline feature flag accessor tests ──────────────────────────────────────

def test_get_effective_retriever_hybrid_bm25_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)

    from app.config import get_settings
    assert get_effective_retriever_hybrid_bm25() == get_settings().retriever_hybrid_bm25


def test_get_effective_retriever_hybrid_bm25_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(retriever_hybrid_bm25=False), returns False."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)

    apply_runtime_settings(retriever_hybrid_bm25=False)
    assert get_effective_retriever_hybrid_bm25() is False

    monkeypatch.setattr(store, "_runtime_retriever_hybrid_bm25", None)


def test_get_effective_relevance_grader_enabled_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)

    from app.config import get_settings
    assert get_effective_relevance_grader_enabled() == get_settings().relevance_grader_enabled


def test_get_effective_relevance_grader_enabled_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(relevance_grader_enabled=True), returns True."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)

    apply_runtime_settings(relevance_grader_enabled=True)
    assert get_effective_relevance_grader_enabled() is True

    monkeypatch.setattr(store, "_runtime_relevance_grader_enabled", None)


def test_get_effective_reranker_type_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_type", None)

    from app.config import get_settings
    assert get_effective_reranker_type() == get_settings().reranker_type


def test_get_effective_reranker_type_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(reranker_type='cross-encoder'), returns 'cross-encoder'."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_reranker_type", None)

    apply_runtime_settings(reranker_type="cross-encoder")
    assert get_effective_reranker_type() == "cross-encoder"

    monkeypatch.setattr(store, "_runtime_reranker_type", None)


def test_get_effective_chunker_type_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunker_type", None)

    from app.config import get_settings
    assert get_effective_chunker_type() == get_settings().chunker_type


def test_get_effective_chunker_type_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(chunker_type='semantic'), returns 'semantic'."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunker_type", None)

    apply_runtime_settings(chunker_type="semantic")
    assert get_effective_chunker_type() == "semantic"

    monkeypatch.setattr(store, "_runtime_chunker_type", None)


def test_get_effective_chunk_size_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)

    from app.config import get_settings
    assert get_effective_chunk_size() == get_settings().chunk_size


def test_get_effective_chunk_size_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(chunk_size=400), returns 400."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_size", None)

    apply_runtime_settings(chunk_size=400)
    assert get_effective_chunk_size() == 400

    monkeypatch.setattr(store, "_runtime_chunk_size", None)


def test_get_effective_chunk_overlap_falls_back_to_config(monkeypatch):
    """When no runtime override, returns config value."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)

    from app.config import get_settings
    assert get_effective_chunk_overlap() == get_settings().chunk_overlap


def test_get_effective_chunk_overlap_returns_runtime_value(monkeypatch):
    """After apply_runtime_settings(chunk_overlap=50), returns 50."""
    import app.settings_store as store
    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)

    apply_runtime_settings(chunk_overlap=50)
    assert get_effective_chunk_overlap() == 50

    monkeypatch.setattr(store, "_runtime_chunk_overlap", None)


def test_pipeline_flags_do_not_reset_agent_singleton(monkeypatch):
    """Pipeline flag changes must NOT reset the compiled agent graph."""
    import app.agents.rag_agent as agent_mod
    import app.settings_store as store

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
