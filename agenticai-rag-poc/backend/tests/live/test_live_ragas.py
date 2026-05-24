"""
Ragas evaluation of the Agentic RAG pipeline.

Measures four retrieval-augmented generation quality metrics:
  - Faithfulness:      Is the answer grounded in the retrieved context?
  - Answer relevance:  Does the answer address the question?
  - Context precision: Are retrieved chunks on-topic?
  - Context recall:    Did retrieval surface the information needed? (requires ground truth)

Run:
    LIVE_TESTS=1 OPENAI_API_KEY=<your-openai-api-key> pytest tests/live/test_live_ragas.py -v

Prerequisites:
  - At least one document must be indexed in the vector store before running.
  - A real OPENAI_API_KEY (not sk-test*) must be exported.
  - A running backend is NOT required; this file calls pipeline functions directly.
  - Costs approximately 100–500 OpenAI tokens per evaluation run.

Telemetry note:
  RAGAS_DO_NOT_TRACK=true is set unconditionally below.  Ragas 0.2.x posts
  analytics to t.explodinggradients.com on every evaluate() call; that external
  domain caused intermittent DNS/connection failures in CI.  Disabling telemetry
  eliminates those spurious failures without affecting metric quality.
"""
import os

# Disable Ragas telemetry before any ragas import.
# Ragas posts analytics to t.explodinggradients.com; that outbound call is the
# source of "domain URL" intermittent failures observed in CI.
os.environ["RAGAS_DO_NOT_TRACK"] = "true"

import pytest

# Skip entire module unless LIVE_TESTS=1
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_TESTS", "0") != "1",
    reason="Set LIVE_TESTS=1 to run Ragas evaluation"
)


# ---------------------------------------------------------------------------
# Sample evaluation dataset
# ---------------------------------------------------------------------------
# Each sample has: question, ground_truth (ideal answer for recall metric),
# and expected_source (to verify retrieval). The ground_truth values here
# are intentionally generic — replace with domain-specific values once you
# have real documents indexed.
_EVAL_SAMPLES = [
    {
        "question": "What is Retrieval-Augmented Generation and how does it work?",
        "ground_truth": (
            "RAG is an AI framework that retrieves relevant document chunks from a vector "
            "database using semantic similarity search, then feeds those chunks as context "
            "to an LLM to generate accurate, grounded answers."
        ),
    },
    {
        "question": "What are the key benefits of RAG systems?",
        "ground_truth": (
            "RAG reduces hallucination, provides access to up-to-date information, "
            "and improves factual accuracy by grounding LLM responses in retrieved context."
        ),
    },
    {
        "question": "What framework is used for agentic AI workflows with nodes and edges?",
        "ground_truth": (
            "LangGraph enables agentic workflows using a StateGraph with nodes such as "
            "planner, retriever, grader, generator, and validator, connected by edges "
            "representing control flow."
        ),
    },
]

# Retry parameters for transient LLM / network errors in the pipeline.
_MAX_PIPELINE_RETRIES = 3
_PIPELINE_RETRY_DELAY_S = 5

# ---------------------------------------------------------------------------
# Test document seeded into the vector store for ragas evaluation
# ---------------------------------------------------------------------------
_RAGAS_TEST_SOURCE = "_ragas_eval_test.txt"
_RAGAS_TEST_CONTENT = """\
Retrieval-Augmented Generation (RAG) is an AI framework that enhances large language models \
by grounding their responses in retrieved external knowledge from a vector database.

RAG operates in two phases. The retrieval phase fetches relevant document chunks using \
semantic similarity search via embeddings. The generation phase feeds those chunks as context \
to the language model, producing accurate, grounded answers. Key benefits include reduced \
hallucination, access to up-to-date information, and improved factual accuracy.

Agentic AI extends language models with planning, tool use, and multi-step task execution. \
LangGraph is a framework that enables complex agentic workflows using a StateGraph to define \
nodes (planner, retriever, grader, generator, validator) and edges representing control flow.

Large Language Models (LLMs) are transformer-based neural networks trained on vast text corpora. \
Capabilities include text generation, summarisation, question answering, and code generation. \
Popular providers include OpenAI (GPT-4o), Anthropic (Claude), and Google (Gemini).\
"""


def _run_pipeline_for_sample(question: str) -> dict:
    """Run the agentic RAG pipeline and collect context + answer.

    Retries up to _MAX_PIPELINE_RETRIES times on transient errors so that
    a single rate-limit or connection hiccup does not fail the whole suite.
    """
    import time
    from app.rag.vector_store import similarity_search
    from app.agents.rag_agent import run_agent

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_PIPELINE_RETRIES + 1):
        try:
            docs = similarity_search(question)
            contexts = [doc.page_content for doc in docs] if docs else ["No documents found."]
            result = run_agent(question)
            return {
                "question": question,
                "answer": result["answer"],
                "contexts": contexts,
                "ground_truth": None,  # filled in by caller
            }
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_PIPELINE_RETRIES:
                time.sleep(_PIPELINE_RETRY_DELAY_S * attempt)

    raise RuntimeError(
        f"Pipeline failed for question {question!r} after {_MAX_PIPELINE_RETRIES} attempts"
    ) from last_exc


@pytest.fixture(scope="module", autouse=True)
def _ragas_indexed_doc():
    """Index a test document into the vector store; delete it after module tests finish."""
    from langchain_core.documents import Document
    from app.rag.vector_store import add_documents, delete_document

    doc = Document(
        page_content=_RAGAS_TEST_CONTENT,
        metadata={"source": _RAGAS_TEST_SOURCE, "chunk": 0},
    )
    try:
        add_documents([doc])
    except Exception as exc:
        module = type(exc).__module__.lower()
        name = type(exc).__name__.lower()
        if "chromadb" in module or "chroma" in module or "internalerror" in name or "compaction" in str(exc).lower():
            pytest.skip(
                f"ChromaDB unavailable or corrupted ({type(exc).__name__}): {exc}\n"
                "  To reset: rm -rf backend/chroma_db  then re-run the backend."
            )
        raise
    yield
    try:
        delete_document(_RAGAS_TEST_SOURCE)
    except Exception:
        pass


@pytest.fixture(scope="module")
def ragas_dataset(_ragas_indexed_doc):
    """Build a Ragas EvaluationDataset from the sample questions."""
    try:
        from ragas import EvaluationDataset, SingleTurnSample
    except ImportError:
        pytest.skip("ragas not installed — run: pip install ragas")

    samples = []
    for item in _EVAL_SAMPLES:
        pipeline_out = _run_pipeline_for_sample(item["question"])
        sample = SingleTurnSample(
            user_input=item["question"],
            response=pipeline_out["answer"],
            retrieved_contexts=pipeline_out["contexts"],
            reference=item["ground_truth"],
        )
        samples.append(sample)
    return EvaluationDataset(samples=samples)


@pytest.fixture(scope="module")
def ragas_results(ragas_dataset):
    """Run Ragas evaluation once per module; return dict of mean float scores.

    ragas 0.2.x may return per-sample lists or scalars depending on the metric
    and whether raise_exceptions=False triggered partial failures.  This fixture
    always normalises to {metric: mean_float | None} so individual tests never
    hit 'TypeError: > not supported between list and float'.
    """
    import math

    try:
        from ragas import evaluate
        from ragas.metrics._faithfulness import faithfulness
        from ragas.metrics._answer_relevance import answer_relevancy
        from ragas.metrics._context_precision import context_precision
        from ragas.metrics._context_recall import context_recall
        from ragas.run_config import RunConfig
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    except ImportError:
        pytest.skip("ragas or langchain_openai not installed")

    from app.runtime.settings_store import get_effective_api_key, get_effective_model
    api_key = get_effective_api_key()

    llm = ChatOpenAI(model=get_effective_model(), openai_api_key=api_key)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=api_key)

    run_config = RunConfig(timeout=120, max_retries=3, log_tenacity=False)

    raw = evaluate(
        dataset=ragas_dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
        raise_exceptions=False,
        show_progress=True,
    )

    def _mean(key: str) -> float | None:
        """Extract mean score; handles scalar, list, Series, ndarray, and None."""
        try:
            val = raw[key]
        except (KeyError, TypeError, AttributeError):
            return None
        if val is None:
            return None
        if isinstance(val, (int, float)):
            f = float(val)
            return None if math.isnan(f) else f
        # Iterable (per-sample list / pandas Series / numpy array)
        try:
            nums = [float(v) for v in val if v is not None and not math.isnan(float(v))]
            return sum(nums) / len(nums) if nums else None
        except (TypeError, ValueError, AttributeError):
            return None

    return {
        "faithfulness": _mean("faithfulness"),
        "answer_relevancy": _mean("answer_relevancy"),
        "context_precision": _mean("context_precision"),
        "context_recall": _mean("context_recall"),
        "_raw": raw,  # kept for the logging test
    }


class TestRagasMetrics:
    """Ragas quality gate — thresholds are intentionally lenient for CI."""

    def test_faithfulness_above_threshold(self, ragas_results):
        """Faithfulness >= 0.5: answers must be mostly grounded in context."""
        score = ragas_results["faithfulness"]
        assert score is not None, "Faithfulness metric returned None — all samples failed evaluation"
        assert score >= 0.5, f"Faithfulness {score:.2f} is below 0.5 threshold"

    def test_answer_relevancy_above_threshold(self, ragas_results):
        """Answer relevancy >= 0.5: answers must address the question."""
        score = ragas_results["answer_relevancy"]
        assert score is not None, "Answer relevancy metric returned None — all samples failed evaluation"
        assert score >= 0.5, f"Answer relevancy {score:.2f} is below 0.5 threshold"

    def test_context_precision_above_threshold(self, ragas_results):
        """Context precision >= 0.3: at least some retrieved chunks are on-topic."""
        score = ragas_results["context_precision"]
        assert score is not None, "Context precision metric returned None — all samples failed evaluation"
        assert score >= 0.3, f"Context precision {score:.2f} is below 0.3 threshold"

    def test_context_recall_above_threshold(self, ragas_results):
        """Context recall >= 0.3: retrieval surfaces enough relevant information."""
        score = ragas_results["context_recall"]
        assert score is not None, "Context recall metric returned None — all samples failed evaluation"
        assert score >= 0.3, f"Context recall {score:.2f} is below 0.3 threshold"

    def test_ragas_scores_logged(self, ragas_results, capsys):
        """Print the full score report and persist scores to ragas_store."""
        _metrics = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
        print("\n── Ragas Evaluation Results ─────────────────")
        for metric in _metrics:
            score = ragas_results[metric]
            label = f"{score:.3f}" if isinstance(score, float) else "N/A"
            print(f"  {metric:<25} {label}")
        print("─────────────────────────────────────────────")

        # Persist scores so the admin dashboard can display them
        from app.runtime.ragas_store import save_ragas_scores
        from app.runtime.settings_store import get_effective_model

        save_ragas_scores(
            faithfulness=ragas_results["faithfulness"] or 0.0,
            answer_relevancy=ragas_results["answer_relevancy"] or 0.0,
            context_precision=ragas_results["context_precision"] or 0.0,
            context_recall=ragas_results["context_recall"] or 0.0,
            model=get_effective_model(),
            num_samples=len(_EVAL_SAMPLES),
        )
