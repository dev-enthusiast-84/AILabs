"""Unit tests for app.ragas_store — get_ragas_scores and save_ragas_scores."""
import json
import pytest


# ---------------------------------------------------------------------------
# get_ragas_scores — None / missing-file cases
# ---------------------------------------------------------------------------

def test_get_returns_none_when_file_missing(tmp_path, monkeypatch):
    """Returns None when the scores file does not exist."""
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(tmp_path / "ragas_scores.json"))
    from app.runtime.ragas_store import get_ragas_scores
    assert get_ragas_scores() is None


def test_get_returns_none_on_bad_json(tmp_path, monkeypatch):
    """Returns None when the file contains malformed JSON."""
    path = tmp_path / "ragas_scores.json"
    path.write_text("not-json{{{")
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import get_ragas_scores
    assert get_ragas_scores() is None


def test_get_returns_none_when_required_key_missing(tmp_path, monkeypatch):
    """Returns None when a required score key is absent from the file."""
    path = tmp_path / "ragas_scores.json"
    # Missing context_recall
    path.write_text(json.dumps({
        "faithfulness": 0.9,
        "answer_relevancy": 0.85,
        "context_precision": 0.8,
        "evaluated_at": "2024-01-01T00:00:00+00:00",
        "model": "gpt-4o-mini",
        "num_samples": 3,
    }))
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import get_ragas_scores
    assert get_ragas_scores() is None


def test_get_returns_none_when_all_required_keys_missing(tmp_path, monkeypatch):
    """Returns None when the file is valid JSON but has none of the required keys."""
    path = tmp_path / "ragas_scores.json"
    path.write_text(json.dumps({"foo": "bar"}))
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import get_ragas_scores
    assert get_ragas_scores() is None


# ---------------------------------------------------------------------------
# save_ragas_scores — file creation and content
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_path, monkeypatch):
    """save_ragas_scores creates the scores file if it does not exist."""
    path = tmp_path / "ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import save_ragas_scores
    save_ragas_scores(
        faithfulness=0.9,
        answer_relevancy=0.85,
        context_precision=0.8,
        context_recall=0.75,
        model="gpt-4o-mini",
        num_samples=3,
    )
    assert path.exists()


def test_save_file_has_correct_content(tmp_path, monkeypatch):
    """Saved file contains the expected score keys and values."""
    path = tmp_path / "ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import save_ragas_scores
    save_ragas_scores(
        faithfulness=0.9,
        answer_relevancy=0.85,
        context_precision=0.8,
        context_recall=0.75,
        model="gpt-4o-mini",
        num_samples=3,
    )
    data = json.loads(path.read_text())
    assert data["faithfulness"] == pytest.approx(0.9, abs=1e-5)
    assert data["answer_relevancy"] == pytest.approx(0.85, abs=1e-5)
    assert data["context_precision"] == pytest.approx(0.8, abs=1e-5)
    assert data["context_recall"] == pytest.approx(0.75, abs=1e-5)
    assert data["model"] == "gpt-4o-mini"
    assert data["num_samples"] == 3
    assert "evaluated_at" in data


# ---------------------------------------------------------------------------
# Round-trip: save then get
# ---------------------------------------------------------------------------

def test_save_then_get_roundtrip(tmp_path, monkeypatch):
    """save_ragas_scores then get_ragas_scores returns consistent values."""
    path = tmp_path / "ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import save_ragas_scores, get_ragas_scores
    save_ragas_scores(
        faithfulness=0.91,
        answer_relevancy=0.87,
        context_precision=0.76,
        context_recall=0.65,
        model="gpt-4o",
        num_samples=5,
    )
    scores = get_ragas_scores()
    assert scores is not None
    assert scores["faithfulness"] == pytest.approx(0.91, abs=1e-5)
    assert scores["answer_relevancy"] == pytest.approx(0.87, abs=1e-5)
    assert scores["context_precision"] == pytest.approx(0.76, abs=1e-5)
    assert scores["context_recall"] == pytest.approx(0.65, abs=1e-5)
    assert scores["model"] == "gpt-4o"
    assert scores["num_samples"] == 5


# ---------------------------------------------------------------------------
# Rounding to 4 decimal places
# ---------------------------------------------------------------------------

def test_scores_are_rounded_to_4_decimal_places(tmp_path, monkeypatch):
    """save_ragas_scores rounds each metric to 4 decimal places."""
    path = tmp_path / "ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import save_ragas_scores
    save_ragas_scores(
        faithfulness=0.912345678,
        answer_relevancy=0.876543210,
        context_precision=0.765432109,
        context_recall=0.654321098,
        model="gpt-4o-mini",
        num_samples=2,
    )
    data = json.loads(path.read_text())
    assert data["faithfulness"] == round(0.912345678, 4)
    assert data["answer_relevancy"] == round(0.876543210, 4)
    assert data["context_precision"] == round(0.765432109, 4)
    assert data["context_recall"] == round(0.654321098, 4)


# ---------------------------------------------------------------------------
# evaluated_at is ISO-8601 UTC
# ---------------------------------------------------------------------------

def test_evaluated_at_is_iso8601_utc(tmp_path, monkeypatch):
    """evaluated_at field is a valid ISO-8601 UTC timestamp."""
    from datetime import datetime, timezone
    path = tmp_path / "ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(path))
    from app.runtime.ragas_store import save_ragas_scores
    save_ragas_scores(
        faithfulness=0.9,
        answer_relevancy=0.85,
        context_precision=0.8,
        context_recall=0.75,
        model="gpt-4o-mini",
        num_samples=3,
    )
    data = json.loads(path.read_text())
    evaluated_at = data["evaluated_at"]
    # Must be parseable as an ISO-8601 datetime
    parsed = datetime.fromisoformat(evaluated_at)
    # Must be UTC (either +00:00 or Z suffix after Python 3.11)
    assert parsed.tzinfo is not None
    # UTC offset must be zero
    assert parsed.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# Creates parent directories if needed
# ---------------------------------------------------------------------------

def test_save_creates_parent_directories(tmp_path, monkeypatch):
    """save_ragas_scores creates missing parent directories."""
    nested_path = tmp_path / "nested" / "deeply" / "ragas_scores.json"
    monkeypatch.setenv("RAGAS_SCORES_FILE", str(nested_path))
    from app.runtime.ragas_store import save_ragas_scores
    save_ragas_scores(
        faithfulness=0.9,
        answer_relevancy=0.85,
        context_precision=0.8,
        context_recall=0.75,
        model="gpt-4o-mini",
        num_samples=3,
    )
    assert nested_path.exists()
