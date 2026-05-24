"""
Ragas evaluation API.

POST /api/ragas/evaluate  — trigger in-process evaluation (admin only)

Results are persisted to disk via app.ragas_store (path: RAGAS_SCORES_FILE env var,
default /tmp/ragas_scores.json) so they survive server restarts.

OWASP A01: evaluation is restricted to admin users (require_full_access).
Guests can view scores via GET /api/settings/ragas-scores but cannot trigger
a new evaluation.  Each run samples up to 5 indexed chunks and makes real
OpenAI calls (30-60 s).  Concurrent runs are blocked with HTTP 429.

GET /api/ragas/scores was removed — the canonical read endpoint is
GET /api/settings/ragas-scores (returns 200 with has_results=False when no
evaluation has been run yet).
"""
import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.utils import require_full_access
from app.runtime.ragas_store import get_ragas_scores, save_ragas_scores

log = structlog.get_logger()
router = APIRouter()


class _EvaluateResponse(BaseModel):
    """Response model for POST /evaluate — mirrors settings.RagasScoresResponse."""

    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    evaluated_at: str | None = None
    model: str | None = None
    num_samples: int = 0
    has_results: bool = False


def _run_ragas_evaluation() -> dict:
    """Synchronous Ragas evaluation — called via asyncio.to_thread to avoid blocking."""
    import os

    from app.runtime.settings_store import get_effective_api_key
    api_key = get_effective_api_key() or os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your_") or api_key.startswith("sk-xxx"):
        raise ValueError("OPENAI_API_KEY is not configured. Set it in Settings before running evaluation.")

    from app.rag.vector_store import get_all_documents
    docs = get_all_documents()
    if not docs:
        raise ValueError("No documents indexed — upload documents before running Ragas evaluation.")

    from app.config import get_settings
    model_name = get_settings().llm_model

    # Lazy imports — heavy optional dependencies
    # ragas/llms/base.py imports from langchain_community.chat_models.vertexai at module
    # level, but langchain-community 0.3+ removed that sub-module. Stub it with the
    # standalone langchain-google-vertexai package before ragas is imported.
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

    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics._faithfulness import faithfulness
    from ragas.metrics._answer_relevance import answer_relevancy
    from ragas.metrics._context_precision import context_precision
    from ragas.metrics._context_recall import context_recall
    from app.rag.pipeline import run_simple_rag

    sample_size = min(5, len(docs))
    samples = docs[:sample_size]

    questions = [
        f"What does this document say about {doc.metadata.get('source', 'the topic')}?"
        for doc in samples
    ]
    contexts = [[doc.page_content] for doc in samples]
    ground_truths = [doc.page_content[:200] for doc in samples]

    answers = []
    for q in questions:
        try:
            res = run_simple_rag(q)
            answers.append(res.get("answer", "No answer generated."))
        except Exception:
            answers.append("Unable to generate answer.")

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    df = result.to_pandas()

    return {
        "faithfulness": float(df["faithfulness"].mean()) if "faithfulness" in df.columns else 0.0,
        "answer_relevancy": float(df["answer_relevancy"].mean()) if "answer_relevancy" in df.columns else 0.0,
        "context_precision": float(df["context_precision"].mean()) if "context_precision" in df.columns else 0.0,
        "context_recall": float(df["context_recall"].mean()) if "context_recall" in df.columns else 0.0,
        "model": model_name,
        "num_samples": sample_size,
    }


@router.post("/evaluate", response_model=_EvaluateResponse)
async def trigger_evaluation(_user=Depends(require_full_access)):
    """
    Run Ragas evaluation against indexed documents (admin only).

    Builds a synthetic dataset from up to 5 indexed chunks, runs the 4 standard
    Ragas metrics, persists results, and returns them immediately.

    Returns HTTP 401/403 for guests, HTTP 503 if OPENAI_API_KEY is not configured
    or no documents are indexed. Concurrent runs are blocked with HTTP 429.
    """
    try:
        scores = await asyncio.to_thread(_run_ragas_evaluation)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.error("ragas_evaluation_failed", error_type=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ragas evaluation failed. Check server logs for details.",
        ) from exc

    save_ragas_scores(**scores)
    log.info("ragas_evaluation_complete", num_samples=scores["num_samples"])
    # Read back from store to include evaluated_at timestamp set by save_ragas_scores
    saved = get_ragas_scores()
    if saved:
        return _EvaluateResponse(**saved, has_results=True)
    return _EvaluateResponse(**scores, has_results=True)
