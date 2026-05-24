"""
Runtime settings store — holds per-session overrides for API key, model,
retrieval parameters, generation limits, and LangSmith observability.

Values here take precedence over the .env-based config.  The store is
in-memory only; nothing is written to disk (OWASP A02 — no secret
persistence beyond what the operator explicitly put in .env).

Thread-safe for single-process uvicorn (sync lock is fine because
FastAPI endpoint handlers run in a threadpool for sync routes).
"""
import re
import threading
import time
from contextvars import ContextVar
from typing import Any

import structlog

from app.config import get_settings

log = structlog.get_logger()
_lock = threading.Lock()
_active_role: ContextVar[str | None] = ContextVar("active_settings_role", default=None)
_active_session_id: ContextVar[str | None] = ContextVar("active_settings_session_id", default=None)
_request_runtime_settings: ContextVar[dict[str, Any] | None] = ContextVar(
    "request_runtime_settings",
    default=None,
)

# Production deployments must not consume billing-bearing provider settings from
# environment variables. Operators/users supply them through the Settings UI so a
# deployed app cannot silently spend from the deployer's account.
_PRODUCTION_SAFE_DEFAULTS = {
    "llm_model": "gpt-4o-mini",
    "embedding_model": "text-embedding-3-small",
    "planner_model": "",
    "generator_model": "",
    "validator_model": "",
    "reranker_judge_model": "gpt-4.1-mini",
    "retriever_k": 4,
    "retriever_fetch_k": 20,
    "max_context_chunks": 4,
    "max_completion_tokens": 1024,
    "token_budget_warning_threshold": 800,
    "langchain_tracing_v2": False,
    "langchain_project": "agenticai-rag-poc",
}

# ── OpenAI key patterns (standard and project-scoped) ──────────────────────────
_KEY_RE = re.compile(r'^sk(-proj)?-[A-Za-z0-9_\-]{20,}$')

# ── Allowlisted model names ────────────────────────────────────────────────────
ALLOWED_MODELS: frozenset[str] = frozenset({
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-preview",
    "o1-mini",
})

ALLOWED_EMBEDDING_MODELS: frozenset[str] = frozenset({
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
})

_runtime_api_key: str = ""   # empty → fall back to .env
_runtime_model:   str = ""   # empty → fall back to .env
_runtime_embedding_model: str = ""

# Per-node model overrides (empty string = fall back to global model)
_runtime_planner_model:   str = ""
_runtime_generator_model: str = ""
_runtime_validator_model: str = ""

# Retrieval (None = fall back to .env config)
_runtime_retriever_k:                   int   | None = None
_runtime_similarity_score_threshold:    float | None = None
_runtime_retriever_use_mmr:             bool  | None = None
_runtime_retriever_fetch_k:             int   | None = None
_runtime_max_context_chunks:            int   | None = None

# Generation
_runtime_max_completion_tokens:          int | None = None
_runtime_token_budget_warning_threshold: int | None = None

# LangSmith
_runtime_langchain_tracing_v2: bool | None = None
_runtime_langchain_api_key:    str = ""    # empty = use .env
_runtime_langchain_project:    str = ""    # empty = use .env

# Pinecone runtime overrides. VECTOR_STORE_TYPE itself is deployment config only.
_runtime_pinecone_api_key:  str = ""  # empty = use .env
_runtime_pinecone_index_name: str = ""
_runtime_pinecone_namespace:  str = ""
_runtime_pinecone_cloud:      str = ""
_runtime_pinecone_region:     str = ""

ALLOWED_PINECONE_CLOUDS: frozenset[str] = frozenset({"aws", "gcp", "azure"})

# Blob runtime override. FILE_STORE_TYPE / VECTOR_STORE_TYPE remain deployment config.
_runtime_blob_read_write_token: str = ""  # empty = use env
_guest_runtime_settings: dict[str, dict[str, Any]] = {}
_guest_runtime_settings_ts: dict[str, float] = {}  # session_id -> last-write epoch
_GUEST_SETTINGS_TTL = 3600.0  # 1 hour — matches guest token expiry

# Pipeline feature flags (None = fall back to .env config)
_runtime_retriever_hybrid_bm25: bool | None = None
_runtime_relevance_grader_enabled: bool | None = None
_runtime_ragas_evaluation_enabled: bool | None = None
_runtime_reranker_type: str | None = None
_runtime_reranker_judge_model: str = ""   # empty = fall back to .env config
_runtime_chunker_type: str | None = None
_runtime_chunk_size: int | None = None
_runtime_chunk_overlap: int | None = None

ALLOWED_RERANKER_TYPES: frozenset[str] = frozenset({"none", "cross-encoder", "llm-judge"})
ALLOWED_CHUNKER_TYPES: frozenset[str] = frozenset({"recursive", "semantic"})

# OpenAI models permitted as the LLM-as-judge reranker model.
# Intentionally excludes all models in ALLOWED_MODELS (gpt-4o, gpt-4o-mini, etc.)
# to enforce independent evaluation — using the same model as the pipeline creates
# circular reasoning.  gpt-4.1-mini is the default: stronger reasoning than nano,
# affordable (~$0.40/1M input tokens), different family from pipeline models.
ALLOWED_JUDGE_MODELS: frozenset[str] = frozenset({
    "gpt-4.1-mini",   # default — balanced reasoning + cost
    "gpt-4.1-nano",   # cheapest option
    "gpt-4.1",        # highest quality; use when precision matters most
})


def set_runtime_scope(role: str | None, session_id: str | None = None) -> None:
    """Bind runtime settings lookup to the authenticated role/session for this request."""
    _active_role.set(role)
    _active_session_id.set(session_id)


def set_request_runtime_settings(overrides: dict[str, Any] | None) -> None:
    """Bind signed UI settings restored for the current request only."""
    _request_runtime_settings.set(overrides or None)


def has_request_runtime_settings() -> bool:
    """Return True when this request restored Settings UI values from cookie."""
    return bool(_request_runtime_settings.get())


def has_guest_runtime_settings(session_id: str | None) -> bool:
    """Return True when a guest session still has runtime overrides in memory."""
    if not session_id:
        return False
    with _lock:
        return bool(_guest_runtime_settings.get(session_id))


def _purge_stale_guest_settings() -> None:
    """Evict guest settings entries whose TTL has expired (call inside _lock)."""
    cutoff = time.time() - _GUEST_SETTINGS_TTL
    stale = [sid for sid, ts in _guest_runtime_settings_ts.items() if ts < cutoff]
    for sid in stale:
        _guest_runtime_settings.pop(sid, None)
        _guest_runtime_settings_ts.pop(sid, None)


def _guest_value(name: str, default: Any = "") -> Any:
    if _active_role.get() != "guest":
        return default
    session_id = _active_session_id.get()
    if not session_id:
        return default
    return _guest_runtime_settings.get(session_id, {}).get(name, default)


def _is_guest_scope() -> bool:
    return _active_role.get() == "guest"


def _request_value(name: str, default: Any = "") -> Any:
    overrides = _request_runtime_settings.get()
    if not overrides:
        return default
    return overrides.get(name, default)


def account_env_fallback_allowed() -> bool:
    """Return whether billing-bearing env values may be used.

    Local development/test environments may read .env for convenience. In
    production, effective provider credentials and cost-shaping knobs must come
    from runtime Settings UI overrides only.
    """
    return get_settings().app_env != "production"


def _account_env_value(value: str) -> str:
    return value if account_env_fallback_allowed() else ""


def _account_env_default(name: str):
    cfg = get_settings()
    if account_env_fallback_allowed():
        return getattr(cfg, name)
    return _PRODUCTION_SAFE_DEFAULTS[name]


# ── Validation helpers (also used by the API router) ──────────────────────────

def validate_api_key(key: str) -> str:
    """Raise ValueError with a safe message if the key is malformed."""
    key = key.strip()
    if not key:
        raise ValueError("API key must not be empty.")
    if len(key) > 200:
        raise ValueError("API key exceeds maximum allowed length.")
    if not _KEY_RE.match(key):
        raise ValueError(
            "API key format is invalid. Expected an OpenAI key starting with 'sk-' "
            "followed by at least 20 alphanumeric characters."
        )
    return key


def validate_model(model: str) -> str:
    """Raise ValueError if model is not in the allowlist."""
    model = model.strip()
    if not model:
        raise ValueError("Model name must not be empty.")
    if model not in ALLOWED_MODELS:
        raise ValueError(
            f"Model '{model}' is not in the allowed list. "
            f"Supported models: {', '.join(sorted(ALLOWED_MODELS))}."
        )
    return model


def validate_embedding_model(model: str) -> str:
    """Raise ValueError if embedding model is not in the allowlist."""
    model = model.strip()
    if not model:
        raise ValueError("Embedding model name must not be empty.")
    if model not in ALLOWED_EMBEDDING_MODELS:
        raise ValueError(
            f"Embedding model '{model}' is not in the allowed list. "
            f"Supported models: {', '.join(sorted(ALLOWED_EMBEDDING_MODELS))}."
        )
    return model


def validate_retriever_k(k: int) -> int:
    """Raise ValueError if retriever_k is out of bounds."""
    if not (1 <= k <= 20):
        raise ValueError("retriever_k must be between 1 and 20.")
    return k


def validate_similarity_score_threshold(t: float) -> float:
    """Raise ValueError if similarity_score_threshold is out of [0.0, 1.0]."""
    if not (0.0 <= t <= 1.0):
        raise ValueError("similarity_score_threshold must be between 0.0 and 1.0.")
    return round(t, 4)


def validate_max_completion_tokens(n: int) -> int:
    """Raise ValueError if max_completion_tokens is outside [128, 4096]."""
    if not (128 <= n <= 4096):
        raise ValueError("max_completion_tokens must be between 128 and 4096.")
    return n


def validate_token_budget_warning_threshold(n: int) -> int:
    """Raise ValueError if token_budget_warning_threshold is negative."""
    if n < 0:
        raise ValueError("token_budget_warning_threshold must be >= 0.")
    return n


def validate_retriever_fetch_k(k: int, retriever_k: int) -> int:
    """Raise ValueError if retriever_fetch_k is out of bounds or less than retriever_k."""
    if k < retriever_k:
        raise ValueError(
            f"retriever_fetch_k ({k}) must be >= retriever_k ({retriever_k})."
        )
    if k > 100:
        raise ValueError("retriever_fetch_k must be <= 100.")
    return k


def validate_max_context_chunks(n: int) -> int:
    """Raise ValueError if max_context_chunks is outside [1, 20]."""
    if not (1 <= n <= 20):
        raise ValueError("max_context_chunks must be between 1 and 20.")
    return n


def validate_langchain_project(p: str) -> str:
    """Strip and validate LangSmith project name."""
    p = p.strip()
    if len(p) > 100:
        raise ValueError("langchain_project must be <= 100 characters.")
    return p


def validate_langchain_api_key(key: str) -> str:
    """Validate LangSmith API key format."""
    key = key.strip()
    # LangSmith keys start with "ls__" or "lsv2_"
    if key and not (key.startswith("ls__") or key.startswith("lsv2_")):
        raise ValueError("LangSmith API key must start with 'ls__' or 'lsv2_'.")
    if len(key) > 200:
        raise ValueError("LangSmith API key exceeds maximum length.")
    return key


def validate_pinecone_api_key(key: str) -> str:
    """Validate Pinecone API key shape without requiring an exact vendor format."""
    key = key.strip()
    if not key:
        raise ValueError("Pinecone API key must not be empty.")
    if len(key) > 300:
        raise ValueError("Pinecone API key exceeds maximum length.")
    if any(ch.isspace() for ch in key):
        raise ValueError("Pinecone API key must not contain whitespace.")
    return key


def validate_pinecone_index_name(name: str) -> str:
    """Validate Pinecone serverless index names."""
    name = name.strip().lower()
    if not name:
        raise ValueError("Pinecone index name must not be empty.")
    if len(name) > 45:
        raise ValueError("Pinecone index name must be <= 45 characters.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", name):
        raise ValueError("Pinecone index name may contain lowercase letters, numbers, and hyphens.")
    return name


def validate_pinecone_namespace(namespace: str) -> str:
    """Validate optional Pinecone namespace."""
    namespace = namespace.strip()
    if len(namespace) > 100:
        raise ValueError("Pinecone namespace must be <= 100 characters.")
    if namespace and not re.fullmatch(r"[A-Za-z0-9_.:-]+", namespace):
        raise ValueError("Pinecone namespace may contain letters, numbers, _, ., :, and -.")
    return namespace


def validate_pinecone_cloud(cloud: str) -> str:
    """Validate Pinecone serverless cloud."""
    cloud = cloud.strip().lower()
    if cloud not in ALLOWED_PINECONE_CLOUDS:
        raise ValueError(
            f"pinecone_cloud must be one of: {', '.join(sorted(ALLOWED_PINECONE_CLOUDS))}."
        )
    return cloud


def validate_pinecone_region(region: str) -> str:
    """Validate Pinecone serverless region."""
    region = region.strip().lower()
    if not region:
        raise ValueError("Pinecone region must not be empty.")
    if len(region) > 50:
        raise ValueError("Pinecone region must be <= 50 characters.")
    if not re.fullmatch(r"[a-z0-9-]+", region):
        raise ValueError("Pinecone region may contain lowercase letters, numbers, and hyphens.")
    return region


def validate_blob_read_write_token(token: str) -> str:
    """Validate a Vercel Blob read/write token without exposing its value."""
    token = token.strip()
    if not token:
        raise ValueError("Blob read/write token must not be empty.")
    if len(token) > 500:
        raise ValueError("Blob read/write token exceeds maximum length.")
    if any(ch.isspace() for ch in token):
        raise ValueError("Blob read/write token must not contain whitespace.")
    return token


def validate_reranker_type(v: str) -> str:
    """Raise ValueError if reranker_type is not in the allowlist."""
    v = v.strip().lower()
    if v not in ALLOWED_RERANKER_TYPES:
        raise ValueError(f"reranker_type must be one of: {', '.join(sorted(ALLOWED_RERANKER_TYPES))}.")
    return v


def validate_reranker_judge_model(model: str) -> str:
    """Raise ValueError if reranker_judge_model is not in the allowed OpenAI judge model list."""
    model = model.strip()
    if not model:
        raise ValueError("Reranker judge model must not be empty.")
    if model not in ALLOWED_JUDGE_MODELS:
        raise ValueError(
            f"reranker_judge_model '{model}' is not allowed. "
            f"Supported models: {', '.join(sorted(ALLOWED_JUDGE_MODELS))}."
        )
    return model


def validate_chunker_type(v: str) -> str:
    """Raise ValueError if chunker_type is not in the allowlist."""
    v = v.strip().lower()
    if v not in ALLOWED_CHUNKER_TYPES:
        raise ValueError(f"chunker_type must be one of: {', '.join(sorted(ALLOWED_CHUNKER_TYPES))}.")
    return v


def validate_chunk_size(n: int) -> int:
    """Raise ValueError if chunk_size is outside [100, 4000]."""
    if not (100 <= n <= 4000):
        raise ValueError("chunk_size must be between 100 and 4000.")
    return n


def validate_chunk_overlap(n: int, chunk_size: int) -> int:
    """Raise ValueError if chunk_overlap is invalid relative to chunk_size."""
    if n < 0:
        raise ValueError("chunk_overlap must be >= 0.")
    if n >= chunk_size:
        raise ValueError(f"chunk_overlap ({n}) must be less than chunk_size ({chunk_size}).")
    return n


# ── Accessors ─────────────────────────────────────────────────────────────────

def get_effective_api_key() -> str:
    with _lock:
        request_key = _request_value("api_key")
        if request_key:
            return str(request_key)
        guest_key = _guest_value("api_key")
        if guest_key:
            return str(guest_key)
        if _is_guest_scope():
            return _account_env_value(get_settings().openai_api_key)
        return _runtime_api_key or _account_env_value(get_settings().openai_api_key)


def get_effective_model() -> str:
    with _lock:
        request_model = _request_value("model")
        if request_model:
            return str(request_model)
        guest_model = _guest_value("model")
        if guest_model:
            return str(guest_model)
        if _is_guest_scope():
            return str(_account_env_default("llm_model"))
        return _runtime_model or str(_account_env_default("llm_model"))


def get_effective_embedding_model() -> str:
    with _lock:
        request_model = _request_value("embedding_model")
        if request_model:
            return str(request_model)
        guest_model = _guest_value("embedding_model")
        if guest_model:
            return str(guest_model)
        if _is_guest_scope():
            return str(_account_env_default("embedding_model"))
        return _runtime_embedding_model or str(_account_env_default("embedding_model"))


def get_masked_api_key() -> str:
    """Return a display-safe masked representation — never the real key."""
    with _lock:
        request_key = _request_value("api_key")
        if request_key:
            return f"sk-****...{str(request_key)[-4:]}"
        guest_key = _guest_value("api_key")
        if guest_key:
            return f"sk-****...{str(guest_key)[-4:]}"
        if _is_guest_scope():
            cfg_key = _account_env_value(get_settings().openai_api_key)
            return f"sk-****...{cfg_key[-4:]} (from environment)" if cfg_key else ""
        if _runtime_api_key:
            # Show prefix + last 4 chars only  (e.g. sk-****...abcd)
            suffix = _runtime_api_key[-4:]
            return f"sk-****...{suffix}"
        cfg_key = _account_env_value(get_settings().openai_api_key)
        if cfg_key:
            suffix = cfg_key[-4:]
            return f"sk-****...{suffix} (from environment)"
        return ""


def is_runtime_key_set() -> bool:
    with _lock:
        if _request_value("api_key"):
            return True
        if _guest_value("api_key"):
            return True
        if _is_guest_scope():
            return False
        return bool(_runtime_api_key)


# ── Per-node model accessors ──────────────────────────────────────────────────

def _first_non_empty(*values: str) -> str:
    """Return the first non-empty string from *values*, or ''."""
    return next((v for v in values if v), "")


def get_effective_planner_model() -> str:
    """Return the effective planner model, falling back through the override chain."""
    with _lock:
        return _first_non_empty(
            str(_request_value("planner_model")),
            str(_request_value("model")),
            _runtime_planner_model, _runtime_model,
            str(_account_env_default("planner_model")),
            str(_account_env_default("llm_model")),
        )


def get_effective_generator_model() -> str:
    """Return the effective generator model, falling back through the override chain."""
    with _lock:
        return _first_non_empty(
            str(_request_value("generator_model")),
            str(_request_value("model")),
            _runtime_generator_model, _runtime_model,
            str(_account_env_default("generator_model")),
            str(_account_env_default("llm_model")),
        )


def get_effective_validator_model() -> str:
    """Return the effective validator model, falling back through the override chain."""
    with _lock:
        return _first_non_empty(
            str(_request_value("validator_model")),
            str(_request_value("model")),
            _runtime_validator_model, _runtime_model,
            str(_account_env_default("validator_model")),
            str(_account_env_default("llm_model")),
        )


# ── Retrieval accessors ───────────────────────────────────────────────────────

def get_effective_retriever_k() -> int:
    """Return the effective retriever_k value."""
    with _lock:
        req_val = _request_value("retriever_k", None)
        if req_val is not None:
            return int(req_val)
        return (
            _runtime_retriever_k
            if _runtime_retriever_k is not None
            else int(_account_env_default("retriever_k"))
        )


def get_effective_similarity_score_threshold() -> float:
    """Return the effective similarity score threshold."""
    with _lock:
        req_val = _request_value("similarity_score_threshold", None)
        if req_val is not None:
            return float(req_val)
        return (
            _runtime_similarity_score_threshold
            if _runtime_similarity_score_threshold is not None
            else get_settings().similarity_score_threshold
        )


def get_effective_retriever_use_mmr() -> bool:
    """Return whether MMR retrieval is enabled."""
    with _lock:
        req_val = _request_value("retriever_use_mmr", None)
        if req_val is not None:
            return bool(req_val)
        return (
            _runtime_retriever_use_mmr
            if _runtime_retriever_use_mmr is not None
            else get_settings().retriever_use_mmr
        )


def get_effective_retriever_fetch_k() -> int:
    """Return the effective MMR candidate pool size."""
    with _lock:
        req_val = _request_value("retriever_fetch_k", None)
        if req_val is not None:
            return int(req_val)
        return (
            _runtime_retriever_fetch_k
            if _runtime_retriever_fetch_k is not None
            else int(_account_env_default("retriever_fetch_k"))
        )


def get_effective_max_context_chunks() -> int:
    """Return the maximum number of context chunks sent to the LLM."""
    with _lock:
        req_val = _request_value("max_context_chunks", None)
        if req_val is not None:
            return int(req_val)
        return (
            _runtime_max_context_chunks
            if _runtime_max_context_chunks is not None
            else int(_account_env_default("max_context_chunks"))
        )


# ── Generation accessors ──────────────────────────────────────────────────────

def get_effective_max_completion_tokens() -> int:
    """Return the effective max completion tokens cap."""
    with _lock:
        request_value = _request_value("max_completion_tokens", None)
        if request_value is not None:
            return int(request_value)
        return (
            _runtime_max_completion_tokens
            if _runtime_max_completion_tokens is not None
            else int(_account_env_default("max_completion_tokens"))
        )


def get_effective_token_budget_warning_threshold() -> int:
    """Return the effective token budget warning threshold."""
    with _lock:
        return (
            _runtime_token_budget_warning_threshold
            if _runtime_token_budget_warning_threshold is not None
            else int(_account_env_default("token_budget_warning_threshold"))
        )


# ── LangSmith accessors ───────────────────────────────────────────────────────

def get_effective_langchain_tracing_v2() -> bool:
    """Return whether LangSmith tracing is enabled."""
    with _lock:
        return (
            _runtime_langchain_tracing_v2
            if _runtime_langchain_tracing_v2 is not None
            else bool(_account_env_default("langchain_tracing_v2"))
        )


def get_effective_langchain_api_key() -> str:
    """Return the effective LangSmith API key (runtime override or env)."""
    with _lock:
        request_key = _request_value("langchain_api_key")
        if request_key:
            return str(request_key)
        return _runtime_langchain_api_key or _account_env_value(get_settings().langchain_api_key)


def get_effective_langchain_project() -> str:
    """Return the effective LangSmith project name."""
    with _lock:
        return _runtime_langchain_project or str(_account_env_default("langchain_project"))


def get_masked_langchain_api_key() -> str:
    """Return a display-safe masked LangSmith API key — never the real value."""
    with _lock:
        key = (
            str(_request_value("langchain_api_key"))
            or _runtime_langchain_api_key
            or _account_env_value(get_settings().langchain_api_key)
        )
        if not key:
            return ""
        return f"ls-****...{key[-4:]}"


# ── Vector store / Pinecone accessors ─────────────────────────────────────────

def get_effective_vector_store_type() -> str:
    with _lock:
        return get_settings().vector_store_type


def get_effective_file_store_type() -> str:
    with _lock:
        value = getattr(get_settings(), "file_store_type", "local")
        return value if isinstance(value, str) else "local"


def get_effective_pinecone_api_key() -> str:
    """Return the Pinecone API key for this request.

    Request-restored Settings UI values are scoped by the encrypted runtime token
    and, for guests, the token's session id. Deployment env fallback remains local
    dev/test only via _account_env_value.
    """
    with _lock:
        request_key = _request_value("pinecone_api_key")
        if request_key:
            return str(request_key)
        guest_key = _guest_value("pinecone_api_key")
        if guest_key:
            return str(guest_key)
        if _is_guest_scope():
            return _runtime_pinecone_api_key or _account_env_value(get_settings().pinecone_api_key)
        return _runtime_pinecone_api_key or _account_env_value(get_settings().pinecone_api_key)


def get_effective_pinecone_index_name() -> str:
    """Return the Pinecone index name for the current runtime scope."""
    with _lock:
        request_index = _request_value("pinecone_index_name")
        if request_index:
            return str(request_index)
        guest_index = _guest_value("pinecone_index_name")
        if guest_index:
            return str(guest_index)
        if _is_guest_scope():
            return _runtime_pinecone_index_name or get_settings().pinecone_index_name
        return _runtime_pinecone_index_name or get_settings().pinecone_index_name


def get_effective_pinecone_namespace() -> str:
    """Return the Pinecone namespace for the current runtime scope."""
    with _lock:
        request_namespace = _request_value("pinecone_namespace")
        if request_namespace:
            return str(request_namespace)
        guest_namespace = _guest_value("pinecone_namespace")
        if guest_namespace:
            return str(guest_namespace)
        if _is_guest_scope():
            return _runtime_pinecone_namespace or get_settings().pinecone_namespace
        return _runtime_pinecone_namespace or get_settings().pinecone_namespace


def get_effective_pinecone_cloud() -> str:
    """Return the Pinecone cloud for the current runtime scope."""
    with _lock:
        request_cloud = _request_value("pinecone_cloud")
        if request_cloud:
            return str(request_cloud)
        guest_cloud = _guest_value("pinecone_cloud")
        if guest_cloud:
            return str(guest_cloud)
        if _is_guest_scope():
            return _runtime_pinecone_cloud or get_settings().pinecone_cloud
        return _runtime_pinecone_cloud or get_settings().pinecone_cloud


def get_effective_pinecone_region() -> str:
    """Return the Pinecone region for the current runtime scope."""
    with _lock:
        request_region = _request_value("pinecone_region")
        if request_region:
            return str(request_region)
        guest_region = _guest_value("pinecone_region")
        if guest_region:
            return str(guest_region)
        if _is_guest_scope():
            return _runtime_pinecone_region or get_settings().pinecone_region
        return _runtime_pinecone_region or get_settings().pinecone_region


def get_masked_pinecone_api_key() -> str:
    """Return a display-safe masked Pinecone API key — never the real value."""
    with _lock:
        key = (
            _request_value("pinecone_api_key")
            or _guest_value("pinecone_api_key")
            or _runtime_pinecone_api_key
            or _account_env_value(get_settings().pinecone_api_key)
        )
        if not key:
            return ""
        prefix = key[:3] if len(key) >= 3 else "pc"
        return f"{prefix}-****...{key[-4:]}"


def is_runtime_pinecone_key_set() -> bool:
    """Return whether a runtime Pinecone key is active for the current scope."""
    with _lock:
        if _request_value("pinecone_api_key"):
            return True
        if _guest_value("pinecone_api_key"):
            return True
        if _is_guest_scope():
            return bool(_runtime_pinecone_api_key)
        return bool(_runtime_pinecone_api_key)


def get_effective_blob_read_write_token() -> str:
    """Return runtime/env Vercel Blob token. Supports both Vercel token names.

    Request-restored Settings UI values are scoped by the encrypted runtime token
    and, for guests, the token's session id. Deployment env fallback is local
    dev/test only — in production all billable attributes must come from the
    Settings UI.
    """
    with _lock:
        cfg = get_settings()
        blob_token = getattr(cfg, "blob_read_write_token", "")
        vercel_blob_token = getattr(cfg, "vercel_blob_read_write_token", "")
        if not isinstance(blob_token, str):
            blob_token = ""
        if not isinstance(vercel_blob_token, str):
            vercel_blob_token = ""
        if not account_env_fallback_allowed():
            blob_token = ""
            vercel_blob_token = ""
        request_token = _request_value("blob_read_write_token")
        if request_token:
            return str(request_token)
        guest_token = _guest_value("blob_read_write_token")
        if guest_token:
            return str(guest_token)
        if _is_guest_scope():
            return str(_runtime_blob_read_write_token or blob_token or vercel_blob_token)
        return str(_runtime_blob_read_write_token or blob_token or vercel_blob_token)


def get_masked_blob_read_write_token() -> str:
    """Return a display-safe masked Blob token — never the real value."""
    with _lock:
        cfg = get_settings()
        blob_token = getattr(cfg, "blob_read_write_token", "")
        vercel_blob_token = getattr(cfg, "vercel_blob_read_write_token", "")
        if not isinstance(blob_token, str):
            blob_token = ""
        if not isinstance(vercel_blob_token, str):
            vercel_blob_token = ""
        if not account_env_fallback_allowed():
            blob_token = ""
            vercel_blob_token = ""
        key = (
            _request_value("blob_read_write_token")
            or _guest_value("blob_read_write_token")
            or _runtime_blob_read_write_token
            or blob_token
            or vercel_blob_token
        )
        if not key:
            return ""
        prefix = key[:10] if len(key) >= 10 else "blob"
        return f"{prefix}****...{key[-4:]}"


def is_runtime_blob_token_set() -> bool:
    """Return whether a runtime Blob token is active for the current scope."""
    with _lock:
        if _request_value("blob_read_write_token"):
            return True
        if _guest_value("blob_read_write_token"):
            return True
        if _is_guest_scope():
            return bool(_runtime_blob_read_write_token)
        return bool(_runtime_blob_read_write_token)


def sync_effective_blob_token_to_env() -> None:
    """Expose the effective Blob token to SDKs that read os.environ directly."""
    import os

    token = get_effective_blob_read_write_token()
    if token:
        os.environ["BLOB_READ_WRITE_TOKEN"] = token


# ── Pipeline feature flag accessors ──────────────────────────────────────────

def get_effective_retriever_hybrid_bm25() -> bool:
    """Return whether BM25 hybrid retrieval is enabled."""
    with _lock:
        req_val = _request_value("retriever_hybrid_bm25", None)
        if req_val is not None:
            return bool(req_val)
        return (
            _runtime_retriever_hybrid_bm25
            if _runtime_retriever_hybrid_bm25 is not None
            else get_settings().retriever_hybrid_bm25
        )


def get_effective_relevance_grader_enabled() -> bool:
    """Return whether the self-RAG relevance grader is enabled."""
    with _lock:
        req_val = _request_value("relevance_grader_enabled", None)
        if req_val is not None:
            return bool(req_val)
        return (
            _runtime_relevance_grader_enabled
            if _runtime_relevance_grader_enabled is not None
            else get_settings().relevance_grader_enabled
        )


def get_effective_ragas_evaluation_enabled() -> bool:
    """Return whether the Ragas evaluation UI/dashboard is enabled."""
    with _lock:
        return (
            _runtime_ragas_evaluation_enabled
            if _runtime_ragas_evaluation_enabled is not None
            else get_settings().ragas_evaluation_enabled
        )


def _smart_default_reranker_type() -> str:
    """Return the best reranker default for this deployment.

    Priority: Vercel → llm-judge. Sentence-transformers installed → cross-encoder. Else → llm-judge.
    Only called when no explicit RERANKER_TYPE env var is set.
    """
    import importlib.util
    import os
    if os.environ.get("VERCEL"):
        return "llm-judge"
    if importlib.util.find_spec("sentence_transformers") is not None:
        return "cross-encoder"
    return "llm-judge"


def get_effective_reranker_type() -> str:
    """Return the effective reranker type ('none', 'cross-encoder', or 'llm-judge')."""
    with _lock:
        req_val = _request_value("reranker_type", None)
        if req_val is not None:
            return str(req_val)
        if _runtime_reranker_type is not None:
            return _runtime_reranker_type
        import os
        env_val = os.environ.get("RERANKER_TYPE", "").strip().lower()
        if env_val:
            return env_val
        return _smart_default_reranker_type()


def get_effective_reranker_judge_model() -> str:
    """Return the effective LLM-as-judge reranker model (falls back to config default)."""
    with _lock:
        return _first_non_empty(
            str(_request_value("reranker_judge_model")),
            _runtime_reranker_judge_model,
            str(_account_env_default("reranker_judge_model")),
        )


def get_effective_chunker_type() -> str:
    """Return the effective chunker type ('recursive' or 'semantic')."""
    with _lock:
        return (
            _runtime_chunker_type
            if _runtime_chunker_type is not None
            else get_settings().chunker_type
        )


def get_effective_chunk_size() -> int:
    """Return the effective chunk size for document splitting."""
    with _lock:
        return (
            _runtime_chunk_size
            if _runtime_chunk_size is not None
            else get_settings().chunk_size
        )


def get_effective_chunk_overlap() -> int:
    """Return the effective chunk overlap for document splitting."""
    with _lock:
        return (
            _runtime_chunk_overlap
            if _runtime_chunk_overlap is not None
            else get_settings().chunk_overlap
        )


# ── Mutator — called by the settings API endpoint ─────────────────────────────

def apply_runtime_settings(
    api_key: str | None = None,
    model: str | None = None,
    embedding_model: str | None = None,
    planner_model: str | None = None,
    generator_model: str | None = None,
    validator_model: str | None = None,
    retriever_k: int | None = None,
    similarity_score_threshold: float | None = None,
    retriever_use_mmr: bool | None = None,
    retriever_fetch_k: int | None = None,
    max_context_chunks: int | None = None,
    max_completion_tokens: int | None = None,
    token_budget_warning_threshold: int | None = None,
    langchain_tracing_v2: bool | None = None,
    langchain_api_key: str | None = None,
    langchain_project: str | None = None,
    pinecone_api_key: str | None = None,
    pinecone_index_name: str | None = None,
    pinecone_namespace: str | None = None,
    pinecone_cloud: str | None = None,
    pinecone_region: str | None = None,
    blob_read_write_token: str | None = None,
    retriever_hybrid_bm25: bool | None = None,
    relevance_grader_enabled: bool | None = None,
    ragas_evaluation_enabled: bool | None = None,
    reranker_type: str | None = None,
    reranker_judge_model: str | None = None,
    chunker_type: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    scope_session_id: str | None = None,
) -> None:
    """
    Persist validated values and flush any LRU-cached clients so the
    next request picks up the new key / model.

    OWASP A02 — API keys and LangSmith keys are never written to disk or logs.
    OWASP A09 — Secrets are always masked in log output.
    """
    global _runtime_api_key, _runtime_model, _runtime_embedding_model
    global _runtime_planner_model, _runtime_generator_model, _runtime_validator_model
    global _runtime_retriever_k, _runtime_similarity_score_threshold
    global _runtime_retriever_use_mmr, _runtime_retriever_fetch_k, _runtime_max_context_chunks
    global _runtime_max_completion_tokens, _runtime_token_budget_warning_threshold
    global _runtime_langchain_tracing_v2, _runtime_langchain_api_key, _runtime_langchain_project
    global _runtime_pinecone_api_key, _runtime_pinecone_index_name
    global _runtime_pinecone_namespace, _runtime_pinecone_cloud, _runtime_pinecone_region
    global _runtime_blob_read_write_token
    global _runtime_retriever_hybrid_bm25, _runtime_relevance_grader_enabled
    global _runtime_ragas_evaluation_enabled
    global _runtime_reranker_type, _runtime_reranker_judge_model
    global _runtime_chunker_type, _runtime_chunk_size, _runtime_chunk_overlap

    if scope_session_id:
        with _lock:
            _purge_stale_guest_settings()
            overrides = _guest_runtime_settings.setdefault(scope_session_id, {})
            if api_key is not None:               overrides["api_key"] = api_key
            if model is not None:                 overrides["model"] = model
            if embedding_model is not None:       overrides["embedding_model"] = embedding_model
            if pinecone_api_key is not None:      overrides["pinecone_api_key"] = pinecone_api_key
            if pinecone_index_name is not None:   overrides["pinecone_index_name"] = pinecone_index_name
            if pinecone_namespace is not None:    overrides["pinecone_namespace"] = pinecone_namespace
            if pinecone_cloud is not None:        overrides["pinecone_cloud"] = pinecone_cloud
            if pinecone_region is not None:       overrides["pinecone_region"] = pinecone_region
            if blob_read_write_token is not None: overrides["blob_read_write_token"] = blob_read_write_token
            _guest_runtime_settings_ts[scope_session_id] = time.time()
        if any(x is not None for x in [model]):
            import app.agents.rag_agent as _agent_mod
            _agent_mod._AGENT = None
        if embedding_model is not None:
            import app.rag.vector_store as _vector_store_mod
            _vector_store_mod.get_vector_store.cache_clear()
            _vector_store_mod.invalidate_doc_cache()
        if any(x is not None for x in [
            pinecone_api_key, pinecone_index_name, pinecone_namespace,
            pinecone_cloud, pinecone_region,
        ]):
            import app.rag.vector_store as _vector_store_mod
            _vector_store_mod.get_vector_store.cache_clear()
            _vector_store_mod.invalidate_doc_cache()
        log.info(
            "guest_runtime_settings_applied",
            model=model or "(unchanged)",
            api_key="***" if api_key else "(unchanged)",
            pinecone_api_key="***" if pinecone_api_key else "(unchanged)",
            blob_read_write_token="***" if blob_read_write_token else "(unchanged)",
        )
        return

    with _lock:
        if api_key is not None:                       _runtime_api_key = api_key
        if model is not None:                         _runtime_model = model
        if embedding_model is not None:               _runtime_embedding_model = embedding_model
        if planner_model is not None:                 _runtime_planner_model = planner_model
        if generator_model is not None:               _runtime_generator_model = generator_model
        if validator_model is not None:               _runtime_validator_model = validator_model
        if retriever_k is not None:                   _runtime_retriever_k = retriever_k
        if similarity_score_threshold is not None:    _runtime_similarity_score_threshold = similarity_score_threshold
        if retriever_use_mmr is not None:             _runtime_retriever_use_mmr = retriever_use_mmr
        if retriever_fetch_k is not None:             _runtime_retriever_fetch_k = retriever_fetch_k
        if max_context_chunks is not None:            _runtime_max_context_chunks = max_context_chunks
        if max_completion_tokens is not None:         _runtime_max_completion_tokens = max_completion_tokens
        if token_budget_warning_threshold is not None: _runtime_token_budget_warning_threshold = token_budget_warning_threshold
        if langchain_tracing_v2 is not None:          _runtime_langchain_tracing_v2 = langchain_tracing_v2
        if langchain_api_key is not None:             _runtime_langchain_api_key = langchain_api_key
        if langchain_project is not None:             _runtime_langchain_project = langchain_project
        if pinecone_api_key is not None:              _runtime_pinecone_api_key = pinecone_api_key
        if pinecone_index_name is not None:           _runtime_pinecone_index_name = pinecone_index_name
        if pinecone_namespace is not None:            _runtime_pinecone_namespace = pinecone_namespace
        if pinecone_cloud is not None:                _runtime_pinecone_cloud = pinecone_cloud
        if pinecone_region is not None:               _runtime_pinecone_region = pinecone_region
        if blob_read_write_token is not None:         _runtime_blob_read_write_token = blob_read_write_token
        if retriever_hybrid_bm25 is not None:         _runtime_retriever_hybrid_bm25 = retriever_hybrid_bm25
        if relevance_grader_enabled is not None:      _runtime_relevance_grader_enabled = relevance_grader_enabled
        if ragas_evaluation_enabled is not None:      _runtime_ragas_evaluation_enabled = ragas_evaluation_enabled
        if reranker_type is not None:                 _runtime_reranker_type = reranker_type
        if reranker_judge_model is not None:          _runtime_reranker_judge_model = reranker_judge_model
        if chunker_type is not None:                  _runtime_chunker_type = chunker_type
        if chunk_size is not None:                    _runtime_chunk_size = chunk_size
        if chunk_overlap is not None:                 _runtime_chunk_overlap = chunk_overlap

    # Apply LangSmith env vars outside the lock (os.environ is not _lock's domain)
    import os
    effective_tracing = (
        _runtime_langchain_tracing_v2
        if _runtime_langchain_tracing_v2 is not None
        else bool(_account_env_default("langchain_tracing_v2"))
    )
    if effective_tracing:
        effective_key = _runtime_langchain_api_key or _account_env_value(get_settings().langchain_api_key)
        if effective_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = effective_key
            os.environ["LANGCHAIN_PROJECT"] = (
                _runtime_langchain_project or str(_account_env_default("langchain_project"))
            )
            log.info("langsmith_tracing_enabled")
        else:
            log.warning("langsmith_tracing_requested_but_no_key")
    else:
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        os.environ.pop("LANGCHAIN_API_KEY", None)

    # Reset the compiled LangGraph agent singleton whenever model-affecting settings change.
    # Nodes call _llm() which reads effective settings at call time, but the graph itself
    # may hold references to old node closures if they captured settings.
    # NOTE: we deliberately do NOT clear the vector store cache here.
    # _DynamicOpenAIEmbeddings reads the API key at call time, so
    # already-indexed documents remain queryable after a key change.
    # Only reset the compiled graph when the model selection changes.
    # api_key and max_completion_tokens are read at call time via get_effective_*,
    # so they do not require a graph rebuild.
    if any(x is not None for x in [model, planner_model, generator_model, validator_model]):
        import app.agents.rag_agent as _agent_mod
        _agent_mod._AGENT = None

    if any(x is not None for x in [
        embedding_model,
        pinecone_api_key, pinecone_index_name, pinecone_namespace,
        pinecone_cloud, pinecone_region,
    ]):
        import app.rag.vector_store as _vector_store_mod
        _vector_store_mod.get_vector_store.cache_clear()
        _vector_store_mod.invalidate_doc_cache()

    if blob_read_write_token is not None:
        sync_effective_blob_token_to_env()
        # The vector store type changes from memory → blob when a token is first
        # configured; clear the singleton so the next call builds the correct store.
        import app.rag.vector_store as _vector_store_mod
        _vector_store_mod.get_vector_store.cache_clear()
        _vector_store_mod.invalidate_doc_cache()

    log.info(
        "runtime_settings_applied",
        model=model or "(unchanged)",
        api_key="***" if api_key else "(unchanged)",  # OWASP A09 — never log secrets
        pinecone_api_key="***" if pinecone_api_key else "(unchanged)",
        blob_read_write_token="***" if blob_read_write_token else "(unchanged)",
    )
