"""
Ragas evaluation API.

POST /api/ragas/evaluate  — trigger in-process evaluation (admin only, OWASP A01)

Results are persisted to disk via app.ragas_store (path: RAGAS_SCORES_FILE env var,
default /tmp/ragas_scores.json) so they survive server restarts.

Accepted risk: POST makes real OpenAI calls and can take 30-60 s.
It is protected by require_full_access and wrapped in asyncio.to_thread.

GET /api/ragas/scores was removed — the canonical read endpoint is
GET /api/settings/ragas-scores (admin only, returns 200 with has_results=False
when no evaluation has been run yet).
"""
import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.utils import require_full_access
from app.ragas_store import get_ragas_scores, save_ragas_scores

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

    from app.settings_store import get_effective_api_key
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
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
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

    Returns HTTP 503 if OPENAI_API_KEY is not configured or no documents are indexed.
    OWASP A01 — restricted to full-access (admin) users.
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
