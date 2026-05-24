"""
Multi-agent RAG workflow using LangGraph.

Flow:  planner → hyde → retriever → grader → reranker → generator → validator
         └─(NEEDS_REVISION, retry_count < MAX_RETRIES)──────────────→ generator
         └─(VALID or max retries reached)──────────────────────────→ END

Search improvements applied at each stage:

1. Multi-Query Retrieval (planner_node):
   Generates 2 alternative query phrasings alongside the primary rewrite.
   The retriever fans-out across all 3 queries and fuses results.

2. HyDE — Hypothetical Document Embeddings (hyde_node):
   Generates a short hypothetical document passage that *would* answer the
   question.  Embedding the passage (rather than the bare question) lands in
   the same vector space as stored document text, improving recall for
   abstract or ambiguous questions.

3. Contextual Chunk Headers (applied at index time in chunking.py):
   Each chunk is prefixed with "[Document: <source>]" before embedding so
   the vector captures document provenance alongside content semantics.

4. Reranking (reranker_node — Feature 4):
   Two modes. RERANKER_TYPE=cross-encoder: sentence_transformers CrossEncoder
   re-scores chunks (requires pip install sentence-transformers; not on Vercel).
   RERANKER_TYPE=llm-judge: single OpenAI batch call scores all chunks 0–10;
   uses RERANKER_JUDGE_MODEL (default gpt-4.1-nano) — intentionally different
   from pipeline models; zero extra dependencies; works on Vercel.

5. RAG Fusion / RRF (retriever_node — Feature 5):
   Reciprocal Rank Fusion combines rankings from multi-query fan-out so chunks
   appearing across multiple queries score higher. Activated by default
   (RETRIEVER_FUSION_MODE=rrf). Falls back to simple dedup when set to "dedup".

6. Self-RAG Relevance Grader (grader_node — Feature 6):
   LLM-based filter that drops irrelevant chunks before generation. Adds one
   extra LLM call per query. Disabled by default (RELEVANCE_GRADER_ENABLED=false).

7. Hybrid BM25 + Dense search (retriever_node — Feature 7):
   Combines lexical BM25 results with dense vector results via RRF. Activated
   when RETRIEVER_HYBRID_BM25=true. Requires: pip install rank-bm25.

Per-node model configuration (all default to llm_model when unset):
  PLANNER_MODEL   — multi-query rewrite + HyDE + grader (lightweight; gpt-4o-mini)
  GENERATOR_MODEL — highest quality; consider "gpt-4o" in production
  VALIDATOR_MODEL — structured classification; gpt-4o-mini is sufficient

LangSmith tracing: set LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY in .env.
LangChain picks the env vars up automatically — no code changes needed here.
"""
import logging
import operator
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from functools import lru_cache
from typing import Annotated, Literal, TypedDict

import structlog
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel as PydanticBaseModel

from app.config import get_settings
from app.rag.pipeline import format_context
from app.rag.vector_store import similarity_search
from app.runtime.settings_store import (
    account_env_fallback_allowed,
    get_effective_api_key,
    get_effective_generator_model,
    get_effective_max_completion_tokens,
    get_effective_model,
    get_effective_planner_model,
    get_effective_token_budget_warning_threshold,
    get_effective_validator_model,
    get_effective_retriever_hybrid_bm25,
    get_effective_relevance_grader_enabled,
    get_effective_reranker_type,
    get_effective_reranker_judge_model,
)

def _cb_tokens(cb) -> int:
    """Sum total_tokens from UsageMetadataCallbackHandler across all models."""
    return sum(v.get("total_tokens", 0) for v in cb.usage_metadata.values())


settings = get_settings()
log = structlog.get_logger()
_logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


# ── State schema ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    question: str
    # ── Multi-query / HyDE search state ──────────────────────────────────────
    query_variants: list[str]     # alternative phrasings from planner (multi-query)
    hypothetical_answer: str      # HyDE passage; used as an additional search query
    # ── RAG pipeline state ────────────────────────────────────────────────────
    retrieved_docs: list          # raw Document objects — passed between retriever/grader/reranker
    retrieved_context: str
    answer: str
    validation: str
    tokens_used: int
    retry_count: int              # generator retry counter; incremented by validator
    messages: Annotated[list[BaseMessage], operator.add]
    sources: list[str]
    # ── Telemetry fields ──────────────────────────────────────────────────────
    original_question: str        # set once in run_agent(), never mutated
    refined_query: str            # primary rewritten query from planner_node
    chunks_found: int             # unique chunks after fan-out + fusion
    chunks_after_grading: int     # chunks remaining after relevance grader
    chunks_after_rerank: int      # chunks remaining after reranker
    validation_reason: str        # set/overwritten by validator_node each pass
    answer_instruction: str       # generation-only presentation instruction
    planner_tokens: int
    hyde_tokens: int              # tokens used by hyde_node
    grader_tokens: int            # tokens used by grader_node (0 when disabled)
    generator_tokens: int         # accumulates across retries
    validator_tokens: int         # accumulates across retries
    planner_latency_ms: int
    hyde_latency_ms: int
    grader_latency_ms: int        # 0 when disabled
    reranker_latency_ms: int      # 0 when disabled
    generator_latency_ms: int     # accumulates across retries
    validator_latency_ms: int     # accumulates across retries


# ── Structured output schemas ─────────────────────────────────────────────────

class _PlannerOutput(PydanticBaseModel):
    """Multi-query planner output: one primary rewrite plus two alternatives."""
    primary_query: str
    alternatives: list[str]   # exactly 2 alternative phrasings


class _ValidationResult(PydanticBaseModel):
    status: Literal["VALID", "NEEDS_REVISION"]
    reason: str


class _RelevanceGrade(PydanticBaseModel):
    """Self-RAG grader output: indices of relevant chunks."""
    relevant_chunk_indices: list[int]  # 0-based indices of relevant chunks
    reason: str


# ── Pipeline telemetry returned by run_agent() ────────────────────────────────

class AgentTrace(PydanticBaseModel):
    """Per-node pipeline telemetry for the frontend Agent Trace accordion."""
    original_question: str
    refined_query: str
    hypothetical_answer: str    # HyDE passage generated by hyde_node
    query_variants: list[str]   # 2 alternative phrasings from planner_node
    chunks_found: int           # unique chunks after multi-query fan-out + fusion
    chunks_after_grading: int   # after self-RAG relevance filter
    chunks_after_rerank: int    # after cross-encoder reranking
    validation_reason: str
    retries: int                # number of generator revisions = retry_count - 1
    planner_tokens: int
    hyde_tokens: int
    grader_tokens: int
    generator_tokens: int
    validator_tokens: int
    planner_latency_ms: int
    hyde_latency_ms: int
    grader_latency_ms: int
    reranker_latency_ms: int
    generator_latency_ms: int
    validator_latency_ms: int
    planner_model: str
    generator_model: str
    validator_model: str


# ── LLM factory — per-node model override ────────────────────────────────────

@lru_cache(maxsize=10)
def _cached_llm(model: str, api_key: str, max_tokens: int) -> ChatOpenAI:
    """Cached ChatOpenAI constructor. Cache key = (model, api_key, max_tokens).

    When settings change the new combination produces a new cache entry and the
    old one self-evicts once the LRU capacity is reached — no explicit invalidation
    needed and no cross-request state leakage.
    """
    return ChatOpenAI(model=model, temperature=0.0, openai_api_key=api_key, max_tokens=max_tokens)


def _llm(model_override: str = "") -> ChatOpenAI:
    """Return a ChatOpenAI client for the given model (or the effective default)."""
    model = model_override or get_effective_model()
    return _cached_llm(model, get_effective_api_key(), get_effective_max_completion_tokens())


# ── RRF fusion helper ─────────────────────────────────────────────────────────

def _rrf_fuse(ranked_lists: list[list[Document]], rrf_k: int = 60) -> list[Document]:
    """Reciprocal Rank Fusion: combine multiple ranked doc lists into one.

    Each document's score = Σ 1/(rrf_k + rank_i + 1) across all lists where it
    appears. Documents appearing in multiple lists score higher.
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}
    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked):
            # Prefer a stable identity from metadata; fall back to truncated content for
            # docs that lack indexing metadata (e.g. test fixtures, blob store entries).
            meta = doc.metadata
            src = meta.get("source", "")
            idx = meta.get("chunk_index", None)
            # Use stable source::chunk_index when both are present; otherwise fall back
            # to truncated content (avoids false collisions when chunk_index is absent).
            key = f"{src}::{idx}" if (src and idx is not None) else doc.page_content[:200]
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            doc_map[key] = doc
    return [doc_map[k] for k in sorted(scores, key=scores.__getitem__, reverse=True)]


# ── Node: Planner ─────────────────────────────────────────────────────────────

_PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a search-query planning agent. Given a user question, produce:\n"
        "1. primary_query — a precise, keyword-rich rewrite that maximises semantic search recall.\n"
        "2. alternatives — exactly 2 alternative phrasings that approach the same information need "
        "from different angles (use synonyms, related concepts, or different specificity levels).\n\n"
        "Return only the structured output — no explanation.",
    ),
    ("human", "{question}"),
])


def planner_node(state: AgentState) -> AgentState:
    with get_usage_metadata_callback() as cb:
        structured_llm = _llm(get_effective_planner_model()).with_structured_output(_PlannerOutput)
        chain = _PLANNER_PROMPT | structured_llm
        t0 = time.perf_counter()
        output: _PlannerOutput = chain.invoke({"question": state["question"]})
        latency = int((time.perf_counter() - t0) * 1000)
    log.info("planner", primary=output.primary_query, alternatives=output.alternatives,
             tokens=_cb_tokens(cb), latency_ms=latency)
    return {
        **state,
        "question": output.primary_query,
        "refined_query": output.primary_query,
        "query_variants": output.alternatives,
        "tokens_used": state["tokens_used"] + _cb_tokens(cb),
        "planner_tokens": _cb_tokens(cb),
        "planner_latency_ms": latency,
        "messages": [HumanMessage(
            content=f"[Planner] primary: {output.primary_query} | variants: {output.alternatives}"
        )],
    }


# ── Node: HyDE ────────────────────────────────────────────────────────────────

_HYDE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Write a concise passage (3-5 sentences) that would appear in a knowledge base document "
        "and directly answer the following question. Write factual, document-style prose — "
        "not a conversational reply and not bullet points. Do not add preamble like "
        "'According to our policy'.",
    ),
    ("human", "{question}"),
])


def hyde_node(state: AgentState) -> AgentState:
    """Generate a hypothetical document passage for HyDE-based retrieval.

    Embedding the passage (which lives in the same vector space as stored
    document text) instead of the bare question significantly improves recall
    for abstract or paraphrased queries.
    """
    with get_usage_metadata_callback() as cb:
        chain = _HYDE_PROMPT | _llm(get_effective_planner_model()) | StrOutputParser()
        t0 = time.perf_counter()
        passage = chain.invoke({"question": state["question"]})
        latency = int((time.perf_counter() - t0) * 1000)
    log.info("hyde", chars=len(passage), tokens=_cb_tokens(cb), latency_ms=latency)
    return {
        **state,
        "hypothetical_answer": passage,
        "tokens_used": state["tokens_used"] + _cb_tokens(cb),
        "hyde_tokens": _cb_tokens(cb),
        "hyde_latency_ms": latency,
        "messages": [AIMessage(content=f"[HyDE] {len(passage)}-char hypothetical passage")],
    }


# ── Node: Retriever ───────────────────────────────────────────────────────────

def retriever_node(state: AgentState) -> AgentState:
    """Fan-out search across primary query, variants, and HyDE passage.

    Fusion strategy (RETRIEVER_FUSION_MODE):
      "rrf"   — Reciprocal Rank Fusion; chunks appearing in multiple query results
                score higher (Feature 5, default).
      "dedup" — First-seen ordering; simpler, deterministic.

    Hybrid search (RETRIEVER_HYBRID_BM25=true):
      BM25 lexical results for the primary query are added as an additional
      ranked list and fused via RRF alongside the dense results (Feature 7).
    """
    queries: list[str] = [state["question"]] + state.get("query_variants", [])
    hyde_passage = state.get("hypothetical_answer", "")
    if hyde_passage:
        queries.append(hyde_passage)

    fusion_mode = settings.retriever_fusion_mode

    if fusion_mode == "rrf":
        # Collect one ranked list per query for RRF fusion — run concurrently (P2)
        ranked_lists: list[list[Document]] = []
        with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as pool:
            futures = [
                pool.submit(lambda q=q, ctx=copy_context(): ctx.run(lambda: list(similarity_search(q))))
                for q in queries
            ]
            try:
                for fut in as_completed(futures, timeout=30):
                    ranked_lists.append(fut.result())
            except TimeoutError:
                log.warning("retriever.fanout_timeout", timeout_s=30)

        # Feature 7: add BM25 results as an additional ranked list
        if get_effective_retriever_hybrid_bm25():
            try:
                from app.rag.bm25 import bm25_search
                from app.rag.vector_store import get_all_documents
                all_corpus = get_all_documents()
                bm25_results = bm25_search(
                    state["question"], all_corpus, k=settings.retriever_k
                )
                if bm25_results:
                    ranked_lists.append([doc for doc, _ in bm25_results])
                    log.info("retriever_bm25", hits=len(bm25_results))
            except Exception as exc:
                _logger.warning("bm25_search_failed: %s", exc)

        all_docs = _rrf_fuse(ranked_lists, rrf_k=settings.retriever_rrf_k)
    else:
        # "dedup" mode — first-seen ordering (original behaviour)
        seen: set[str] = set()
        all_docs = []
        for q in queries:
            for doc in similarity_search(q):
                key = doc.page_content[:200]
                if key not in seen:
                    seen.add(key)
                    all_docs.append(doc)

    if not all_docs:
        context, sources = "No relevant documents found in the knowledge base.", []
    else:
        context = format_context(all_docs)
        sources = list({doc.metadata.get("source", "unknown") for doc in all_docs})

    log.info(
        "retriever",
        fusion=fusion_mode,
        hybrid_bm25=get_effective_retriever_hybrid_bm25(),
        queries=len(queries),
        unique_chunks=len(all_docs),
        sources=sources,
    )
    return {
        **state,
        "retrieved_docs": all_docs,
        "retrieved_context": context,
        "sources": sources,
        "chunks_found": len(all_docs),
        "chunks_after_grading": len(all_docs),  # pre-grading default
        "chunks_after_rerank": len(all_docs),   # pre-reranking default
        "messages": [AIMessage(
            content=f"[Retriever] {len(queries)} queries → {len(all_docs)} chunks ({fusion_mode})"
        )],
    }


# ── Node: Grader (Self-RAG relevance filter) ─────────────────────────────────

_GRADER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a relevance grader. Given a question and a numbered list of document chunks, "
        "return the 0-based indices of chunks that are relevant to answering the question.\n"
        "A chunk is relevant if it contains information that helps answer the question — "
        "be liberal: if a chunk is partially relevant, include it.\n"
        "If ALL chunks are irrelevant, return an empty list.",
    ),
    ("human", "Question: {question}\n\nChunks:\n{numbered_chunks}"),
])


def grader_node(state: AgentState) -> AgentState:
    """Self-RAG relevance grader — filters irrelevant chunks before generation.

    No-op when RELEVANCE_GRADER_ENABLED=false (default). When enabled, grades all
    retrieved chunks in one LLM call and drops irrelevant ones. If all chunks are
    graded irrelevant, the full set is kept as a fallback to avoid silent failures.

    Uses the planner/validator model (lightweight — no generation quality needed).
    """
    if not get_effective_relevance_grader_enabled():
        return {**state, "grader_tokens": 0, "grader_latency_ms": 0}

    docs: list[Document] = state.get("retrieved_docs", [])
    if not docs:
        return {**state, "grader_tokens": 0, "grader_latency_ms": 0}

    numbered = "\n\n".join(
        f"[{i}] {doc.metadata.get('raw_chunk', doc.page_content)}"
        for i, doc in enumerate(docs)
    )

    with get_usage_metadata_callback() as cb:
        structured_llm = _llm(get_effective_planner_model()).with_structured_output(_RelevanceGrade)
        chain = _GRADER_PROMPT | structured_llm
        t0 = time.perf_counter()
        grade: _RelevanceGrade = chain.invoke({
            "question": state["question"],
            "numbered_chunks": numbered,
        })
        latency = int((time.perf_counter() - t0) * 1000)

    kept_indices = [i for i in grade.relevant_chunk_indices if 0 <= i < len(docs)]
    if not kept_indices:
        # Fallback: keep everything rather than passing empty context to generator
        _logger.warning("grader filtered all chunks — keeping full set as fallback")
        filtered_docs = docs
    else:
        filtered_docs = [docs[i] for i in sorted(kept_indices)]

    context = format_context(filtered_docs) if filtered_docs else "No relevant documents found."
    sources = list({doc.metadata.get("source", "unknown") for doc in filtered_docs})

    log.info("grader", total=len(docs), kept=len(filtered_docs),
             reason=grade.reason, tokens=_cb_tokens(cb), latency_ms=latency)
    return {
        **state,
        "retrieved_docs": filtered_docs,
        "retrieved_context": context,
        "sources": sources,
        "chunks_after_grading": len(filtered_docs),
        "grader_tokens": _cb_tokens(cb),
        "grader_latency_ms": latency,
        "tokens_used": state["tokens_used"] + _cb_tokens(cb),
        "messages": [AIMessage(
            content=f"[Grader] {len(docs)} → {len(filtered_docs)} chunks kept"
        )],
    }


# ── Node: Reranker ────────────────────────────────────────────────────────────

# Module-level cache: CrossEncoder is expensive to load (downloads weights on first use).
# Keyed by model name so a settings change picks up a fresh instance.
_cross_encoder_cache: dict = {}


class _LLMJudgeScores(PydanticBaseModel):
    """Structured output schema for the LLM-as-judge reranker."""
    scores: list[int]


def _llm_judge_rerank(
    docs: list[Document],
    question: str,
    top_k: int,
    api_key: str,
    judge_model: str,
) -> tuple[list[Document], int]:
    """Score chunks with a single LLM batch call; return (ranked_docs[:top_k], tokens_used).

    Each chunk is truncated to 400 chars — sufficient for relevance judgement and
    keeps the prompt compact.  Falls back to first top_k docs on any error so the
    pipeline never stalls.
    """
    chunk_snippets = [
        doc.metadata.get("raw_chunk", doc.page_content)[:400]
        for doc in docs
    ]
    numbered = "\n\n".join(f"[{i + 1}] {text}" for i, text in enumerate(chunk_snippets))

    # timeout=8: if the judge LLM is slow or unresponsive, the try/except below
    # catches the timeout and falls back gracefully — the pipeline never stalls.
    llm = ChatOpenAI(
        model=judge_model,
        openai_api_key=api_key,
        max_tokens=128,
        timeout=8,
    ).with_structured_output(_LLMJudgeScores)

    prompt = (
        "Rate each document chunk's relevance to the query on a scale of 0–10 "
        "(0 = irrelevant, 10 = directly answers the query).\n\n"
        f"Query: {question}\n\n"
        f"Chunks:\n{numbered}\n\n"
        "Return a 'scores' array with one integer per chunk in the same order."
    )

    try:
        with get_usage_metadata_callback() as cb:
            result: _LLMJudgeScores = llm.invoke(prompt)
        tokens = _cb_tokens(cb)
    except Exception as exc:
        _logger.warning("LLM judge reranker failed (%s) — passing through unchanged", exc)
        return docs[:top_k], 0

    if len(result.scores) != len(docs):
        _logger.warning(
            "LLM judge returned %d scores for %d chunks — passing through unchanged",
            len(result.scores), len(docs),
        )
        return docs[:top_k], 0

    ranked = sorted(zip(docs, result.scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]], tokens


def _get_cross_encoder(model_name: str):
    """Return a cached CrossEncoder, creating it on first call for each model.

    Passes token=HF_TOKEN (if set) or token=False (explicit opt-out) so
    huggingface_hub never emits the "unauthenticated requests" warning — the
    model is public and works fine without a token; authentication is only
    needed for higher rate limits.  Set HF_TOKEN in the environment to
    enable it.
    """
    if model_name not in _cross_encoder_cache:
        from sentence_transformers import CrossEncoder
        hf_token = os.environ.get("HF_TOKEN") or False
        _cross_encoder_cache[model_name] = CrossEncoder(model_name, token=hf_token)
    return _cross_encoder_cache[model_name]


def reranker_node(state: AgentState) -> AgentState:
    """Rerank retrieved chunks by predicted relevance to the question.

    RERANKER_TYPE=none (default): pass-through, no-op.
    RERANKER_TYPE=cross-encoder: sentence_transformers CrossEncoder scores all
      (question, chunk) pairs; falls back to no-op if package absent.
    RERANKER_TYPE=llm-judge: single OpenAI batch call using RERANKER_JUDGE_MODEL
      (default gpt-4.1-nano); scores 0–10 per chunk; no extra dependencies;
      works on Vercel.

    OWASP A04: reranker_top_k is bounded by config; cannot be inflated by user input.
    """
    reranker_type = get_effective_reranker_type()
    if reranker_type == "none":
        return {**state, "reranker_latency_ms": 0}

    docs: list[Document] = state.get("retrieved_docs", [])
    if not docs:
        return {**state, "reranker_latency_ms": 0}

    if reranker_type == "cross-encoder":
        try:
            cross_encoder = _get_cross_encoder(settings.reranker_model)
        except ImportError:
            _logger.warning(
                "sentence_transformers not installed — reranker disabled. "
                "Install with: pip install sentence-transformers"
            )
            return {**state, "reranker_latency_ms": 0}

        t0 = time.perf_counter()
        pairs = [
            (state["question"], doc.metadata.get("raw_chunk", doc.page_content))
            for doc in docs
        ]
        scores = cross_encoder.predict(pairs)
        latency = int((time.perf_counter() - t0) * 1000)

        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        top_docs = [doc for doc, _ in ranked[: settings.reranker_top_k]]

        context = format_context(top_docs)
        sources = list({doc.metadata.get("source", "unknown") for doc in top_docs})

        log.info("reranker", model=settings.reranker_model,
                 input_chunks=len(docs), output_chunks=len(top_docs), latency_ms=latency)
        return {
            **state,
            "retrieved_docs": top_docs,
            "retrieved_context": context,
            "sources": sources,
            "chunks_after_rerank": len(top_docs),
            "reranker_latency_ms": latency,
            "messages": [AIMessage(
                content=f"[Reranker] {len(docs)} → {len(top_docs)} chunks (cross-encoder)"
            )],
        }

    if reranker_type == "llm-judge":
        judge_model = get_effective_reranker_judge_model()
        t0 = time.perf_counter()
        top_docs, tokens = _llm_judge_rerank(
            docs=docs,
            question=state["question"],
            top_k=settings.reranker_top_k,
            api_key=get_effective_api_key(),
            judge_model=judge_model,
        )
        latency = int((time.perf_counter() - t0) * 1000)

        context = format_context(top_docs)
        sources = list({doc.metadata.get("source", "unknown") for doc in top_docs})

        log.info(
            "reranker",
            type="llm-judge",
            model=judge_model,
            input_chunks=len(docs),
            output_chunks=len(top_docs),
            latency_ms=latency,
            tokens=tokens,
        )
        return {
            **state,
            "retrieved_docs": top_docs,
            "retrieved_context": context,
            "sources": sources,
            "chunks_after_rerank": len(top_docs),
            "reranker_latency_ms": latency,
            "messages": [AIMessage(
                content=f"[Reranker] {len(docs)} → {len(top_docs)} chunks "
                        f"(llm-judge: {judge_model})"
            )],
        }

    # Unknown reranker_type — log warning and pass through
    _logger.warning("Unknown reranker_type=%r — skipping reranking", reranker_type)
    return {**state, "reranker_latency_ms": 0}


# ── Node: Generator ───────────────────────────────────────────────────────────

_GENERATOR_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a precise document Q&A assistant.\n\n"
        "Rules:\n"
        "1. Answer the user's original question ONLY using information present in the context below.\n"
        "2. If the context defines the user's term or stage, give that document-grounded definition directly.\n"
        "3. If the context partially addresses the question, share what you can find and note any gaps.\n"
        "4. Only if the context contains NO information whatsoever related to the question, respond exactly:\n"
        "   \"I could not find sufficient information in the uploaded documents to answer this question.\"\n"
        "5. Do not answer a broader or different planner interpretation when the original question is narrower.\n"
        "6. Do not fabricate statistics, names, or details absent from the context.\n"
        "7. Be concise, factual, and cite the source name when helpful.\n\n"
        "{answer_instruction}\n\n"
        "Context:\n{context}",
    ),
    ("human", "{question}"),
])


def generator_node(state: AgentState) -> AgentState:
    question = state.get("original_question") or state["question"]
    retry_count = state.get("retry_count", 0)
    # On retry, prepend a revision hint so the model knows to be more precise
    if retry_count > 0:
        question = (
            f"[Revision attempt {retry_count}] "
            "Your previous answer was flagged as needing revision. "
            "Be more strictly grounded in the context — cite only what is explicitly stated.\n\n"
            + question
        )
    warning_threshold = get_effective_token_budget_warning_threshold()
    with get_usage_metadata_callback() as cb:
        chain = _GENERATOR_PROMPT | _llm(get_effective_generator_model()) | StrOutputParser()
        t0 = time.perf_counter()
        answer = chain.invoke({
            "context": state["retrieved_context"],
            "question": question,
            "answer_instruction": state.get("answer_instruction", ""),
        })
        latency = int((time.perf_counter() - t0) * 1000)
    tokens_total = state["tokens_used"] + _cb_tokens(cb)
    if tokens_total > warning_threshold:
        log.warning("token_budget_warning", total_tokens=tokens_total,
                    threshold=warning_threshold)
    log.info("generator", answer_chars=len(answer), tokens=_cb_tokens(cb),
             retry=retry_count, latency_ms=latency)
    return {
        **state,
        "retry_count": retry_count,
        "answer": answer,
        "tokens_used": tokens_total,
        "generator_tokens": state["generator_tokens"] + _cb_tokens(cb),
        "generator_latency_ms": state["generator_latency_ms"] + latency,
        "messages": [AIMessage(content=f"[Generator] produced {len(answer)}-char answer")],
    }


# ── Node: Validator ───────────────────────────────────────────────────────────

_VALIDATOR_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a quality-control agent. Evaluate whether the answer is faithful to the context.\n\n"
        "Mark status=VALID when:\n"
        "  (a) The answer is factually supported by the context, OR\n"
        "  (b) The answer honestly states it could not find the information — this is correct, not a failure.\n"
        "Mark status=NEEDS_REVISION ONLY when the answer makes claims that contradict or are "
        "absent from the context (hallucination).\n\n"
        "Context:\n{context}\n\nAnswer:\n{answer}",
    ),
    ("human", "Validate."),
])


def validator_node(state: AgentState) -> AgentState:
    retry_count = state.get("retry_count", 0)
    with get_usage_metadata_callback() as cb:
        structured_llm = _llm(get_effective_validator_model()).with_structured_output(_ValidationResult)
        chain = _VALIDATOR_PROMPT | structured_llm
        t0 = time.perf_counter()
        result: _ValidationResult = chain.invoke({
            "context": state["retrieved_context"],
            "answer": state["answer"],
        })
        latency = int((time.perf_counter() - t0) * 1000)
    validation = result.status
    log.info("validator", status=validation, reason=result.reason, tokens=_cb_tokens(cb),
             retry_count=retry_count, latency_ms=latency)
    return {
        **state,
        "validation": validation,
        "validation_reason": result.reason,
        "retry_count": retry_count + 1,
        "tokens_used": state["tokens_used"] + _cb_tokens(cb),
        "validator_tokens": state["validator_tokens"] + _cb_tokens(cb),
        "validator_latency_ms": state["validator_latency_ms"] + latency,
        "messages": [AIMessage(content=f"[Validator] {validation}: {result.reason}")],
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_validator(state: AgentState) -> str:
    """Route back to generator on NEEDS_REVISION (up to _MAX_RETRIES), else END."""
    if state["validation"] == "NEEDS_REVISION" and state["retry_count"] < _MAX_RETRIES:
        log.info("validator_retry", attempt=state["retry_count"])
        return "generator"
    return END


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("hyde", hyde_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("grader", grader_node)
    graph.add_node("reranker", reranker_node)
    graph.add_node("generator", generator_node)
    graph.add_node("validator", validator_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "hyde")
    graph.add_edge("hyde", "retriever")
    graph.add_edge("retriever", "grader")    # Feature 6: relevance grader
    graph.add_edge("grader", "reranker")     # Feature 4: cross-encoder reranker
    graph.add_edge("reranker", "generator")
    graph.add_edge("generator", "validator")
    graph.add_conditional_edges(
        "validator",
        _route_validator,
        {"generator": "generator", END: END},
    )

    return graph.compile()


_AGENT = None


def get_agent():
    global _AGENT
    if _AGENT is None:
        _AGENT = build_agent_graph()
    return _AGENT


def _initial_state(
    question: str,
    answer_instruction: str = "",
    retrieval_question: str | None = None,
) -> dict:
    """Build the zeroed-out AgentState dict for a fresh pipeline run."""
    return {
        "question": retrieval_question or question,
        "original_question": question,
        "query_variants": [],
        "hypothetical_answer": "",
        "retrieved_docs": [],
        "retrieved_context": "",
        "answer": "",
        "validation": "",
        "tokens_used": 0,
        "retry_count": 0,
        "messages": [],
        "sources": [],
        "refined_query": "",
        "chunks_found": 0,
        "chunks_after_grading": 0,
        "chunks_after_rerank": 0,
        "validation_reason": "",
        "answer_instruction": answer_instruction,
        "planner_tokens": 0,
        "hyde_tokens": 0,
        "grader_tokens": 0,
        "generator_tokens": 0,
        "validator_tokens": 0,
        "planner_latency_ms": 0,
        "hyde_latency_ms": 0,
        "grader_latency_ms": 0,
        "reranker_latency_ms": 0,
        "generator_latency_ms": 0,
        "validator_latency_ms": 0,
    }


def run_agent(
    question: str,
    answer_instruction: str = "",
    retrieval_question: str | None = None,
) -> dict:
    """Execute the full 7-node pipeline and return an AgentTrace with telemetry.

    Returns a dict compatible with ``QueryResponse``, including an ``AgentTrace``
    instance with per-node telemetry for frontend display.
    """
    planner_model = get_effective_planner_model()
    generator_model = get_effective_generator_model()
    validator_model = get_effective_validator_model()

    result = get_agent().invoke(_initial_state(question, answer_instruction, retrieval_question))

    trace = AgentTrace(
        original_question=result["original_question"],
        refined_query=result["refined_query"],
        hypothetical_answer=result.get("hypothetical_answer", ""),
        query_variants=result.get("query_variants", []),
        chunks_found=result["chunks_found"],
        chunks_after_grading=result.get("chunks_after_grading", result["chunks_found"]),
        chunks_after_rerank=result.get("chunks_after_rerank", result["chunks_found"]),
        validation_reason=result["validation_reason"],
        retries=max(0, result["retry_count"] - 1),
        planner_tokens=result["planner_tokens"],
        hyde_tokens=result.get("hyde_tokens", 0),
        grader_tokens=result.get("grader_tokens", 0),
        generator_tokens=result["generator_tokens"],
        validator_tokens=result["validator_tokens"],
        planner_latency_ms=result["planner_latency_ms"],
        hyde_latency_ms=result.get("hyde_latency_ms", 0),
        grader_latency_ms=result.get("grader_latency_ms", 0),
        reranker_latency_ms=result.get("reranker_latency_ms", 0),
        generator_latency_ms=result["generator_latency_ms"],
        validator_latency_ms=result["validator_latency_ms"],
        planner_model=planner_model,
        generator_model=generator_model,
        validator_model=validator_model,
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "validation": result["validation"],
        "tokens_used": result["tokens_used"],
        "mode": "agentic",
        "retry_count": result["retry_count"],
        "trace": trace,
    }
