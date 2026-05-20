"""BM25 lexical-search helper for hybrid dense+sparse retrieval (Feature 7).

rank_bm25 is a lightweight pure-Python BM25 implementation. Lazy-imported so the
module loads even when rank_bm25 is not installed — the retriever falls back to
dense-only search with a log warning.
"""
import logging
from typing import TYPE_CHECKING

from langchain_core.documents import Document

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Module-level BM25 index cache: (corpus_fingerprint, BM25Okapi).
# Avoids rebuilding the index on every query when the corpus hasn't changed
# (get_all_documents() already caches docs via a TTL, so the corpus is stable
# across queries within the same cache window).
_bm25_cache: "tuple[int, BM25Okapi] | None" = None


def bm25_search(query: str, docs: list[Document], k: int) -> list[tuple[Document, float]]:
    """Return (doc, normalized_bm25_score) pairs sorted descending, top-k.

    Tokenizes query and doc.page_content by whitespace. Scores are min-max
    normalized to [0, 1] so they can be combined with dense cosine scores via RRF.

    Returns [] (with a warning) if rank_bm25 is not installed or docs is empty.
    """
    global _bm25_cache

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning(
            "rank_bm25 not installed — BM25 hybrid search unavailable. "
            "Install with: pip install rank-bm25"
        )
        return []

    if not docs:
        return []

    corpus_key = hash(tuple(doc.page_content[:80] for doc in docs))
    if _bm25_cache is not None and _bm25_cache[0] == corpus_key:
        bm25 = _bm25_cache[1]
    else:
        tokenized_corpus = [doc.page_content.lower().split() for doc in docs]
        bm25 = BM25Okapi(tokenized_corpus)
        _bm25_cache = (corpus_key, bm25)

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    max_score = max(scores) if max(scores) > 0 else 1.0
    normalized = [s / max_score for s in scores]

    ranked = sorted(zip(docs, normalized), key=lambda x: x[1], reverse=True)
    return list(ranked[:k])
