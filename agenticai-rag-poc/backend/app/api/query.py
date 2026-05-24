import asyncio
import random
import re
import time
from typing import Literal

import bleach
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.core.audit import audit_event
from app.agents.rag_agent import run_agent, AgentTrace
from app.auth.utils import get_current_user
from app.auth.models import UserInDB
from app.core.chat_languages import SUPPORTED_LANGUAGES, ChatLanguageCode
from app.config import get_settings
from app.core.errors import SafeAppError, safe_app_error_from_exception
from app.runtime.settings_store import get_effective_ragas_evaluation_enabled, is_runtime_key_set
from app.guardrails.engine import GuardrailEngine
from app.guardrails.store import get_guardrail_store
from app.guardrails.safety import sanitize_query
from app.api.documents import _list_visible_document_names
from app.rag.pipeline import run_simple_rag
from app.rag.vector_store import set_retrieval_metadata_filter

settings = get_settings()
log = structlog.get_logger()
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_guardrail_engine = GuardrailEngine()

_RAGAS_AUTO_TRIGGER_INTERVAL: int = 50


def _retrieval_filter_for_user(user: UserInDB) -> dict:
    if user.role == "guest":
        return {"owner_role": "guest", "owner_session": {"$eq": user.session_id or ""}}
    return {"owner_role": {"$ne": "guest"}}


def _has_visible_documents(user: UserInDB) -> bool:
    return bool(_list_visible_document_names(user))


class QueryHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=1200)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    mode: Literal["simple", "agentic"] = "agentic"
    language: ChatLanguageCode = "en"
    history: list[QueryHistoryMessage] = Field(default_factory=list, max_length=6)


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    validation: str
    tokens_used: int = 0
    mode: str
    language: str = "en"
    retry_count: int = 0
    latency_ms: int = 0
    output_flagged: bool = False  # True when output guardrail fired; violations are NOT exposed
    trace: AgentTrace | None = None


def _answer_instruction_for_language(language: str) -> str:
    language_name = SUPPORTED_LANGUAGES.get(language, "English")
    if language == "en":
        return ""
    return (
        f"Answer in {language_name}. Keep source grounding and do not translate source filenames."
    )


def _check_input_guardrail(text: str, *, surface: str) -> None:
    result = _guardrail_engine.check(text, "input")
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query blocked by content policy.",
        )
    if result.flagged:
        log.warning(
            "query_flagged",
            surface=surface,
            violations=[v.rule_id for v in result.violations],
        )


_RAG_ACRONYM_RE = re.compile(r"\brag\b", re.IGNORECASE)
_INGESTION_RE = re.compile(r"\bingest(?:ion|ing|ed)?\b", re.IGNORECASE)


def _expand_retrieval_terms(question: str) -> str:
    """Add common domain expansions that improve vector recall without changing UI text."""
    expansions: list[str] = []
    if _RAG_ACRONYM_RE.search(question):
        expansions.append("Retrieval-Augmented Generation")
    if _INGESTION_RE.search(question):
        expansions.append("document ingestion upload indexing chunking embedding vector store")
    if not expansions:
        return question
    return f"{question}\n\nSearch terms: {'; '.join(expansions)}"


def _history_snippet(content: str, max_chars: int = 360) -> str:
    """Clean chat history for retrieval context without applying query length rules."""
    clean = bleach.clean(content, tags=[], strip=True)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars]


def _contextual_retrieval_question(question: str, history: list[QueryHistoryMessage]) -> str:
    """Build a bounded retrieval query that preserves follow-up context."""
    expanded_question = _expand_retrieval_terms(question)
    if not history:
        return expanded_question

    snippets: list[str] = []
    for message in history[-4:]:
        cleaned = _history_snippet(message.content)
        if cleaned:
            snippets.append(f"{message.role}: {cleaned}")

    if not snippets:
        return expanded_question

    return (
        "Use this recent chat context only to resolve pronouns or short follow-up questions. "
        "Do not answer from the chat context; answer only from retrieved uploaded documents.\n"
        + "\n".join(snippets)
        + f"\n\nCurrent question: {expanded_question}"
    )


@router.post("/", response_model=QueryResponse)
@limiter.limit(f"{settings.query_rate_limit_per_minute}/minute")
async def query_documents(request: Request, body: QueryRequest, background_tasks: BackgroundTasks, user: UserInDB = Depends(get_current_user)):
    """
    Run a RAG query against indexed documents.

    Supports two modes via the ``mode`` field:
    - ``"agentic"`` (default): multi-agent pipeline (planner → retriever → generator → validator)
      with a faithfulness validation step.
    - ``"simple"``: single retrieve → generate pass; ``validation`` is always ``"N/A"``.

    Token usage is returned for transparency and budgeting.

    Rate-limited to {query_rate_limit_per_minute} requests/minute per IP (OWASP A04).

    Guardrail checks are applied to both the input query and the generated output:
    - Input blocked: HTTP 400 returned immediately (OWASP A03).
    - Output blocked: answer is replaced with a policy-blocked message.
    - Flagged violations are logged server-side only (OWASP A09).
    """
    set_retrieval_metadata_filter(_retrieval_filter_for_user(user))
    try:
        visible_documents = _has_visible_documents(user)
    except Exception as exc:
        safe_error = safe_app_error_from_exception(exc, default="retrieval_error")
        audit_event(
            "query",
            status="failed",
            request=request,
            user=user,
            error_category=safe_error.category,
        )
        raise safe_error from exc

    if not visible_documents:
        audit_event("query", status="rejected", request=request, user=user, error_category="no_documents")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No documents have been indexed yet. Upload at least one document first.",
        )

    clean_question = sanitize_query(body.question)
    retrieval_question = _contextual_retrieval_question(clean_question, body.history)
    answer_instruction = _answer_instruction_for_language(body.language)

    # ── Input guardrail check ─────────────────────────────────────────────────
    # Must run after sanitize_query so HTML/injection already stripped.
    # Applied to BOTH modes — sanitise_query + guardrail run BEFORE the mode branch.
    _check_input_guardrail(clean_question, surface="original")
    for message in body.history:
        if message.role == "user":
            _check_input_guardrail(sanitize_query(message.content), surface="history")
    if answer_instruction:
        _check_input_guardrail(answer_instruction, surface="language_instruction")

    try:
        audit_event("query", status="started", request=request, user=user, mode=body.mode, language=body.language)
        t0 = time.perf_counter()
        if body.mode == "simple":
            result = await asyncio.to_thread(
                run_simple_rag,
                clean_question,
                answer_instruction=answer_instruction,
                retrieval_question=retrieval_question,
            )
        else:
            result = await asyncio.to_thread(
                run_agent,
                clean_question,
                answer_instruction=answer_instruction,
                retrieval_question=retrieval_question,
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except SafeAppError:
        raise
    except Exception as exc:
        safe_error = safe_app_error_from_exception(
            exc,
            default="internal_error",
        )
        audit_event(
            "query",
            status="failed",
            request=request,
            user=user,
            error_category=safe_error.category,
            mode=body.mode,
            language=body.language,
        )
        raise safe_error from exc

    # ── Output guardrail check ────────────────────────────────────────────────
    output_result = _guardrail_engine.check(result["answer"], "output")
    if not output_result.allowed:
        result["answer"] = "Response blocked by content policy."
    else:
        result["answer"] = output_result.modified_text
    if output_result.flagged:
        log.warning(
            "output_flagged",
            violations=[v.rule_id for v in output_result.violations],
        )
    output_flagged = output_result.flagged
    audit_event(
        "query",
        status="completed",
        request=request,
        user=user,
        mode=body.mode,
        language=body.language,
        output_flagged=output_flagged,
        latency_ms=latency_ms,
    )

    # Auto-trigger Ragas evaluation probabilistically (p = 1/N per request).
    # Stateless — no shared counter — so trigger rate is correct across multiple
    # workers or serverless instances without any coordination overhead.
    if (
        random.random() < 1.0 / _RAGAS_AUTO_TRIGGER_INTERVAL
        and get_effective_ragas_evaluation_enabled()
        and is_runtime_key_set()
    ):
        from app.api.settings import _run_ragas_eval_background  # local import avoids circular dep
        background_tasks.add_task(_run_ragas_eval_background)
        log.info("ragas_auto_trigger.queued")

    return QueryResponse(**result, latency_ms=latency_ms, output_flagged=output_flagged, language=body.language)
