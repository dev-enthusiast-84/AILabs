"""Integration tests for POST /api/ragas/evaluate.

GET /api/ragas/scores was removed (dead code). The canonical read endpoint is
GET /api/settings/ragas-scores — tested in test_api_settings.py.
"""
import unittest.mock as mock

import pytest


# ── POST /api/ragas/evaluate ─────────────────────────────────────────────────

def test_evaluate_guest_returns_503_when_no_api_key(client, guest_headers, monkeypatch):
    """Guest tokens can trigger evaluation; 503 is returned when no API key is configured."""
    monkeypatch.setattr(
        "app.api.ragas._run_ragas_evaluation",
        mock.Mock(side_effect=ValueError("OPENAI_API_KEY is not configured.")),
    )
    resp = client.post("/api/ragas/evaluate", headers=guest_headers)
    assert resp.status_code == 503


def test_evaluate_returns_503_when_no_api_key(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.ragas._run_ragas_evaluation",
        mock.Mock(side_effect=ValueError("OPENAI_API_KEY is not configured.")),
    )
    resp = client.post("/api/ragas/evaluate", headers=auth_headers)
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_evaluate_returns_503_when_no_documents(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.ragas._run_ragas_evaluation",
        mock.Mock(side_effect=ValueError("No documents indexed")),
    )
    resp = client.post("/api/ragas/evaluate", headers=auth_headers)
    assert resp.status_code == 503


def test_evaluate_returns_500_on_unexpected_error(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.ragas._run_ragas_evaluation",
        mock.Mock(side_effect=RuntimeError("unexpected")),
    )
    resp = client.post("/api/ragas/evaluate", headers=auth_headers)
    assert resp.status_code == 500


def test_evaluate_success_saves_and_returns_scores(client, auth_headers, monkeypatch):
    fake_result = {
        "faithfulness": 0.92,
        "answer_relevancy": 0.88,
        "context_precision": 0.84,
        "context_recall": 0.79,
        "model": "gpt-4o-mini",
        "num_samples": 3,
    }
    saved = {}

    def fake_save(**kwargs):
        saved.update(kwargs)

    fake_scores_with_ts = {**fake_result, "evaluated_at": "2026-01-01T00:00:00+00:00"}

    monkeypatch.setattr("app.api.ragas._run_ragas_evaluation", mock.Mock(return_value=fake_result))
    monkeypatch.setattr("app.api.ragas.save_ragas_scores", fake_save)
    monkeypatch.setattr("app.api.ragas.get_ragas_scores", lambda: fake_scores_with_ts)

    resp = client.post("/api/ragas/evaluate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_results"] is True
    assert body["faithfulness"] == pytest.approx(0.92)
    assert saved["faithfulness"] == pytest.approx(0.92)
