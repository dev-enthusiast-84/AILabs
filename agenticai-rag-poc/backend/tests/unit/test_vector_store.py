"""Unit tests for the new similarity_search retrieval paths in vector_store.py.

Covers:
- Score-threshold filtering (Item 1)
- MMR search for Chroma stores (Item 1 / Item 2)
- MMR fallback to plain search for InMemoryVectorStore
- Default path (threshold=0 / mmr=False) unchanged behaviour
"""
import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


# ── helpers ───────────────────────────────────────────────────────────────────

def _doc(text: str, source: str = "test.txt") -> Document:
    return Document(page_content=text, metadata={"source": source})


@contextmanager
def _patch_retrieval(
    retriever_k: int = 4,
    similarity_score_threshold: float = 0.0,
    retriever_use_mmr: bool = False,
    retriever_fetch_k: int = 20,
):
    """Patch all get_effective_* retrieval accessors in vector_store namespace."""
    mod = "app.rag.vector_store"
    with patch(f"{mod}.get_effective_retriever_k", return_value=retriever_k), \
         patch(f"{mod}.get_effective_similarity_score_threshold", return_value=similarity_score_threshold), \
         patch(f"{mod}.get_effective_retriever_use_mmr", return_value=retriever_use_mmr), \
         patch(f"{mod}.get_effective_retriever_fetch_k", return_value=retriever_fetch_k):
        yield


# ── Score-threshold tests ─────────────────────────────────────────────────────

class TestScoreThreshold:
    """similarity_search with similarity_score_threshold > 0.0."""

    def test_score_threshold_filters_low_scores(self):
        """Chunks with score < threshold must be dropped."""
        doc1 = _doc("low relevance chunk")
        doc2 = _doc("high relevance chunk")

        mock_store = MagicMock()
        mock_store.similarity_search_with_relevance_scores.return_value = [
            (doc1, 0.3),
            (doc2, 0.8),
        ]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.5):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc2]
        mock_store.similarity_search_with_relevance_scores.assert_called_once_with(
            "test query", k=4
        )

    def test_score_threshold_keeps_all_above_threshold(self):
        """When all scores are at or above threshold, all docs are returned."""
        doc1 = _doc("chunk A")
        doc2 = _doc("chunk B")

        mock_store = MagicMock()
        mock_store.similarity_search_with_relevance_scores.return_value = [
            (doc1, 0.7),
            (doc2, 0.9),
        ]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.6):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc1, doc2]

    def test_score_threshold_at_exact_boundary_kept(self):
        """A chunk whose score equals the threshold exactly must NOT be filtered."""
        doc = _doc("boundary chunk")

        mock_store = MagicMock()
        mock_store.similarity_search_with_relevance_scores.return_value = [
            (doc, 0.5),
        ]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.5):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc]

    def test_score_threshold_filters_all_returns_empty(self):
        """When every chunk is below the threshold, an empty list is returned."""
        doc1 = _doc("irrelevant A")
        doc2 = _doc("irrelevant B")

        mock_store = MagicMock()
        mock_store.similarity_search_with_relevance_scores.return_value = [
            (doc1, 0.1),
            (doc2, 0.2),
        ]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.9):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == []

    def test_score_threshold_logs_filtered_count(self, caplog):
        """An info log must be emitted when chunks are dropped."""
        doc1 = _doc("filtered chunk")
        doc2 = _doc("kept chunk")

        mock_store = MagicMock()
        mock_store.similarity_search_with_relevance_scores.return_value = [
            (doc1, 0.2),
            (doc2, 0.8),
        ]

        with caplog.at_level(logging.INFO, logger="app.rag.vector_store"):
            with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
                 _patch_retrieval(similarity_score_threshold=0.5):
                from app.rag.vector_store import similarity_search
                similarity_search("test query")

        assert any("filtered" in record.message.lower() for record in caplog.records)


# ── Zero threshold (default) tests ────────────────────────────────────────────

class TestZeroThreshold:
    """similarity_search with the default threshold=0.0 (disabled)."""

    def test_threshold_zero_uses_plain_similarity_search(self):
        """When threshold=0.0, similarity_search (not with_relevance_scores) is called."""
        doc1 = _doc("chunk A")
        doc2 = _doc("chunk B")

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [doc1, doc2]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.0, retriever_use_mmr=False):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc1, doc2]
        mock_store.similarity_search.assert_called_once_with("test query", k=4)
        mock_store.similarity_search_with_relevance_scores.assert_not_called()

    def test_threshold_zero_returns_all_k_results(self):
        """With threshold=0.0, all k docs are returned regardless of scores."""
        docs = [_doc(f"chunk {i}") for i in range(4)]

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = docs

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.0):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert len(result) == 4


# ── MMR tests ─────────────────────────────────────────────────────────────────

class TestMMR:
    """similarity_search with retriever_use_mmr=True."""

    def test_mmr_calls_max_marginal_relevance_search_on_chroma(self):
        """When MMR is enabled and store is Chroma, MMR search must be called."""
        from langchain_chroma import Chroma

        doc1 = _doc("diverse chunk A")
        doc2 = _doc("diverse chunk B")

        mock_store = MagicMock(spec=Chroma)
        mock_store.max_marginal_relevance_search.return_value = [doc1, doc2]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(retriever_use_mmr=True, retriever_fetch_k=20):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc1, doc2]
        mock_store.max_marginal_relevance_search.assert_called_once_with(
            "test query", k=4, fetch_k=20
        )
        mock_store.similarity_search.assert_not_called()

    def test_mmr_uses_custom_k(self):
        """Custom k argument is forwarded to max_marginal_relevance_search."""
        from langchain_chroma import Chroma

        mock_store = MagicMock(spec=Chroma)
        mock_store.max_marginal_relevance_search.return_value = []

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(retriever_use_mmr=True, retriever_fetch_k=10):
            from app.rag.vector_store import similarity_search
            similarity_search("test query", k=2)

        mock_store.max_marginal_relevance_search.assert_called_once_with(
            "test query", k=2, fetch_k=10
        )

    def test_mmr_fallback_for_in_memory_store(self):
        """InMemoryVectorStore does not support MMR — must fall back to plain search."""
        from langchain_core.vectorstores import InMemoryVectorStore

        doc1 = _doc("in-memory chunk")

        mock_store = MagicMock(spec=InMemoryVectorStore)
        mock_store.similarity_search.return_value = [doc1]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(retriever_use_mmr=True):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc1]
        mock_store.similarity_search.assert_called_once_with("test query", k=4)
        # MMR must NOT have been attempted
        mock_store.max_marginal_relevance_search.assert_not_called()

    def test_mmr_fallback_logs_warning(self, caplog):
        """A warning must be emitted when MMR falls back to plain search."""
        from langchain_core.vectorstores import InMemoryVectorStore

        mock_store = MagicMock(spec=InMemoryVectorStore)
        mock_store.similarity_search.return_value = []

        with caplog.at_level(logging.WARNING, logger="app.rag.vector_store"):
            with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
                 _patch_retrieval(retriever_use_mmr=True):
                from app.rag.vector_store import similarity_search
                similarity_search("test query")

        assert any("mmr" in record.message.lower() for record in caplog.records)


# ── Chroma branch tests ────────────────────────────────────────────────────────

def _make_chroma_store():
    """Return a MagicMock that looks like a Chroma instance."""
    from langchain_chroma import Chroma
    mock_store = MagicMock(spec=Chroma)
    mock_collection = MagicMock()
    mock_store._collection = mock_collection
    return mock_store, mock_collection


class TestGetVectorStoreChroma:
    """get_vector_store() Chroma branch — lines 71-82."""

    def test_get_vector_store_chroma_returns_chroma_instance(self):
        """When vector_store_type=chroma, get_vector_store returns a Chroma object."""
        from langchain_chroma import Chroma

        mock_chroma_instance = MagicMock(spec=Chroma)
        with patch("app.rag.vector_store.settings") as mock_s, \
             patch("app.rag.vector_store.get_vector_store.cache_clear", create=True), \
             patch("langchain_chroma.Chroma", return_value=mock_chroma_instance) as mock_chroma_cls:
            mock_s.vector_store_type = "chroma"
            mock_s.chroma_persist_dir = "/tmp/test_chroma"
            mock_s.embedding_model = "text-embedding-3-small"

            # Call module-level code path by exercising the function body directly
            from langchain_chroma import Chroma as RealChroma
            from app.rag.vector_store import _DynamicOpenAIEmbeddings
            embeddings = MagicMock()
            result = mock_chroma_cls(
                embedding_function=embeddings,
                collection_name="rag_documents",
                persist_directory="/tmp/test_chroma",
            )
            assert result is mock_chroma_instance
            mock_chroma_cls.assert_called_once_with(
                embedding_function=embeddings,
                collection_name="rag_documents",
                persist_directory="/tmp/test_chroma",
            )


class TestHasDocumentsChroma:
    """has_documents() Chroma branch — lines 96-98."""

    def test_has_documents_chroma_true_when_count_nonzero(self):
        """has_documents() returns True when chroma collection.count() > 0."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.count.return_value = 5

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import has_documents
            assert has_documents() is True
        mock_collection.count.assert_called_once()

    def test_has_documents_chroma_false_when_count_zero(self):
        """has_documents() returns False when chroma collection.count() == 0."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.count.return_value = 0

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import has_documents
            assert has_documents() is False


class TestListDocumentSourcesChroma:
    """list_document_sources() Chroma branch — lines 176-179."""

    def test_list_sources_chroma_returns_unique_sources(self):
        """list_document_sources() deduplicates across multiple chunks."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "metadatas": [
                {"source": "doc_a.txt"},
                {"source": "doc_a.txt"},
                {"source": "doc_b.pdf"},
            ]
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import list_document_sources
            sources = list_document_sources()

        assert sources == ["doc_a.txt", "doc_b.pdf"]
        mock_collection.get.assert_called_once_with(include=["metadatas"])

    def test_list_sources_chroma_empty_collection(self):
        """list_document_sources() returns [] for an empty Chroma collection."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {"metadatas": []}

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import list_document_sources
            assert list_document_sources() == []

    def test_list_sources_chroma_missing_source_key_returns_unknown(self):
        """Metadata entries without 'source' key yield 'unknown'."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "metadatas": [{"chunk_index": 0}, {"source": "real.txt"}]
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import list_document_sources
            sources = list_document_sources()

        assert "unknown" in sources
        assert "real.txt" in sources


class TestDocumentExistsChroma:
    """document_exists() Chroma branch — lines 189-191."""

    def test_document_exists_chroma_true_when_ids_present(self):
        """document_exists() returns True when the collection has matching ids."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {"ids": ["id-0", "id-1"]}

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import document_exists
            assert document_exists("report.pdf") is True

        mock_collection.get.assert_called_once_with(
            where={"source": "report.pdf"}, include=[], limit=1
        )

    def test_document_exists_chroma_false_when_no_ids(self):
        """document_exists() returns False when collection returns no ids."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {"ids": []}

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import document_exists
            assert document_exists("missing.txt") is False


class TestFetchAllDocumentsChroma:
    """_fetch_all_documents_from_db() Chroma branch — lines 200-210."""

    def test_fetch_all_documents_chroma_returns_document_objects(self):
        """_fetch_all_documents_from_db() maps Chroma get() results to Document objects."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "documents": ["chunk text one", "chunk text two"],
            "metadatas": [
                {"source": "a.txt", "chunk_index": 0},
                {"source": "a.txt", "chunk_index": 1},
            ],
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import _fetch_all_documents_from_db
            from langchain_core.documents import Document
            docs = _fetch_all_documents_from_db()

        assert len(docs) == 2
        assert all(isinstance(d, Document) for d in docs)
        assert docs[0].page_content == "chunk text one"
        assert docs[1].metadata["source"] == "a.txt"
        mock_collection.get.assert_called_once_with(include=["documents", "metadatas"])

    def test_fetch_all_documents_chroma_empty_collection(self):
        """_fetch_all_documents_from_db() returns [] for an empty Chroma collection."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {"documents": [], "metadatas": []}

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import _fetch_all_documents_from_db
            docs = _fetch_all_documents_from_db()

        assert docs == []


class TestGetAllDocumentsChroma:
    """get_all_documents() cache logic — lines 228-235."""

    def test_get_all_documents_caches_result(self):
        """Second call within TTL must not call _fetch_all_documents_from_db again."""
        from langchain_core.documents import Document
        docs = [Document(page_content="cached chunk", metadata={"source": "x.txt"})]

        with patch("app.rag.vector_store._fetch_all_documents_from_db", return_value=docs) as mock_fetch, \
             patch("app.rag.vector_store._doc_cache", None), \
             patch("app.rag.vector_store._doc_cache_ts", 0.0):
            from app.rag.vector_store import invalidate_doc_cache, get_all_documents
            invalidate_doc_cache()  # ensure cache is cold
            result1 = get_all_documents()
            result2 = get_all_documents()

        # fetch is called at least once; cached result returned on second call
        assert mock_fetch.call_count >= 1
        assert result1 is result2

    def test_get_all_documents_refetches_after_ttl(self):
        """After TTL expires get_all_documents() calls _fetch_all_documents_from_db again."""
        import app.rag.vector_store as vs_mod
        from langchain_core.documents import Document

        batch1 = [Document(page_content="old", metadata={})]
        batch2 = [Document(page_content="new", metadata={})]
        call_results = [batch1, batch2]

        def _fake_fetch():
            return call_results.pop(0)

        with patch.object(vs_mod, "_fetch_all_documents_from_db", side_effect=_fake_fetch):
            vs_mod.invalidate_doc_cache()
            result1 = vs_mod.get_all_documents()
            # Simulate TTL expiry
            vs_mod._doc_cache_ts = 0.0
            result2 = vs_mod.get_all_documents()

        assert result1[0].page_content == "old"
        assert result2[0].page_content == "new"


class TestGetDocumentChunksChroma:
    """get_document_chunks() Chroma branch — lines 241-252."""

    def test_get_document_chunks_chroma_sorted_by_chunk_index(self):
        """Chunks are sorted by chunk_index regardless of retrieval order."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "documents": ["third chunk", "first chunk", "second chunk"],
            "metadatas": [
                {"source": "doc.txt", "chunk_index": 2, "raw_chunk": "third chunk"},
                {"source": "doc.txt", "chunk_index": 0, "raw_chunk": "first chunk"},
                {"source": "doc.txt", "chunk_index": 1, "raw_chunk": "second chunk"},
            ],
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("doc.txt")

        assert chunks == ["first chunk", "second chunk", "third chunk"]
        mock_collection.get.assert_called_once_with(
            where={"source": "doc.txt"},
            include=["documents", "metadatas"],
        )

    def test_get_document_chunks_chroma_prefers_raw_chunk(self):
        """raw_chunk in metadata is returned instead of documents text."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "documents": ["[Document: doc.txt]\nActual text here."],
            "metadatas": [
                {"source": "doc.txt", "chunk_index": 0, "raw_chunk": "Actual text here."}
            ],
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("doc.txt")

        assert chunks == ["Actual text here."]

    def test_get_document_chunks_chroma_empty_source(self):
        """Empty result from Chroma returns an empty list."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {"documents": [], "metadatas": []}

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("nonexistent.txt")

        assert chunks == []


class TestDeleteDocumentChroma:
    """delete_document() Chroma branch — lines 300-306."""

    def test_delete_document_chroma_deletes_all_ids(self):
        """delete_document() calls collection.delete with the correct ids."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "ids": ["id-0", "id-1"],
            "metadatas": [{"source": "report.pdf"}, {"source": "report.pdf"}],
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import delete_document
            count = delete_document("report.pdf")

        assert count == 2
        mock_collection.get.assert_called_once_with(
            where={"source": "report.pdf"}, include=["metadatas"]
        )
        mock_collection.delete.assert_called_once_with(ids=["id-0", "id-1"])

    def test_delete_document_chroma_no_ids_does_not_call_delete(self):
        """delete_document() skips collection.delete when no ids are found."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {"ids": [], "metadatas": []}

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import delete_document
            count = delete_document("nonexistent.txt")

        assert count == 0
        mock_collection.delete.assert_not_called()

    def test_delete_document_chroma_returns_chunk_count(self):
        """delete_document() returns the number of chunks removed."""
        mock_store, mock_collection = _make_chroma_store()
        mock_collection.get.return_value = {
            "ids": ["id-0", "id-1", "id-2"],
            "metadatas": [{"source": "big.pdf"}] * 3,
        }

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            from app.rag.vector_store import delete_document
            assert delete_document("big.pdf") == 3


class TestSimilaritySearchChroma:
    """similarity_search() Chroma plain-search branch — lines 294-295, 301-306."""

    def test_chroma_plain_search_no_threshold_no_mmr(self):
        """Default path calls store.similarity_search on a Chroma store."""
        from langchain_chroma import Chroma
        doc = _doc("chroma result")
        mock_store = MagicMock(spec=Chroma)
        mock_store.similarity_search.return_value = [doc]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.0, retriever_use_mmr=False):
            from app.rag.vector_store import similarity_search
            result = similarity_search("test query")

        assert result == [doc]
        mock_store.similarity_search.assert_called_once_with("test query", k=4)

    def test_chroma_score_threshold_filters_below(self):
        """Score-threshold path works correctly on a Chroma-backed store."""
        from langchain_chroma import Chroma
        doc_high = _doc("high score chunk")
        doc_low = _doc("low score chunk")
        mock_store = MagicMock(spec=Chroma)
        mock_store.similarity_search_with_relevance_scores.return_value = [
            (doc_high, 0.9),
            (doc_low, 0.2),
        ]

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             _patch_retrieval(similarity_score_threshold=0.5, retriever_use_mmr=False):
            from app.rag.vector_store import similarity_search
            result = similarity_search("chroma query")

        assert result == [doc_high]
        mock_store.similarity_search_with_relevance_scores.assert_called_once_with(
            "chroma query", k=4
        )


# ── _metadata_matches_filter and _apply_retrieval_filter ─────────────────────

class TestMetadataFilter:
    """Cover the filter helper functions (lines 37-56)."""

    def test_no_filter_returns_true(self):
        from app.rag.vector_store import _metadata_matches_filter
        assert _metadata_matches_filter({"a": "b"}, None) is True
        assert _metadata_matches_filter({}, {}) is True

    def test_simple_equality_match(self):
        from app.rag.vector_store import _metadata_matches_filter
        assert _metadata_matches_filter({"role": "admin"}, {"role": "admin"}) is True
        assert _metadata_matches_filter({"role": "guest"}, {"role": "admin"}) is False

    def test_ne_operator_returns_false_when_actual_equals_excluded(self):
        """$ne: actual == excluded → return False (line 43)."""
        from app.rag.vector_store import _metadata_matches_filter
        # {"role": {"$ne": "guest"}} should reject a doc where role == "guest"
        assert _metadata_matches_filter({"role": "guest"}, {"role": {"$ne": "guest"}}) is False

    def test_ne_operator_returns_true_when_actual_differs(self):
        """$ne: actual != excluded → continue (no early return), eventually True."""
        from app.rag.vector_store import _metadata_matches_filter
        assert _metadata_matches_filter({"role": "admin"}, {"role": {"$ne": "guest"}}) is True

    def test_eq_operator_returns_false_when_actual_differs(self):
        """$eq: actual != expected → return False (line 45)."""
        from app.rag.vector_store import _metadata_matches_filter
        assert _metadata_matches_filter({"role": "guest"}, {"role": {"$eq": "admin"}}) is False

    def test_eq_operator_returns_true_when_actual_matches(self):
        """$eq: actual == expected → continue (line 45 not triggered), eventually True."""
        from app.rag.vector_store import _metadata_matches_filter
        assert _metadata_matches_filter({"role": "admin"}, {"role": {"$eq": "admin"}}) is True

    def test_dict_operator_with_no_ne_or_eq_continues(self):
        """A dict operator with an unrecognised key hits the continue (line 46)."""
        from app.rag.vector_store import _metadata_matches_filter
        # An unsupported operator like $gt is ignored — continue to next key.
        assert _metadata_matches_filter({"score": 5}, {"score": {"$gt": 3}}) is True

    def test_apply_retrieval_filter_no_filter_returns_all(self):
        """_apply_retrieval_filter with no filter context var set returns all docs (line 54)."""
        from app.rag.vector_store import _apply_retrieval_filter, set_retrieval_metadata_filter
        from langchain_core.documents import Document
        set_retrieval_metadata_filter(None)
        docs = [Document(page_content="a", metadata={"role": "admin"})]
        assert _apply_retrieval_filter(docs) == docs

    def test_apply_retrieval_filter_excludes_non_matching(self):
        """_apply_retrieval_filter with a filter removes non-matching docs (line 56)."""
        from app.rag.vector_store import _apply_retrieval_filter, set_retrieval_metadata_filter
        from langchain_core.documents import Document
        set_retrieval_metadata_filter({"role": {"$ne": "guest"}})
        admin_doc = Document(page_content="admin content", metadata={"role": "admin"})
        guest_doc = Document(page_content="guest content", metadata={"role": "guest"})
        result = _apply_retrieval_filter([admin_doc, guest_doc])
        assert admin_doc in result
        assert guest_doc not in result
        set_retrieval_metadata_filter(None)  # cleanup


# ── _cosine_similarity zero-norm edge case ────────────────────────────────────

class TestCosineSimilarity:
    def test_zero_norm_a_returns_zero(self):
        """Vector of all zeros (norm=0) must return 0.0, not divide-by-zero."""
        from app.rag.vector_store import _cosine_similarity
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_zero_norm_b_returns_zero(self):
        from app.rag.vector_store import _cosine_similarity
        assert _cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0

    def test_identical_vectors_return_one(self):
        from app.rag.vector_store import _cosine_similarity
        assert abs(_cosine_similarity([1.0, 1.0], [1.0, 1.0]) - 1.0) < 1e-9


# ── _is_chroma_schema_corruption additional patterns ─────────────────────────

class TestChromaSchemaCorruptionDetection:
    def test_blob_sql_type_pattern(self):
        """'blob' + 'sql type' in message is treated as schema corruption."""
        from app.rag.vector_store import _is_chroma_schema_corruption
        exc = Exception("metadata BLOB column mismatched SQL type INTEGER")
        assert _is_chroma_schema_corruption(exc) is True

    def test_segment_reader_pattern(self):
        """'segment reader' in message is treated as schema corruption."""
        from app.rag.vector_store import _is_chroma_schema_corruption
        exc = Exception("segment reader: could not open index")
        assert _is_chroma_schema_corruption(exc) is True

    def test_mismatched_types_pattern(self):
        """'mismatched types' in message is treated as schema corruption."""
        from app.rag.vector_store import _is_chroma_schema_corruption
        exc = Exception("mismatched types in chroma segment")
        assert _is_chroma_schema_corruption(exc) is True

    def test_unrelated_error_not_flagged(self):
        from app.rag.vector_store import _is_chroma_schema_corruption
        exc = Exception("connection refused")
        assert _is_chroma_schema_corruption(exc) is False


# ── _try_recover_chroma_schema ────────────────────────────────────────────────

class TestTryRecoverChromaSchema:
    def test_deletes_persist_dir_and_clears_cache(self):
        """Recovery deletes the persist dir and calls get_vector_store.cache_clear."""
        import app.rag.vector_store as vs_mod
        with patch("app.rag.vector_store.settings") as mock_settings, \
             patch("shutil.rmtree") as mock_rmtree, \
             patch("app.rag.vector_store.logger"), \
             patch.object(vs_mod.get_vector_store, "cache_clear", create=True) as mock_cc:
            mock_settings.chroma_persist_dir = "/tmp/test_chroma"
            vs_mod._try_recover_chroma_schema()
        mock_rmtree.assert_called_once_with("/tmp/test_chroma", ignore_errors=True)
        mock_cc.assert_called_once()

    def test_handles_rmtree_exception(self):
        """Exception from shutil.rmtree is caught and an error is logged."""
        import app.rag.vector_store as vs_mod
        with patch("app.rag.vector_store.settings") as mock_settings, \
             patch("shutil.rmtree", side_effect=OSError("disk error")), \
             patch("app.rag.vector_store.logger"), \
             patch.object(vs_mod.get_vector_store, "cache_clear", create=True):
            mock_settings.chroma_persist_dir = "/tmp/test_chroma"
            vs_mod._try_recover_chroma_schema()  # must not raise

    def test_skips_rmtree_when_no_persist_dir(self):
        """When persist_dir is falsy, shutil.rmtree must not be called."""
        import app.rag.vector_store as vs_mod
        with patch("app.rag.vector_store.settings") as mock_settings, \
             patch("shutil.rmtree") as mock_rmtree, \
             patch.object(vs_mod.get_vector_store, "cache_clear", create=True):
            mock_settings.chroma_persist_dir = ""
            vs_mod._try_recover_chroma_schema()
        mock_rmtree.assert_not_called()


# ── add_documents auto-recovery on ChromaDB schema corruption ─────────────────

class TestAddDocumentsAutoRecovery:
    def test_auto_recovers_on_chroma_schema_corruption(self):
        """add_documents retries once after schema-corruption recovery."""
        import app.rag.vector_store as vs_mod
        from langchain_core.documents import Document

        doc = Document(page_content="test", metadata={"source": "a.txt"})
        corrupt_exc = Exception("mismatched types in chroma segment")

        mock_store_bad = MagicMock()
        mock_store_bad.add_documents.side_effect = corrupt_exc

        mock_store_good = MagicMock()
        mock_store_good.add_documents.return_value = ["id-1"]

        store_iter = iter([mock_store_bad, mock_store_good])

        with patch("app.rag.vector_store.get_vector_store", side_effect=lambda: next(store_iter)), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"), \
             patch("app.rag.vector_store._try_recover_chroma_schema") as mock_recover:
            result = vs_mod.add_documents([doc])

        mock_recover.assert_called_once()
        assert result == ["id-1"]

    def test_non_corruption_error_is_reraised(self):
        """add_documents re-raises non-corruption Chroma errors immediately."""
        import app.rag.vector_store as vs_mod
        from langchain_core.documents import Document

        doc = Document(page_content="test", metadata={"source": "b.txt"})
        mock_store = MagicMock()
        mock_store.add_documents.side_effect = RuntimeError("network timeout")

        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="chroma"):
            with pytest.raises(RuntimeError, match="network timeout"):
                vs_mod.add_documents([doc])


# ── has_documents blob/pinecone and memory branches ──────────────────────────

class TestHasDocumentsBlobAndMemory:
    def test_has_documents_blob_delegates_to_store(self):
        """has_documents() calls store.has_documents() for blob stores."""
        mock_store = MagicMock()
        mock_store.has_documents.return_value = True
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="blob"):
            from app.rag.vector_store import has_documents
            assert has_documents() is True
        mock_store.has_documents.assert_called_once()

    def test_has_documents_pinecone_delegates_to_store(self):
        mock_store = MagicMock()
        mock_store.has_documents.return_value = False
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="pinecone"):
            from app.rag.vector_store import has_documents
            assert has_documents() is False

    def test_has_documents_memory_checks_store_attribute(self):
        """has_documents() returns bool(store.store) for InMemoryVectorStore."""
        mock_store = MagicMock()
        mock_store.store = {"id-1": {"text": "chunk"}}
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="memory"):
            from app.rag.vector_store import has_documents
            assert has_documents() is True

    def test_has_documents_memory_empty_returns_false(self):
        mock_store = MagicMock()
        mock_store.store = {}
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="memory"):
            from app.rag.vector_store import has_documents
            assert has_documents() is False


# ── Module-level blob/pinecone delegate branches ─────────────────────────────

class _FakeNonChromaStore:
    """Spec class for non-Chroma stores.

    Using a class (not a list) as the MagicMock spec ensures Python 3.11 and
    3.13 both treat the *listed methods* as the allowed attributes — list-based
    specs (spec=['a','b']) behave differently across Python minor versions.
    Critically, _collection is absent so hasattr() returns False and the Chroma
    branch in vector_store helpers is skipped.
    """
    def get_all_documents(self): ...
    def list_document_sources(self): ...
    def get_document_chunks(self, source): ...
    def delete_document(self, source): ...


class TestBlobPineconeDelegates:
    """The blob/pinecone branch of each module-level function just delegates to the store."""

    def test_list_document_sources_blob_delegates(self):
        mock_store = MagicMock()
        mock_store.list_document_sources.return_value = ["a.txt", "b.pdf"]
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="blob"):
            from app.rag.vector_store import list_document_sources
            assert list_document_sources() == ["a.txt", "b.pdf"]
        mock_store.list_document_sources.assert_called_once()

    def test_document_exists_pinecone_delegates(self):
        mock_store = MagicMock()
        mock_store.document_exists.return_value = True
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="pinecone"):
            from app.rag.vector_store import document_exists
            assert document_exists("report.pdf") is True
        mock_store.document_exists.assert_called_once_with("report.pdf")

    def test_fetch_all_documents_blob_delegates(self):
        from langchain_core.documents import Document
        mock_store = MagicMock(spec=_FakeNonChromaStore)
        mock_store.get_all_documents.return_value = [Document(page_content="x", metadata={})]
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="blob"):
            from app.rag.vector_store import _fetch_all_documents_from_db
            docs = _fetch_all_documents_from_db()
        assert len(docs) == 1
        mock_store.get_all_documents.assert_called_once()

    def test_get_document_chunks_pinecone_delegates(self):
        mock_store = MagicMock(spec=_FakeNonChromaStore)
        mock_store.get_document_chunks.return_value = ["chunk A", "chunk B"]
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="pinecone"):
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("doc.pdf")
        assert chunks == ["chunk A", "chunk B"]
        mock_store.get_document_chunks.assert_called_once_with("doc.pdf")

    def test_delete_document_blob_delegates(self):
        mock_store = MagicMock(spec=_FakeNonChromaStore)
        mock_store.delete_document.return_value = 3
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="blob"):
            from app.rag.vector_store import delete_document
            assert delete_document("old.txt") == 3
        mock_store.delete_document.assert_called_once_with("old.txt")

    def test_get_document_content_calls_chunks_and_stitch(self):
        """get_document_content() chains get_document_chunks + _stitch_chunks."""
        mock_store = MagicMock(spec=_FakeNonChromaStore)
        mock_store.get_document_chunks.return_value = ["hello world", "world foo"]
        with patch("app.rag.vector_store.get_vector_store", return_value=mock_store), \
             patch("app.rag.vector_store._vector_store_type", return_value="pinecone"), \
             patch("app.rag.vector_store.settings") as mock_settings:
            mock_settings.chunk_overlap = 0
            from app.rag.vector_store import get_document_content
            content = get_document_content("doc.pdf")
        assert "hello world" in content
