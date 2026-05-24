"""
Unit tests for app/api/ragas.py — _run_ragas_evaluation internal logic.

All heavy optional dependencies (ragas, datasets) and external I/O are mocked.
No real OpenAI calls, network traffic, or file-system writes are made.

OWASP coverage: tests ensure ValueError is raised before any LLM call is made
when the API key is missing (A07) or when no documents are indexed (A01).
"""
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from langchain_core.documents import Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_docs(n: int = 3) -> list[Document]:
    """Return *n* fake LangChain Documents for use in tests."""
    return [
        Document(
            page_content=f"Sample content for document {i}.",
            metadata={"source": f"doc{i}.txt"},
        )
        for i in range(n)
    ]


def _make_ragas_df() -> pd.DataFrame:
    """Return a minimal DataFrame matching the columns _run_ragas_evaluation reads."""
    return pd.DataFrame({
        "faithfulness": [0.90, 0.85, 0.88],
        "answer_relevancy": [0.80, 0.82, 0.84],
        "context_precision": [0.75, 0.78, 0.77],
        "context_recall": [0.70, 0.72, 0.71],
    })


def _inject_ragas_modules():
    """
    Insert lightweight stub modules for 'datasets' and 'ragas.*' into sys.modules
    so that the lazy imports inside _run_ragas_evaluation resolve without errors.

    Returns a tuple of (mock_Dataset, mock_evaluate, mock_faithfulness,
    mock_answer_relevancy, mock_context_precision, mock_context_recall).
    """
    # ── datasets ────────────────────────────────────────────────────────────
    mock_dataset_instance = MagicMock()
    mock_Dataset = MagicMock(return_value=mock_dataset_instance)
    mock_Dataset.from_dict = MagicMock(return_value=mock_dataset_instance)

    datasets_mod = types.ModuleType("datasets")
    datasets_mod.Dataset = mock_Dataset
    sys.modules["datasets"] = datasets_mod

    # ── ragas ────────────────────────────────────────────────────────────────
    fake_df = _make_ragas_df()
    mock_result = MagicMock()
    mock_result.to_pandas.return_value = fake_df
    mock_evaluate = MagicMock(return_value=mock_result)

    ragas_mod = types.ModuleType("ragas")
    ragas_mod.evaluate = mock_evaluate
    sys.modules["ragas"] = ragas_mod

    # ── ragas.metrics ────────────────────────────────────────────────────────
    mock_faithfulness = MagicMock(name="faithfulness")
    mock_answer_relevancy = MagicMock(name="answer_relevancy")
    mock_context_precision = MagicMock(name="context_precision")
    mock_context_recall = MagicMock(name="context_recall")

    ragas_metrics_mod = types.ModuleType("ragas.metrics")
    ragas_metrics_mod.faithfulness = mock_faithfulness
    ragas_metrics_mod.answer_relevancy = mock_answer_relevancy
    ragas_metrics_mod.context_precision = mock_context_precision
    ragas_metrics_mod.context_recall = mock_context_recall
    sys.modules["ragas.metrics"] = ragas_metrics_mod

    return (
        mock_Dataset,
        mock_evaluate,
        mock_faithfulness,
        mock_answer_relevancy,
        mock_context_precision,
        mock_context_recall,
    )


def _cleanup_ragas_modules():
    """Remove stub modules injected by _inject_ragas_modules."""
    for mod_name in ("datasets", "ragas", "ragas.metrics"):
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Test: missing / placeholder API key → ValueError
# ---------------------------------------------------------------------------

class TestRunRagasEvaluationApiKeyValidation:
    """_run_ragas_evaluation raises ValueError when the API key is absent."""

    def test_empty_string_api_key_raises_value_error(self):
        """An empty API key must raise ValueError before any LLM call."""
        with patch("app.runtime.settings_store.get_effective_api_key", return_value=""), \
             patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            from app.api.ragas import _run_ragas_evaluation
            with pytest.raises(ValueError, match="OPENAI_API_KEY is not configured"):
                _run_ragas_evaluation()

    def test_default_placeholder_your_prefix_raises_value_error(self):
        """Keys starting with 'your_' are rejected as placeholder values."""
        with patch("app.runtime.settings_store.get_effective_api_key", return_value="your_openai_key_here"):
            from app.api.ragas import _run_ragas_evaluation
            with pytest.raises(ValueError, match="OPENAI_API_KEY is not configured"):
                _run_ragas_evaluation()

    def test_sk_xxx_placeholder_raises_value_error(self):
        """Keys starting with 'sk-xxx' are rejected as placeholder values."""
        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-xxx-placeholder"):
            from app.api.ragas import _run_ragas_evaluation
            with pytest.raises(ValueError, match="OPENAI_API_KEY is not configured"):
                _run_ragas_evaluation()

    def test_none_api_key_raises_value_error(self):
        """None returned by get_effective_api_key is coerced to '' and rejected."""
        with patch("app.runtime.settings_store.get_effective_api_key", return_value=None), \
             patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            from app.api.ragas import _run_ragas_evaluation
            with pytest.raises(ValueError, match="OPENAI_API_KEY is not configured"):
                _run_ragas_evaluation()


# ---------------------------------------------------------------------------
# Test: no documents indexed → ValueError
# ---------------------------------------------------------------------------

class TestRunRagasEvaluationNoDocuments:
    """_run_ragas_evaluation raises ValueError when the vector store is empty."""

    def test_empty_document_list_raises_value_error(self):
        """An empty document list must raise ValueError with the 'No documents' message."""
        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=[]):
            from app.api.ragas import _run_ragas_evaluation
            with pytest.raises(ValueError, match="No documents indexed"):
                _run_ragas_evaluation()

    def test_error_raised_before_any_llm_import(self):
        """Heavy lazy imports must NOT be reached when there are no documents."""
        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=[]):
            # If ragas were imported it would fail because it's not installed;
            # this confirms the guard runs first.
            from app.api.ragas import _run_ragas_evaluation
            with pytest.raises(ValueError):
                _run_ragas_evaluation()


# ---------------------------------------------------------------------------
# Test: happy path — valid key + documents → returns score dict
# ---------------------------------------------------------------------------

class TestRunRagasEvaluationSuccess:
    """_run_ragas_evaluation returns the expected score dict on the happy path."""

    def setup_method(self):
        _inject_ragas_modules()

    def teardown_method(self):
        _cleanup_ragas_modules()

    def test_returns_dict_with_all_metric_keys(self):
        """Result must contain faithfulness, answer_relevancy, context_precision, context_recall."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(3)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}):

            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        assert "faithfulness" in result
        assert "answer_relevancy" in result
        assert "context_precision" in result
        assert "context_recall" in result

    def test_metric_values_are_floats(self):
        """Each metric value in the result dict must be a Python float."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(3)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}):

            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        for key in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            assert isinstance(result[key], float), f"{key} must be a float"

    def test_model_name_comes_from_settings(self):
        """The 'model' key in the result must match the value from get_settings()."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(3)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}):

            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        assert result["model"] == "gpt-4o-mini"

    def test_num_samples_capped_at_five(self):
        """num_samples must not exceed 5 regardless of how many documents exist."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(10)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}):

            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        assert result["num_samples"] <= 5

    def test_num_samples_equals_document_count_when_fewer_than_five(self):
        """When fewer than 5 documents exist, num_samples equals the document count."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(2)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}):

            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        assert result["num_samples"] == 2

    def test_run_simple_rag_called_for_each_sample(self):
        """run_simple_rag must be called once per sampled document."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(3)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}) as mock_rag:

            from app.api.ragas import _run_ragas_evaluation
            _run_ragas_evaluation()

        assert mock_rag.call_count == 3

    def test_run_simple_rag_exception_falls_back_to_placeholder(self):
        """When run_simple_rag raises, the answer falls back to the placeholder string."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(1)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", side_effect=RuntimeError("LLM unavailable")):

            # Should not raise — exception is caught inside the function
            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        # The evaluation must still complete (evaluate() was called on fallback answers)
        assert "faithfulness" in result

    def test_metric_scores_match_dataframe_means(self):
        """Each metric score must equal the mean of the corresponding DataFrame column."""
        mock_settings = MagicMock()
        mock_settings.llm_model = "gpt-4o-mini"

        with patch("app.runtime.settings_store.get_effective_api_key", return_value="sk-real-key-abc123"), \
             patch("app.rag.vector_store.get_all_documents", return_value=_make_fake_docs(3)), \
             patch("app.config.get_settings", return_value=mock_settings), \
             patch("app.rag.pipeline.run_simple_rag", return_value={"answer": "Test answer"}):

            from app.api.ragas import _run_ragas_evaluation
            result = _run_ragas_evaluation()

        expected_df = _make_ragas_df()
        assert result["faithfulness"] == pytest.approx(expected_df["faithfulness"].mean(), abs=1e-6)
        assert result["answer_relevancy"] == pytest.approx(expected_df["answer_relevancy"].mean(), abs=1e-6)
        assert result["context_precision"] == pytest.approx(expected_df["context_precision"].mean(), abs=1e-6)
        assert result["context_recall"] == pytest.approx(expected_df["context_recall"].mean(), abs=1e-6)


# ---------------------------------------------------------------------------
# Test: trigger_evaluation endpoint — line 140 fallback (get_ragas_scores → None)
# ---------------------------------------------------------------------------

class TestTriggerEvaluationFallback:
    """
    When get_ragas_scores() returns None after a successful evaluation,
    trigger_evaluation must still return the scores dict from _run_ragas_evaluation.
    """

    def test_returns_scores_from_dict_when_get_ragas_scores_returns_none(self, monkeypatch):
        """Line 140: fallback branch — scores returned directly from the dict."""
        fake_scores = {
            "faithfulness": 0.91,
            "answer_relevancy": 0.87,
            "context_precision": 0.76,
            "context_recall": 0.65,
            "model": "gpt-4o-mini",
            "num_samples": 3,
        }

        monkeypatch.setattr("app.api.ragas._run_ragas_evaluation", MagicMock(return_value=fake_scores))
        monkeypatch.setattr("app.api.ragas.save_ragas_scores", MagicMock())
        monkeypatch.setattr("app.api.ragas.get_ragas_scores", lambda: None)

        import asyncio

        from app.api.ragas import trigger_evaluation

        # trigger_evaluation is async; call it with a mock admin user
        mock_user = MagicMock()

        async def _run():
            return await trigger_evaluation(_user=mock_user)

        result = asyncio.run(_run())

        assert result.has_results is True
        assert result.faithfulness == pytest.approx(0.91)
        assert result.answer_relevancy == pytest.approx(0.87)
        assert result.context_precision == pytest.approx(0.76)
        assert result.context_recall == pytest.approx(0.65)
        assert result.model == "gpt-4o-mini"
        assert result.num_samples == 3

    def test_returns_scores_from_store_when_available(self, monkeypatch):
        """When get_ragas_scores() returns data, the stored values (with timestamp) are used."""
        fake_scores = {
            "faithfulness": 0.91,
            "answer_relevancy": 0.87,
            "context_precision": 0.76,
            "context_recall": 0.65,
            "model": "gpt-4o-mini",
            "num_samples": 3,
        }
        saved_with_ts = {**fake_scores, "evaluated_at": "2026-01-01T00:00:00+00:00"}

        monkeypatch.setattr("app.api.ragas._run_ragas_evaluation", MagicMock(return_value=fake_scores))
        monkeypatch.setattr("app.api.ragas.save_ragas_scores", MagicMock())
        monkeypatch.setattr("app.api.ragas.get_ragas_scores", lambda: saved_with_ts)

        import asyncio

        from app.api.ragas import trigger_evaluation

        mock_user = MagicMock()

        async def _run():
            return await trigger_evaluation(_user=mock_user)

        result = asyncio.run(_run())

        assert result.has_results is True
        assert result.evaluated_at == "2026-01-01T00:00:00+00:00"
