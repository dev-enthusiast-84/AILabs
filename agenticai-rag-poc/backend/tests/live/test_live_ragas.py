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
"""
import os
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
        "question": "What is the main topic covered in the uploaded documents?",
        "ground_truth": "The documents cover the topic specified during sample data generation.",
    },
    {
        "question": "Summarise the key points from the documents.",
        "ground_truth": "A summary of key concepts from the uploaded sample documents.",
    },
    {
        "question": "What specific details are mentioned about the subject matter?",
        "ground_truth": "Specific details and facts from the uploaded documents.",
    },
]


def _run_pipeline_for_sample(question: str) -> dict:
    """Run the simple RAG pipeline and collect context + answer."""
    from app.rag.vector_store import similarity_search
    from app.agents.rag_agent import run_agent

    docs = similarity_search(question)
    contexts = [doc.page_content for doc in docs] if docs else ["No documents found."]

    result = run_agent(question)
    return {
        "question": question,
        "answer": result["answer"],
        "contexts": contexts,
        "ground_truth": None,  # filled in by caller
    }


@pytest.fixture(scope="module")
def ragas_dataset():
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
    """Run Ragas evaluation once per module; share results across tests."""
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    except ImportError:
        pytest.skip("ragas or langchain_openai not installed")

    from app.settings_store import get_effective_api_key, get_effective_model
    api_key = get_effective_api_key()

    llm = ChatOpenAI(model=get_effective_model(), openai_api_key=api_key)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=api_key)

    results = evaluate(
        dataset=ragas_dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=embeddings,
    )
    return results


class TestRagasMetrics:
    """Ragas quality gate — thresholds are intentionally lenient for CI."""

    def test_faithfulness_above_threshold(self, ragas_results):
        """Faithfulness >= 0.5: answers must be mostly grounded in context."""
        score = ragas_results["faithfulness"]
        assert score >= 0.5, f"Faithfulness {score:.2f} is below 0.5 threshold"

    def test_answer_relevancy_above_threshold(self, ragas_results):
        """Answer relevancy >= 0.5: answers must address the question."""
        score = ragas_results["answer_relevancy"]
        assert score >= 0.5, f"Answer relevancy {score:.2f} is below 0.5 threshold"

    def test_context_precision_above_threshold(self, ragas_results):
        """Context precision >= 0.3: at least some retrieved chunks are on-topic."""
        score = ragas_results["context_precision"]
        assert score >= 0.3, f"Context precision {score:.2f} is below 0.3 threshold"

    def test_context_recall_above_threshold(self, ragas_results):
        """Context recall >= 0.3: retrieval surfaces enough relevant information."""
        score = ragas_results["context_recall"]
        assert score >= 0.3, f"Context recall {score:.2f} is below 0.3 threshold"

    def test_ragas_scores_logged(self, ragas_results, capsys):
        """Print the full score report and persist scores to ragas_store."""
        print("\n── Ragas Evaluation Results ─────────────────")
        for metric, score in ragas_results.items():
            if isinstance(score, float):
                print(f"  {metric:<25} {score:.3f}")
        print("─────────────────────────────────────────────")

        # Persist scores so the admin dashboard can display them
        from app.ragas_store import save_ragas_scores
        from app.settings_store import get_effective_model
        save_ragas_scores(
            faithfulness=float(ragas_results["faithfulness"]),
            answer_relevancy=float(ragas_results["answer_relevancy"]),
            context_precision=float(ragas_results["context_precision"]),
            context_recall=float(ragas_results["context_recall"]),
            model=get_effective_model(),
            num_samples=len(_EVAL_SAMPLES),
        )
