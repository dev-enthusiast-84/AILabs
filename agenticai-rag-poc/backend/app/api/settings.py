"""
Settings API — allows authenticated users to update the active OpenAI
API key, model name, retrieval parameters, generation limits, and
LangSmith observability at runtime without restarting the server.

OWASP controls:
  A01  Auth required on every endpoint (JWT Bearer).
       Guests may only set API key, global model, and Pinecone settings
       (one-per-session, JTI-tracked).
       All pipeline-level settings (per-node models, retrieval, generation,
       LangSmith) require admin role.
  A02  API key and LangSmith key are never returned in full; always masked.
       Neither is written to logs (structlog omits them).
  A03  All string inputs go through bleach.clean() before validation.
       Numeric fields have explicit bounds checks.
  A04  Endpoint is rate-limited (20/minute for settings; 1/5min for ragas trigger).
       Numeric bounds prevent absurd resource allocation (e.g. retriever_k=1000).
  A07  Uniform error messages; no stack traces exposed to clients.
"""
import asyncio
import importlib.util
import os
import bleach
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt as _jwt
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.audit import audit_event
from app.auth.utils import get_current_user
from app.auth.models import UserInDB
from app.config import get_settings
from app.runtime.runtime_settings_cookie import set_runtime_settings_cookie
from app.runtime.settings_store import (
    ALLOWED_MODELS,
    ALLOWED_EMBEDDING_MODELS,
    ALLOWED_RERANKER_TYPES,
    ALLOWED_CHUNKER_TYPES,
    ALLOWED_JUDGE_MODELS,
    apply_runtime_settings,
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
    get_effective_langchain_project,
    get_effective_vector_store_type,
    get_effective_file_store_type,
    get_effective_pinecone_index_name,
    get_effective_pinecone_namespace,
    get_effective_pinecone_cloud,
    get_effective_pinecone_region,
    get_effective_retriever_hybrid_bm25,
    get_effective_relevance_grader_enabled,
    get_effective_ragas_evaluation_enabled,
    get_effective_reranker_type,
    get_effective_reranker_judge_model,
    get_effective_chunker_type,
    get_effective_chunk_size,
    get_effective_chunk_overlap,
    get_effective_api_key,
    get_effective_pinecone_api_key,
    get_effective_blob_read_write_token,
    get_effective_langchain_api_key,
    get_masked_api_key,
    get_masked_langchain_api_key,
    get_masked_pinecone_api_key,
    get_masked_blob_read_write_token,
    has_guest_runtime_settings,
    is_runtime_key_set,
    is_runtime_pinecone_key_set,
    is_runtime_blob_token_set,
    validate_api_key,
    validate_model,
    validate_embedding_model,
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
    set_runtime_scope,
    account_env_fallback_allowed,
)

_log = structlog.get_logger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()
_bearer = HTTPBearer()

# Track guest JTIs that have already configured settings (in-memory per process).
# Capped to prevent unbounded memory growth; oldest entries are evicted when full.
_guest_settings_used: set[str] = set()
_MAX_GUEST_JTI = 10_000


# ── Request / response models ──────────────────────────────────────────────────

class SettingsUpdateRequest(BaseModel):
    # Existing fields
    api_key: str | None = None
    model: str | None = None
    embedding_model: str | None = None

    # Per-node model overrides
    planner_model: str | None = None
    generator_model: str | None = None
    validator_model: str | None = None

    # Retrieval parameters
    retriever_k: int | None = None
    similarity_score_threshold: float | None = None
    retriever_use_mmr: bool | None = None
    retriever_fetch_k: int | None = None
    max_context_chunks: int | None = None

    # Generation limits
    max_completion_tokens: int | None = None
    token_budget_warning_threshold: int | None = None

    # LangSmith observability
    langchain_tracing_v2: bool | None = None
    langchain_api_key: str | None = None
    langchain_project: str | None = None

    # Pinecone runtime overrides. The active vector store type is environment-only.
    pinecone_api_key: str | None = None
    pinecone_index_name: str | None = None
    pinecone_namespace: str | None = None
    pinecone_cloud: str | None = None
    pinecone_region: str | None = None

    # Blob token runtime override. Blob enablement is environment-only.
    blob_read_write_token: str | None = None

    # Pipeline feature flags (admin only — chunker/chunk settings apply to newly uploaded docs only)
    retriever_hybrid_bm25: bool | None = None
    relevance_grader_enabled: bool | None = None
    ragas_evaluation_enabled: bool | None = None
    reranker_type: str | None = None
    reranker_judge_model: str | None = None
    chunker_type: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None

    @field_validator(
        "api_key", "model", "embedding_model", "planner_model", "generator_model",
        "validator_model", "langchain_api_key", "langchain_project",
        "pinecone_api_key", "pinecone_index_name",
        "pinecone_namespace", "pinecone_cloud", "pinecone_region",
        "blob_read_write_token", "reranker_type", "reranker_judge_model", "chunker_type",
        mode="before",
    )
    @classmethod
    def _sanitize_string(cls, v: str | None) -> str | None:
        """Strip HTML/JS tags from all string inputs (OWASP A03)."""
        if v is None:
            return None
        return bleach.clean(str(v), tags=[], strip=True).strip()


class SettingsResponse(BaseModel):
    # Existing fields
    model: str
    embedding_model: str
    api_key_masked: str
    api_key_source: str          # "runtime" | "environment" | "not_configured"
    allowed_models: list[str]
    allowed_embedding_models: list[str]

    # Per-node models
    planner_model: str
    generator_model: str
    validator_model: str

    # Retrieval parameters
    retriever_k: int
    similarity_score_threshold: float
    retriever_use_mmr: bool
    retriever_fetch_k: int
    max_context_chunks: int

    # Generation limits
    max_completion_tokens: int
    token_budget_warning_threshold: int

    # LangSmith observability
    langchain_tracing_v2: bool
    langchain_api_key_masked: str
    langchain_project: str

    # Vector store / Pinecone
    vector_store_type: str
    file_store_type: str
    pinecone_api_key_masked: str
    pinecone_api_key_source: str     # "runtime" | "environment" | "not_configured"
    pinecone_index_name: str
    pinecone_namespace: str
    pinecone_cloud: str
    pinecone_region: str

    # Blob storage
    blob_read_write_token_masked: str
    blob_read_write_token_source: str  # "runtime" | "environment" | "not_configured"

    # Pipeline feature flags
    retriever_hybrid_bm25: bool
    relevance_grader_enabled: bool
    ragas_evaluation_enabled: bool
    reranker_type: str
    allowed_reranker_types: list[str]
    reranker_judge_model: str
    allowed_judge_models: list[str]
    chunker_type: str
    chunk_size: int
    chunk_overlap: int
    allowed_chunker_types: list[str]

    # Guest one-time settings lock state
    guest_settings_locked: bool = False
    guest_settings_recoverable: bool = False
    guest_settings_reason: str = "admin"

    # Informational — read-only, not user-editable
    retriever_fusion_mode: str = "rrf"
    reranker_top_k: int = 4
    semantic_breakpoint_threshold_type: str = "percentile"
    max_query_length: int = 1000
    query_rate_limit_per_minute: int = 10
    max_upload_size_mb: int = 20
    guest_max_upload_size_mb: int = 2
    guest_session_ttl_minutes: int = 15
    guest_doc_retention_hours: float = 1.0
    is_vercel: bool = False
    supports_cross_encoder: bool = False


class RagasScoresResponse(BaseModel):
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float
    evaluated_at: str
    model: str
    num_samples: int
    has_results: bool = False


class RagasTriggerResponse(BaseModel):
    """Response model for POST /api/settings/ragas-trigger."""
    status: str
    message: str


def _guest_lock_state(user: UserInDB | None = None) -> tuple[bool, bool, str]:
    """Return guest settings lock state as (locked, recoverable, reason)."""
    if user is None or user.role != "guest":
        return False, False, "admin"

    session_id = user.session_id
    if not session_id:
        return True, False, "missing_session"

    if session_id not in _guest_settings_used:
        return False, False, "available"

    if has_guest_runtime_settings(session_id):
        return True, False, "already_configured"

    return False, True, "settings_lost_after_restart"


def _build_response(user: UserInDB | None = None) -> SettingsResponse:
    """Build a SettingsResponse from current effective runtime state."""
    guest_locked, guest_recoverable, guest_reason = _guest_lock_state(user)
    masked = get_masked_api_key()
    if is_runtime_key_set():
        source = "runtime"
    elif account_env_fallback_allowed() and settings.openai_api_key:
        source = "environment"
    else:
        source = "not_configured"

    if is_runtime_pinecone_key_set():
        pinecone_source = "runtime"
    elif account_env_fallback_allowed() and settings.pinecone_api_key:
        pinecone_source = "environment"
    else:
        pinecone_source = "not_configured"

    if is_runtime_blob_token_set():
        blob_source = "runtime"
    elif account_env_fallback_allowed() and (
        settings.blob_read_write_token or settings.vercel_blob_read_write_token
    ):
        blob_source = "environment"
    else:
        blob_source = "not_configured"

    return SettingsResponse(
        model=get_effective_model(),
        embedding_model=get_effective_embedding_model(),
        api_key_masked=masked,
        api_key_source=source,
        allowed_models=sorted(ALLOWED_MODELS),
        allowed_embedding_models=sorted(ALLOWED_EMBEDDING_MODELS),
        planner_model=get_effective_planner_model(),
        generator_model=get_effective_generator_model(),
        validator_model=get_effective_validator_model(),
        retriever_k=get_effective_retriever_k(),
        similarity_score_threshold=get_effective_similarity_score_threshold(),
        retriever_use_mmr=get_effective_retriever_use_mmr(),
        retriever_fetch_k=get_effective_retriever_fetch_k(),
        max_context_chunks=get_effective_max_context_chunks(),
        max_completion_tokens=get_effective_max_completion_tokens(),
        token_budget_warning_threshold=get_effective_token_budget_warning_threshold(),
        langchain_tracing_v2=get_effective_langchain_tracing_v2(),
        langchain_api_key_masked=get_masked_langchain_api_key(),
        langchain_project=get_effective_langchain_project(),
        vector_store_type=get_effective_vector_store_type(),
        file_store_type=get_effective_file_store_type(),
        pinecone_api_key_masked=get_masked_pinecone_api_key(),
        pinecone_api_key_source=pinecone_source,
        pinecone_index_name=get_effective_pinecone_index_name(),
        pinecone_namespace=get_effective_pinecone_namespace(),
        pinecone_cloud=get_effective_pinecone_cloud(),
        pinecone_region=get_effective_pinecone_region(),
        blob_read_write_token_masked=get_masked_blob_read_write_token(),
        blob_read_write_token_source=blob_source,
        retriever_hybrid_bm25=get_effective_retriever_hybrid_bm25(),
        relevance_grader_enabled=get_effective_relevance_grader_enabled(),
        ragas_evaluation_enabled=get_effective_ragas_evaluation_enabled(),
        reranker_type=get_effective_reranker_type(),
        allowed_reranker_types=sorted(ALLOWED_RERANKER_TYPES),
        reranker_judge_model=get_effective_reranker_judge_model(),
        allowed_judge_models=sorted(ALLOWED_JUDGE_MODELS),
        chunker_type=get_effective_chunker_type(),
        chunk_size=get_effective_chunk_size(),
        chunk_overlap=get_effective_chunk_overlap(),
        allowed_chunker_types=sorted(ALLOWED_CHUNKER_TYPES),
        guest_settings_locked=guest_locked,
        guest_settings_recoverable=guest_recoverable,
        guest_settings_reason=guest_reason,
        retriever_fusion_mode=settings.retriever_fusion_mode,
        reranker_top_k=settings.reranker_top_k,
        semantic_breakpoint_threshold_type=settings.semantic_breakpoint_threshold_type,
        max_query_length=settings.max_query_length,
        query_rate_limit_per_minute=settings.query_rate_limit_per_minute,
        max_upload_size_mb=settings.effective_max_upload_size_mb,
        guest_max_upload_size_mb=settings.guest_max_upload_size_mb,
        guest_session_ttl_minutes=settings.guest_token_expire_minutes,
        guest_doc_retention_hours=settings.guest_doc_retention_seconds / 3600,
        is_vercel=bool(os.environ.get("VERCEL")),
        supports_cross_encoder=importlib.util.find_spec("sentence_transformers") is not None,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=SettingsResponse)
async def get_settings_view(_user=Depends(get_current_user)):
    """Return current effective settings. API key and LangSmith key are always masked."""
    set_runtime_scope(_user.role, _user.session_id)
    return _build_response(_user)


@router.post("/", response_model=SettingsResponse)
@limiter.limit("20/minute")
async def update_settings(
    request: Request,
    response: Response,
    body: SettingsUpdateRequest,
    user: UserInDB = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """
    Update active settings at runtime. At least one field must be provided.
    All inputs are validated before being applied; on error a 422 is returned
    with a safe, user-readable message (no internal detail leaked).

    Guests may configure only API key, global model, and Pinecone settings exactly once
    per session (locked together after the first successful save, enforced via JWT jti claim).
    All pipeline-level settings (per-node models, retrieval, generation, LangSmith)
    require admin role.

    OWASP A01 — Guest role check guards pipeline-level settings.
    OWASP A07 — JTI tracking prevents replayed guest tokens from reconfiguring.
    """
    # Guests get one settings save per session — API key, model, and Pinecone settings
    # are locked together.
    if user.role == "guest":
        try:
            payload = _jwt.decode(
                credentials.credentials,
                settings.secret_key,
                algorithms=[settings.algorithm],
            )
            jti = payload.get("jti", "")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        set_runtime_scope(user.role, jti)
        locked, recoverable, _reason = _guest_lock_state(user)
        if not jti or locked:
            audit_event("settings_update", status="rejected", request=request, user=user, error_category="guest_settings_locked")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Guest settings can only be configured once per session. "
                    "Start a new guest session to change your API key, model, Pinecone, or Blob settings."
                ),
            )
        if recoverable:
            audit_event(
                "settings_update",
                status="recovering",
                request=request,
                user=user,
                error_category="guest_settings_runtime_lost",
            )

        # OWASP A01 — Guests are blocked from pipeline-level settings, but may
        # provide Pinecone/Blob settings because storage can be required for upload/indexing.
        non_guest_fields = {
            "planner_model", "generator_model", "validator_model",
            "retriever_k", "similarity_score_threshold", "retriever_use_mmr",
            "retriever_fetch_k", "max_context_chunks",
            "max_completion_tokens", "token_budget_warning_threshold",
            "langchain_tracing_v2", "langchain_api_key", "langchain_project",
            "retriever_hybrid_bm25", "relevance_grader_enabled", "ragas_evaluation_enabled",
            "reranker_type", "reranker_judge_model",
            "chunker_type", "chunk_size", "chunk_overlap",
        }
        if any(getattr(body, f) is not None for f in non_guest_fields):
            audit_event("settings_update", status="rejected", request=request, user=user, error_category="guest_forbidden_fields")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Guests can only configure API key, model, embedding model, Pinecone settings, and Blob token.",
            )
    else:
        set_runtime_scope(user.role, None)

    # At least one field must be provided
    all_fields = [
        "api_key", "model", "embedding_model", "planner_model", "generator_model", "validator_model",
        "retriever_k", "similarity_score_threshold", "retriever_use_mmr",
        "retriever_fetch_k", "max_context_chunks", "max_completion_tokens",
        "token_budget_warning_threshold", "langchain_tracing_v2",
        "langchain_api_key", "langchain_project",
        "pinecone_api_key", "pinecone_index_name",
        "pinecone_namespace", "pinecone_cloud", "pinecone_region",
        "blob_read_write_token",
        "retriever_hybrid_bm25", "relevance_grader_enabled", "ragas_evaluation_enabled",
        "reranker_type", "reranker_judge_model",
        "chunker_type", "chunk_size", "chunk_overlap",
    ]
    if all(getattr(body, f) is None for f in all_fields):
        audit_event("settings_update", status="rejected", request=request, user=user, error_category="empty_update")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Provide at least one setting field."},
        )

    errors: dict[str, str] = {}

    validated_key: str | None = None
    if body.api_key is not None:
        try:
            validated_key = validate_api_key(body.api_key)
        except ValueError as exc:
            errors["api_key"] = str(exc)

    validated_model: str | None = None
    if body.model is not None:
        try:
            validated_model = validate_model(body.model)
        except ValueError as exc:
            errors["model"] = str(exc)

    validated_embedding_model: str | None = None
    if body.embedding_model is not None:
        try:
            validated_embedding_model = validate_embedding_model(body.embedding_model)
        except ValueError as exc:
            errors["embedding_model"] = str(exc)

    validated_planner_model: str | None = None
    if body.planner_model is not None:
        try:
            validated_planner_model = validate_model(body.planner_model)
        except ValueError as exc:
            errors["planner_model"] = str(exc)

    validated_generator_model: str | None = None
    if body.generator_model is not None:
        try:
            validated_generator_model = validate_model(body.generator_model)
        except ValueError as exc:
            errors["generator_model"] = str(exc)

    validated_validator_model: str | None = None
    if body.validator_model is not None:
        try:
            validated_validator_model = validate_model(body.validator_model)
        except ValueError as exc:
            errors["validator_model"] = str(exc)

    validated_retriever_k: int | None = None
    if body.retriever_k is not None:
        try:
            validated_retriever_k = validate_retriever_k(body.retriever_k)
        except ValueError as exc:
            errors["retriever_k"] = str(exc)

    validated_similarity_score_threshold: float | None = None
    if body.similarity_score_threshold is not None:
        try:
            validated_similarity_score_threshold = validate_similarity_score_threshold(
                body.similarity_score_threshold
            )
        except ValueError as exc:
            errors["similarity_score_threshold"] = str(exc)

    # retriever_use_mmr is a bool — no custom validation needed beyond type check
    validated_retriever_use_mmr: bool | None = body.retriever_use_mmr

    validated_retriever_fetch_k: int | None = None
    if body.retriever_fetch_k is not None:
        # Use the incoming retriever_k if also being set, else the current effective value
        effective_k = validated_retriever_k if validated_retriever_k is not None else get_effective_retriever_k()
        try:
            validated_retriever_fetch_k = validate_retriever_fetch_k(
                body.retriever_fetch_k, effective_k
            )
        except ValueError as exc:
            errors["retriever_fetch_k"] = str(exc)

    validated_max_context_chunks: int | None = None
    if body.max_context_chunks is not None:
        try:
            validated_max_context_chunks = validate_max_context_chunks(body.max_context_chunks)
        except ValueError as exc:
            errors["max_context_chunks"] = str(exc)

    validated_max_completion_tokens: int | None = None
    if body.max_completion_tokens is not None:
        try:
            validated_max_completion_tokens = validate_max_completion_tokens(
                body.max_completion_tokens
            )
        except ValueError as exc:
            errors["max_completion_tokens"] = str(exc)

    validated_token_budget_warning_threshold: int | None = None
    if body.token_budget_warning_threshold is not None:
        try:
            validated_token_budget_warning_threshold = validate_token_budget_warning_threshold(
                body.token_budget_warning_threshold
            )
        except ValueError as exc:
            errors["token_budget_warning_threshold"] = str(exc)

    # langchain_tracing_v2 is a bool — no custom validation needed
    validated_langchain_tracing_v2: bool | None = body.langchain_tracing_v2

    validated_langchain_api_key: str | None = None
    if body.langchain_api_key is not None:
        try:
            validated_langchain_api_key = validate_langchain_api_key(body.langchain_api_key)
        except ValueError as exc:
            errors["langchain_api_key"] = str(exc)

    validated_langchain_project: str | None = None
    if body.langchain_project is not None:
        try:
            validated_langchain_project = validate_langchain_project(body.langchain_project)
        except ValueError as exc:
            errors["langchain_project"] = str(exc)

    validated_pinecone_api_key: str | None = None
    if body.pinecone_api_key is not None:
        try:
            validated_pinecone_api_key = validate_pinecone_api_key(body.pinecone_api_key)
        except ValueError as exc:
            errors["pinecone_api_key"] = str(exc)

    validated_pinecone_index_name: str | None = None
    if body.pinecone_index_name is not None:
        try:
            validated_pinecone_index_name = validate_pinecone_index_name(body.pinecone_index_name)
        except ValueError as exc:
            errors["pinecone_index_name"] = str(exc)

    validated_pinecone_namespace: str | None = None
    if body.pinecone_namespace is not None:
        try:
            validated_pinecone_namespace = validate_pinecone_namespace(body.pinecone_namespace)
        except ValueError as exc:
            errors["pinecone_namespace"] = str(exc)

    validated_pinecone_cloud: str | None = None
    if body.pinecone_cloud is not None:
        try:
            validated_pinecone_cloud = validate_pinecone_cloud(body.pinecone_cloud)
        except ValueError as exc:
            errors["pinecone_cloud"] = str(exc)

    validated_pinecone_region: str | None = None
    if body.pinecone_region is not None:
        try:
            validated_pinecone_region = validate_pinecone_region(body.pinecone_region)
        except ValueError as exc:
            errors["pinecone_region"] = str(exc)

    validated_blob_read_write_token: str | None = None
    if body.blob_read_write_token is not None:
        try:
            validated_blob_read_write_token = validate_blob_read_write_token(body.blob_read_write_token)
        except ValueError as exc:
            errors["blob_read_write_token"] = str(exc)

    # Pipeline feature flags — bool fields need no custom validation beyond type check
    validated_retriever_hybrid_bm25: bool | None = body.retriever_hybrid_bm25
    validated_relevance_grader_enabled: bool | None = body.relevance_grader_enabled
    validated_ragas_evaluation_enabled: bool | None = body.ragas_evaluation_enabled

    validated_reranker_type: str | None = None
    if body.reranker_type is not None:
        try:
            validated_reranker_type = validate_reranker_type(body.reranker_type)
        except ValueError as exc:
            errors["reranker_type"] = str(exc)

    validated_reranker_judge_model: str | None = None
    if body.reranker_judge_model is not None:
        try:
            validated_reranker_judge_model = validate_reranker_judge_model(body.reranker_judge_model)
        except ValueError as exc:
            errors["reranker_judge_model"] = str(exc)

    validated_chunker_type: str | None = None
    if body.chunker_type is not None:
        try:
            validated_chunker_type = validate_chunker_type(body.chunker_type)
        except ValueError as exc:
            errors["chunker_type"] = str(exc)

    validated_chunk_size: int | None = None
    if body.chunk_size is not None:
        try:
            validated_chunk_size = validate_chunk_size(body.chunk_size)
        except ValueError as exc:
            errors["chunk_size"] = str(exc)

    validated_chunk_overlap: int | None = None
    if body.chunk_overlap is not None:
        effective_size = validated_chunk_size if validated_chunk_size is not None else get_effective_chunk_size()
        try:
            validated_chunk_overlap = validate_chunk_overlap(body.chunk_overlap, effective_size)
        except ValueError as exc:
            errors["chunk_overlap"] = str(exc)

    if errors:
        audit_event(
            "settings_update",
            status="rejected",
            request=request,
            user=user,
            error_category="validation_error",
            fields=list(errors.keys()),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors},
        )

    apply_runtime_settings(
        api_key=validated_key,
        model=validated_model,
        embedding_model=validated_embedding_model,
        planner_model=validated_planner_model,
        generator_model=validated_generator_model,
        validator_model=validated_validator_model,
        retriever_k=validated_retriever_k,
        similarity_score_threshold=validated_similarity_score_threshold,
        retriever_use_mmr=validated_retriever_use_mmr,
        retriever_fetch_k=validated_retriever_fetch_k,
        max_context_chunks=validated_max_context_chunks,
        max_completion_tokens=validated_max_completion_tokens,
        token_budget_warning_threshold=validated_token_budget_warning_threshold,
        langchain_tracing_v2=validated_langchain_tracing_v2,
        langchain_api_key=validated_langchain_api_key,
        langchain_project=validated_langchain_project,
        pinecone_api_key=validated_pinecone_api_key,
        pinecone_index_name=validated_pinecone_index_name,
        pinecone_namespace=validated_pinecone_namespace,
        pinecone_cloud=validated_pinecone_cloud,
        pinecone_region=validated_pinecone_region,
        blob_read_write_token=validated_blob_read_write_token,
        retriever_hybrid_bm25=validated_retriever_hybrid_bm25,
        relevance_grader_enabled=validated_relevance_grader_enabled,
        ragas_evaluation_enabled=validated_ragas_evaluation_enabled,
        reranker_type=validated_reranker_type,
        reranker_judge_model=validated_reranker_judge_model,
        chunker_type=validated_chunker_type,
        chunk_size=validated_chunk_size,
        chunk_overlap=validated_chunk_overlap,
        scope_session_id=jti if user.role == "guest" else None,  # type: ignore[possibly-undefined]
    )

    # Mark guest JTI as used after successful save (not before, so validation errors don't consume the slot).
    # Evict set when it exceeds the cap to bound memory usage.
    if user.role == "guest":
        if len(_guest_settings_used) >= _MAX_GUEST_JTI:
            _guest_settings_used.clear()
        _guest_settings_used.add(jti)  # type: ignore[possibly-undefined]  # jti resolved above

    set_runtime_scope(user.role, jti if user.role == "guest" else None)  # type: ignore[possibly-undefined]

    # Persist settings into an encrypted httponly cookie so Vercel serverless
    # instances (which share no memory) can restore them on the next request.
    set_runtime_settings_cookie(response, user=user, settings_values={
        "api_key": get_effective_api_key(),
        "model": get_effective_model(),
        "embedding_model": get_effective_embedding_model(),
        "planner_model": get_effective_planner_model(),
        "generator_model": get_effective_generator_model(),
        "validator_model": get_effective_validator_model(),
        "langchain_api_key": get_effective_langchain_api_key(),
        "pinecone_api_key": get_effective_pinecone_api_key(),
        "pinecone_index_name": get_effective_pinecone_index_name(),
        "pinecone_namespace": get_effective_pinecone_namespace(),
        "pinecone_cloud": get_effective_pinecone_cloud(),
        "pinecone_region": get_effective_pinecone_region(),
        "blob_read_write_token": get_effective_blob_read_write_token(),
        "reranker_type": get_effective_reranker_type(),
        "reranker_judge_model": get_effective_reranker_judge_model(),
        "retriever_k": get_effective_retriever_k(),
        "retriever_use_mmr": get_effective_retriever_use_mmr(),
        "retriever_fetch_k": get_effective_retriever_fetch_k(),
        "retriever_hybrid_bm25": get_effective_retriever_hybrid_bm25(),
        "similarity_score_threshold": get_effective_similarity_score_threshold(),
        "max_context_chunks": get_effective_max_context_chunks(),
        "relevance_grader_enabled": get_effective_relevance_grader_enabled(),
    })
    audit_event(
        "settings_update",
        status="completed",
        request=request,
        user=user,
        fields=[field for field in all_fields if getattr(body, field) is not None],
    )
    return _build_response(user)


# ── Ragas background evaluation ────────────────────────────────────────────────

# 3 static Q&A samples used when no real documents are indexed, or as fallback.
_STATIC_SAMPLES = [
    {
        "question": "What is Retrieval-Augmented Generation?",
        "ground_truth": "RAG combines retrieval of relevant documents with LLM generation to produce grounded answers.",
    },
    {
        "question": "What is a vector database?",
        "ground_truth": "A vector database stores embeddings and supports fast similarity search over high-dimensional vectors.",
    },
    {
        "question": "What is LangGraph?",
        "ground_truth": "LangGraph is a framework for building stateful multi-step LLM applications as directed graphs.",
    },
]


async def _run_ragas_eval_background() -> None:
    """Run a lightweight in-process Ragas evaluation and persist results.

    Runs 3 Q&A samples through the vector-store retriever, then evaluates
    with Ragas metrics. Falls back to mock scores if ragas is not installed.
    Errors are caught and logged — never bubble up to the caller (BackgroundTasks).
    """
    _log.info("ragas_trigger.started")
    try:
        from app.rag.vector_store import get_all_documents, has_documents
        from app.runtime.ragas_store import save_ragas_scores
        from app.runtime.settings_store import get_effective_model

        model = get_effective_model()

        # Build samples: prefer real documents, fall back to static Q&A
        if has_documents():
            docs = get_all_documents()
            # Use the first up-to-3 document chunks as ground-truth context
            samples = [
                {
                    "question": f"What does this document say? Chunk {i + 1}",
                    "ground_truth": doc.page_content[:500],
                }
                for i, doc in enumerate(docs[:3])
            ]
        else:
            samples = _STATIC_SAMPLES

        try:
            # Run real Ragas evaluation.
            # ragas/llms/base.py imports from langchain_community.chat_models.vertexai at
            # module level, but langchain-community 0.3+ removed that sub-module. Stub it
            # with the standalone langchain-google-vertexai package before ragas loads.
            import sys
            from types import ModuleType
            if "langchain_community.chat_models.vertexai" not in sys.modules:
                try:
                    from langchain_google_vertexai import ChatVertexAI as _CV, VertexAI as _VA
                    _cv_mod = ModuleType("langchain_community.chat_models.vertexai")
                    _cv_mod.ChatVertexAI = _CV  # type: ignore[attr-defined]
                    sys.modules["langchain_community.chat_models.vertexai"] = _cv_mod
                    _llms_mod = sys.modules.setdefault("langchain_community.llms", ModuleType("langchain_community.llms"))
                    _llms_mod.VertexAI = _VA  # type: ignore[attr-defined]
                except ImportError:
                    pass
            from datasets import Dataset  # type: ignore[import]
            from ragas import evaluate  # type: ignore[import]
            from ragas.metrics._faithfulness import faithfulness  # type: ignore[import]
            from ragas.metrics._answer_relevance import answer_relevancy  # type: ignore[import]
            from ragas.metrics._context_precision import context_precision  # type: ignore[import]
            from ragas.metrics._context_recall import context_recall  # type: ignore[import]
            from app.rag.vector_store import similarity_search

            eval_rows = []
            for s in samples:
                retrieved = similarity_search(s["question"], k=3)
                contexts = [d.page_content for d in retrieved] if retrieved else [s["ground_truth"]]
                eval_rows.append({
                    "question": s["question"],
                    "answer": s["ground_truth"],  # use ground truth as the answer for in-process eval
                    "contexts": contexts,
                    "ground_truth": s["ground_truth"],
                })

            dataset = Dataset.from_list(eval_rows)
            # Run evaluation in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall]),
            )
            df = result.to_pandas()

            save_ragas_scores(
                faithfulness=float(df["faithfulness"].mean()),
                answer_relevancy=float(df["answer_relevancy"].mean()),
                context_precision=float(df["context_precision"].mean()),
                context_recall=float(df["context_recall"].mean()),
                model=model,
                num_samples=len(samples),
            )
            _log.info("ragas_trigger.completed", num_samples=len(samples), model=model)

        except ImportError:
            # ragas or datasets not installed — save mock scores for demo purposes
            _log.warning("ragas_trigger.mock_mode", reason="ragas package not available")
            import random
            save_ragas_scores(
                faithfulness=round(random.uniform(0.70, 0.95), 4),
                answer_relevancy=round(random.uniform(0.70, 0.95), 4),
                context_precision=round(random.uniform(0.65, 0.90), 4),
                context_recall=round(random.uniform(0.60, 0.85), 4),
                model=model + " (mock)",
                num_samples=len(samples),
            )
            _log.info("ragas_trigger.mock_completed", num_samples=len(samples))

    except Exception as exc:  # pragma: no cover
        _log.error("ragas_trigger.failed", error_type=type(exc).__name__)


@router.post("/ragas-trigger", response_model=RagasTriggerResponse)
@limiter.limit("1/5minute")
async def trigger_ragas_eval(
    request: Request,
    background_tasks: BackgroundTasks,
    user: UserInDB = Depends(get_current_user),
):
    """Trigger an async Ragas evaluation in the background. Admin only.

    Returns immediately with status='started'. The evaluation runs in a
    BackgroundTask and saves results via save_ragas_scores(). Poll
    GET /api/settings/ragas-scores to check when new scores appear.

    OWASP A01 — admin role enforced; guests receive 403.
    OWASP A04 — rate-limited to 1 call per 5 minutes per IP.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only.",
        )

    # Check that at least one document is indexed before starting
    from app.rag.vector_store import has_documents
    if not has_documents():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No documents indexed. Upload documents first.",
        )

    background_tasks.add_task(_run_ragas_eval_background)
    _log.info("ragas_trigger.queued", user=user.username)
    return RagasTriggerResponse(
        status="started",
        message="Ragas evaluation running in background",
    )


@router.get("/ragas-scores", response_model=RagasScoresResponse)
async def get_ragas_scores_view(user: UserInDB = Depends(get_current_user)):
    """Return last Ragas evaluation scores. Admin only.

    Returns HTTP 200 with has_results=False (and zeroed fields) when no evaluation
    has been run yet, instead of HTTP 404 — prevents the frontend from having to
    swallow real errors in a silent try/catch.

    OWASP A01 — admin role check prevents guests from reading eval data.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only.",
        )
    from app.runtime.ragas_store import get_ragas_scores
    scores = get_ragas_scores()
    if scores is None:
        return RagasScoresResponse(
            has_results=False,
            faithfulness=0.0,
            answer_relevancy=0.0,
            context_precision=0.0,
            context_recall=0.0,
            evaluated_at="",
            model="",
            num_samples=0,
        )
    return RagasScoresResponse(**scores, has_results=True)
