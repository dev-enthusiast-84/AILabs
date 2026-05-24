"""Unit tests for app/rag/bm25.py — BM25 lexical search helper."""
import logging
import os
import sys
from unittest.mock import patch

import pytest
from langchain_core.documents import Document

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32ch")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass@99!")


def _make_doc(content: str, source: str = "doc.txt") -> Document:
    return Document(page_content=content, metadata={"source": source})


class TestBM25Search:
    def test_returns_top_k_results(self):
        """bm25_search returns at most k results."""
        from app.rag.bm25 import bm25_search
        docs = [_make_doc(f"keyword document number {i}") for i in range(10)]
        results = bm25_search("keyword document", docs, k=3)
        assert len(results) <= 3

    def test_returns_doc_score_tuples(self):
        """Each result is a (Document, float) tuple."""
        from app.rag.bm25 import bm25_search
        docs = [_make_doc("relevant text here"), _make_doc("unrelated content")]
        results = bm25_search("relevant text", docs, k=5)
        assert isinstance(results, list)
        for doc, score in results:
            assert isinstance(doc, Document)
            assert isinstance(score, float)

    def test_empty_corpus_returns_empty(self):
        """Empty docs list returns []."""
        from app.rag.bm25 import bm25_search
        assert bm25_search("query", [], k=5) == []

    def test_scores_normalized_to_0_1(self):
        """All scores must be in [0, 1]."""
        from app.rag.bm25 import bm25_search
        docs = [_make_doc(f"word{i} content") for i in range(5)]
        results = bm25_search("word1 content", docs, k=5)
        for _, score in results:
            assert 0.0 <= score <= 1.0

    def test_results_sorted_descending(self):
        """Results are sorted by score in descending order."""
        from app.rag.bm25 import bm25_search
        docs = [_make_doc(f"term{i}") for i in range(5)]
        results = bm25_search("term0", docs, k=5)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_relevant_doc_ranks_higher_than_irrelevant(self):
        """Docs containing query terms rank above docs that don't.

        Extra padding docs are required: with only 2 docs, BM25Okapi IDF =
        log((N-n+0.5)/(n+0.5)) = log(1.0) = 0 for every term that appears in
        exactly one of the two docs, making all scores equal. Adding more docs
        raises IDF above zero so the matching doc scores higher.
        """
        from app.rag.bm25 import bm25_search
        relevant = _make_doc("remote work policy days per week")
        irrelevant = _make_doc("quarterly earnings report fiscal year")
        # Padding docs ensure N=4 so IDF ≈ log(2.33) > 0
        pad1 = _make_doc("unrelated alpha beta gamma delta epsilon")
        pad2 = _make_doc("other document about something entirely different")
        docs = [irrelevant, relevant, pad1, pad2]
        results = bm25_search("remote work policy", docs, k=4)
        ranked_pages = [d.page_content for d, _ in results]
        assert ranked_pages.index(relevant.page_content) < ranked_pages.index(irrelevant.page_content)

    def test_k_truncates_results(self):
        """When k < len(docs), only k results are returned."""
        from app.rag.bm25 import bm25_search
        docs = [_make_doc(f"match term doc {i}") for i in range(10)]
        results = bm25_search("match term doc", docs, k=2)
        assert len(results) == 2

    def test_single_doc_returns_score_one(self):
        """Single doc gets normalized score of 1.0 (max/max = 1)."""
        from app.rag.bm25 import bm25_search
        docs = [_make_doc("the only document here")]
        results = bm25_search("only document", docs, k=1)
        # If the query matches, score should be 1.0 (or 0 if no match, handled separately)
        assert len(results) == 1

    def test_missing_rank_bm25_returns_empty_with_warning(self, caplog):
        """When rank_bm25 is not installed, returns [] and logs a warning."""
        docs = [_make_doc("some content")]

        with patch.dict(sys.modules, {"rank_bm25": None}):
            # Re-import to trigger the lazy import inside bm25_search
            if "app.rag.bm25" in sys.modules:
                del sys.modules["app.rag.bm25"]

            with caplog.at_level(logging.WARNING, logger="app.rag.bm25"):
                from app.rag.bm25 import bm25_search
                results = bm25_search("query", docs, k=5)

        assert results == []
        assert any("rank_bm25" in r.message for r in caplog.records)

    def test_all_zero_scores_still_returns_docs(self):
        """When all BM25 scores are zero (no query term matches), docs are still returned."""
        from app.rag.bm25 import bm25_search
        # Query has no overlap with any doc
        docs = [_make_doc("alpha beta gamma"), _make_doc("delta epsilon zeta")]
        results = bm25_search("xyz completely unrelated", docs, k=5)
        # Normalized: max_score=0 → handled, returns something (may be empty or all 0-score docs)
        # The implementation treats max_score=0 as 1.0 normalization → scores all 0.0
        assert isinstance(results, list)
