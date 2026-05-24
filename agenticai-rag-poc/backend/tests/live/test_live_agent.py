"""
Live agent pipeline tests — real LLM, interactive stage gates.

Tests each of the 4 LangGraph nodes individually, then runs the full pipeline,
then exercises the simple RAG path.  An ephemeral in-memory ChromaDB collection
(seeded with sample documents) is wired in so the retriever has something to
search without touching production data.

Stage flow:
  Stage 1 — Planner   : rewrites the user question for better semantic recall
  Stage 2 — Retriever : fetches chunks from the ephemeral ChromaDB
  Stage 3 — Generator : produces a grounded answer from retrieved context
  Stage 4 — Validator : quality-checks the answer against the context
  Stage 5 — Pipeline  : runs the full planner→retriever→generator→validator graph
  Stage 6 — Simple RAG: single retrieve→generate pass; validation="N/A", mode="simple"
"""
import pytest
from unittest.mock import patch
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.agents.rag_agent import (
    AgentState,
    generator_node,
    planner_node,
    retriever_node,
    run_agent,
    validator_node,
)
from app.rag.pipeline import run_simple_rag


# ── Seed data ──────────────────────────────────────────────────────────────────

_SEED_DOCS = [
    Document(
        page_content=(
            "Retrieval-Augmented Generation (RAG) grounds LLM responses in private knowledge. "
            "A RAG pipeline has three stages: (1) indexing — documents are split into chunks and "
            "embedded into a vector store; (2) retrieval — a similarity search fetches the most "
            "relevant chunks for the user's query; (3) generation — the LLM produces an answer "
            "using only the retrieved context, reducing hallucination."
        ),
        metadata={"source": "rag_overview.txt"},
    ),
    Document(
        page_content=(
            "Agentic AI extends LLMs with planning and tool use. LangGraph models agent logic as "
            "a stateful directed graph (StateGraph) and is the preferred framework for production "
            "RAG pipelines. AutoGen enables multi-agent conversation patterns. CrewAI provides a "
            "role-based crew abstraction suited to task decomposition workflows."
        ),
        metadata={"source": "agentic_frameworks.txt"},
    ),
]


# ── Module-scoped ephemeral store + similarity_search patch ───────────────────

@pytest.fixture(scope="module")
def _seeded_store(openai_api_key):
    """Ephemeral in-memory Chroma store pre-loaded with seed docs; deleted at module teardown."""
    emb = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=openai_api_key)
    store = Chroma(collection_name="live_agent_test", embedding_function=emb)
    store.add_documents(_SEED_DOCS)
    yield store
    store.delete_collection()


@pytest.fixture(scope="module")
def patch_retriever(_seeded_store):
    """
    Route similarity_search inside the agent to the ephemeral store.
    Module-scoped so it stays active for all agent stage tests.
    """
    with patch(
        "app.agents.rag_agent.similarity_search",
        side_effect=lambda q, **kw: _seeded_store.similarity_search(q, k=kw.get("k", 4)),
    ):
        yield


def _blank_state(question: str) -> AgentState:
    """Fresh AgentState with all fields zeroed — mirrors the initial state built by run_agent()."""
    return {
        "question": question,
        "original_question": question,
        "refined_query": "",
        "query_variants": [],
        "hypothetical_answer": "",
        "retrieved_docs": [],
        "retrieved_context": "",
        "answer": "",
        "validation": "",
        "validation_reason": "",
        "tokens_used": 0,
        "retry_count": 0,
        "messages": [],
        "sources": [],
        "chunks_found": 0,
        "chunks_after_grading": 0,
        "chunks_after_rerank": 0,
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


# ── Stage 1: Planner ──────────────────────────────────────────────────────────

@pytest.mark.timeout(120)
def test_stage_1_planner(stage_gate, prompt_question, openai_api_key):
    """Planner rewrites the user question for improved vector-search recall."""
    if not stage_gate(
        "Stage 1 — Planner",
        "The planner LLM will rewrite your question into a search-optimised query.",
    ):
        pytest.skip("Skipped at stage gate")

    result = planner_node(_blank_state(prompt_question))

    print(f"\n  Original question : {prompt_question}", flush=True)
    print(f"  Refined query     : {result['question']}", flush=True)
    print(f"  Tokens used       : {result['tokens_used']}", flush=True)

    assert result["question"], "Planner returned an empty refined query"
    assert result["tokens_used"] > 0, "Planner reported zero tokens"


# ── Stage 2: Retriever ────────────────────────────────────────────────────────

@pytest.mark.timeout(120)
def test_stage_2_retriever(stage_gate, prompt_question, patch_retriever, openai_api_key):
    """Retriever embeds the query and fetches relevant chunks from ChromaDB."""
    if not stage_gate(
        "Stage 2 — Retriever",
        "The retriever will search the seeded ChromaDB and display what was found.",
    ):
        pytest.skip("Skipped at stage gate")

    result = retriever_node(_blank_state(prompt_question))

    sources = result["sources"]
    ctx_preview = (result["retrieved_context"] or "")[:200].replace("\n", " ")
    print(f"\n  Sources   : {sources}", flush=True)
    print(f"  Context   : {ctx_preview}…", flush=True)

    assert result["retrieved_context"], "Retriever returned no context"
    assert sources, "Retriever returned no sources"


# ── Stage 3: Generator ────────────────────────────────────────────────────────

@pytest.mark.timeout(120)
def test_stage_3_generator(stage_gate, prompt_question, patch_retriever, openai_api_key):
    """Generator produces a grounded answer from the retrieved context."""
    if not stage_gate(
        "Stage 3 — Generator",
        "The generator LLM will produce an answer based solely on retrieved context.",
    ):
        pytest.skip("Skipped at stage gate")

    state = retriever_node(_blank_state(prompt_question))
    result = generator_node(state)

    print(f"\n  Question  : {prompt_question}", flush=True)
    print(f"  Answer    : {result['answer']}", flush=True)
    print(f"  Tokens    : {result['tokens_used']}", flush=True)

    assert result["answer"], "Generator produced an empty answer"
    assert result["tokens_used"] > 0, "Generator reported zero tokens"


# ── Stage 4: Validator ────────────────────────────────────────────────────────

@pytest.mark.timeout(120)
def test_stage_4_validator(stage_gate, prompt_question, patch_retriever, openai_api_key):
    """Validator quality-checks the generated answer against the retrieved context."""
    if not stage_gate(
        "Stage 4 — Validator",
        "The validator LLM will review the answer and return VALID or NEEDS_REVISION.",
    ):
        pytest.skip("Skipped at stage gate")

    state = retriever_node(_blank_state(prompt_question))
    state = generator_node(state)
    result = validator_node(state)

    print(f"\n  Answer     : {state['answer']}", flush=True)
    print(f"  Validation : {result['validation']}", flush=True)
    print(f"  Total tok  : {result['tokens_used']}", flush=True)

    assert result["validation"] in {"VALID", "NEEDS_REVISION"}, (
        f"Unexpected validation status: {result['validation']!r}"
    )


# ── Stage 5: Full pipeline ────────────────────────────────────────────────────

@pytest.mark.timeout(240)
def test_stage_5_full_pipeline(stage_gate, prompt_question, patch_retriever, openai_api_key):
    """
    Full end-to-end run through the compiled LangGraph:
    planner → retriever → generator → validator.
    """
    if not stage_gate(
        "Stage 5 — Full Pipeline",
        "Runs all 4 nodes in the compiled LangGraph with real LLM calls.",
    ):
        pytest.skip("Skipped at stage gate")

    result = run_agent(prompt_question)

    print(f"\n  Question   : {prompt_question}", flush=True)
    print(f"  Answer     : {result['answer']}", flush=True)
    print(f"  Sources    : {result['sources']}", flush=True)
    print(f"  Validation : {result['validation']}", flush=True)
    print(f"  Tokens     : {result['tokens_used']}", flush=True)

    assert result["answer"], "Pipeline produced no answer"
    assert result["tokens_used"] > 0, "Pipeline reported zero total tokens"
    assert result["validation"] in {"VALID", "NEEDS_REVISION"}, (
        f"Unexpected validation: {result['validation']!r}"
    )
    assert result["mode"] == "agentic", f"Expected 'agentic', got {result['mode']!r}"


# ── Stage 6: Simple RAG ───────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def patch_pipeline_retriever(_seeded_store):
    """Route similarity_search inside run_simple_rag to the ephemeral store."""
    with patch(
        "app.rag.pipeline.similarity_search",
        side_effect=lambda q, **kw: _seeded_store.similarity_search(q, k=kw.get("k", 4)),
    ):
        yield


@pytest.mark.timeout(120)
def test_stage_6_simple_rag(stage_gate, prompt_question, patch_pipeline_retriever, openai_api_key):
    """
    Simple RAG: single retrieve → generate pass.
    Bypasses the planner and validator; validation="N/A", mode="simple".
    """
    if not stage_gate(
        "Stage 6 — Simple RAG",
        "run_simple_rag() retrieves context and generates an answer in one pass (no planner or validator).",
    ):
        pytest.skip("Skipped at stage gate")

    result = run_simple_rag(prompt_question)

    print(f"\n  Question   : {prompt_question}", flush=True)
    print(f"  Answer     : {result['answer']}", flush=True)
    print(f"  Sources    : {result['sources']}", flush=True)
    print(f"  Validation : {result['validation']}", flush=True)
    print(f"  Mode       : {result['mode']}", flush=True)
    print(f"  Tokens     : {result['tokens_used']}", flush=True)

    assert result["answer"], "Simple RAG produced no answer"
    assert result["validation"] == "N/A", f"Expected 'N/A', got {result['validation']!r}"
    assert result["mode"] == "simple", f"Expected 'simple', got {result['mode']!r}"
    assert result["tokens_used"] > 0, "Simple RAG reported zero tokens"
