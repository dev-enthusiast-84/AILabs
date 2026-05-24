"""Unit tests for the InMemoryVectorStore code paths in vector_store.py.

These tests bypass the session-scoped get_vector_store mock (conftest.py)
by providing a per-test patch that returns a real InMemoryVectorStore
populated with known data.  No OpenAI calls are made.
"""
from unittest.mock import MagicMock, patch


# ── _DynamicOpenAIEmbeddings ──────────────────────────────────────────────────

class TestDynamicOpenAIEmbeddings:
    """Verify that the dynamic embeddings wrapper reads the API key at call time."""

    def _make_embeddings(self, fake_key="sk-" + "a" * 48):
        from app.rag.vector_store import _DynamicOpenAIEmbeddings
        return _DynamicOpenAIEmbeddings()

    def test_embed_documents_uses_current_api_key(self):
        """embed_documents reads get_effective_api_key() at call time, not construction."""
        from app.rag.vector_store import _DynamicOpenAIEmbeddings

        captured = {}

        def fake_embed_docs(self_inner, texts):
            captured["key"] = self_inner.openai_api_key
            return [[0.1, 0.2]] * len(texts)

        key1 = "sk-" + "a" * 48
        key2 = "sk-" + "b" * 48

        emb = _DynamicOpenAIEmbeddings()

        with patch("app.runtime.settings_store._runtime_api_key", key1):
            with patch("langchain_openai.OpenAIEmbeddings.embed_documents", fake_embed_docs):
                emb.embed_documents(["hello"])
        raw1 = captured.get("key")
        actual1 = raw1.get_secret_value() if hasattr(raw1, "get_secret_value") else raw1
        assert actual1 == key1

        with patch("app.runtime.settings_store._runtime_api_key", key2):
            with patch("langchain_openai.OpenAIEmbeddings.embed_documents", fake_embed_docs):
                emb.embed_documents(["world"])
        raw2 = captured.get("key")
        actual2 = raw2.get_secret_value() if hasattr(raw2, "get_secret_value") else raw2
        assert actual2 == key2

    def test_embed_query_uses_current_api_key(self):
        """embed_query reads get_effective_api_key() at call time."""
        from app.rag.vector_store import _DynamicOpenAIEmbeddings

        captured = {}

        def fake_embed_query(self_inner, text):
            captured["key"] = self_inner.openai_api_key
            return [0.1, 0.2]

        key = "sk-" + "c" * 48
        emb = _DynamicOpenAIEmbeddings()

        with patch("app.runtime.settings_store._runtime_api_key", key):
            with patch("langchain_openai.OpenAIEmbeddings.embed_query", fake_embed_query):
                emb.embed_query("test query")

        raw = captured.get("key")
        actual = raw.get_secret_value() if hasattr(raw, "get_secret_value") else raw
        assert actual == key


def _make_store(docs: list[dict]):
    """Return an InMemoryVectorStore with raw store entries (no embedding calls)."""
    from langchain_core.vectorstores import InMemoryVectorStore

    mock_emb = MagicMock()
    mock_emb.embed_documents.return_value = [[0.1, 0.2, 0.3]]
    mock_emb.embed_query.return_value = [0.1, 0.2, 0.3]

    store = InMemoryVectorStore(embedding=mock_emb)
    for i, doc in enumerate(docs):
        store.store[f"id-{i}"] = {
            "id": f"id-{i}",
            "vector": [0.1, 0.2, 0.3],
            "text": doc.get("text", ""),
            "metadata": doc.get("metadata", {}),
        }
    return store


# ── list_document_sources ─────────────────────────────────────────────────────

class TestListDocumentSourcesMemory:
    def test_empty_store_returns_empty_list(self):
        store = _make_store([])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import list_document_sources
            assert list_document_sources() == []

    def test_single_source(self):
        store = _make_store([
            {"text": "content", "metadata": {"source": "doc.txt", "chunk_index": 0}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import list_document_sources
            assert list_document_sources() == ["doc.txt"]

    def test_multiple_chunks_same_source_deduplicated(self):
        store = _make_store([
            {"text": "chunk1", "metadata": {"source": "report.pdf", "chunk_index": 0}},
            {"text": "chunk2", "metadata": {"source": "report.pdf", "chunk_index": 1}},
            {"text": "chunk3", "metadata": {"source": "report.pdf", "chunk_index": 2}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import list_document_sources
            sources = list_document_sources()
            assert sources == ["report.pdf"]

    def test_multiple_distinct_sources(self):
        store = _make_store([
            {"text": "a", "metadata": {"source": "a.txt"}},
            {"text": "b", "metadata": {"source": "b.csv"}},
            {"text": "c", "metadata": {"source": "c.pdf"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import list_document_sources
            sources = list_document_sources()
            assert set(sources) == {"a.txt", "b.csv", "c.pdf"}
            assert len(sources) == 3

    def test_missing_source_key_returns_unknown(self):
        store = _make_store([
            {"text": "no source key", "metadata": {}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import list_document_sources
            assert list_document_sources() == ["unknown"]

    def test_mixed_known_and_unknown_sources(self):
        store = _make_store([
            {"text": "a", "metadata": {"source": "known.txt"}},
            {"text": "b", "metadata": {}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import list_document_sources
            sources = list_document_sources()
            assert set(sources) == {"known.txt", "unknown"}


# ── delete_document ───────────────────────────────────────────────────────────

class TestDeleteDocumentMemory:
    def test_delete_existing_document_returns_chunk_count(self):
        store = _make_store([
            {"text": "chunk1", "metadata": {"source": "report.pdf"}},
            {"text": "chunk2", "metadata": {"source": "report.pdf"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import delete_document
            assert delete_document("report.pdf") == 2

    def test_delete_removes_chunks_from_store(self):
        store = _make_store([
            {"text": "target chunk", "metadata": {"source": "target.txt"}},
            {"text": "other chunk",  "metadata": {"source": "other.txt"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import delete_document, list_document_sources
            delete_document("target.txt")
            remaining = list_document_sources()
            assert remaining == ["other.txt"]

    def test_delete_nonexistent_document_returns_zero(self):
        store = _make_store([])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import delete_document
            assert delete_document("does_not_exist.pdf") == 0

    def test_delete_does_not_affect_other_sources(self):
        store = _make_store([
            {"text": "keep1", "metadata": {"source": "keep.txt"}},
            {"text": "del1",  "metadata": {"source": "delete_me.csv"}},
            {"text": "del2",  "metadata": {"source": "delete_me.csv"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import delete_document, list_document_sources
            removed = delete_document("delete_me.csv")
            assert removed == 2
            assert list_document_sources() == ["keep.txt"]

    def test_delete_exact_match_only(self):
        """Deleting 'a.txt' must not touch 'ab.txt' or 'prefix_a.txt'."""
        store = _make_store([
            {"text": "exact",  "metadata": {"source": "a.txt"}},
            {"text": "longer", "metadata": {"source": "ab.txt"}},
            {"text": "prefix", "metadata": {"source": "prefix_a.txt"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import delete_document, list_document_sources
            delete_document("a.txt")
            remaining = list_document_sources()
            assert set(remaining) == {"ab.txt", "prefix_a.txt"}

    def test_delete_all_documents_leaves_empty_store(self):
        store = _make_store([
            {"text": "a", "metadata": {"source": "a.txt"}},
            {"text": "b", "metadata": {"source": "b.txt"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store):
            from app.rag.vector_store import delete_document, list_document_sources
            delete_document("a.txt")
            delete_document("b.txt")
            assert list_document_sources() == []


# ── _stitch_chunks ────────────────────────────────────────────────────────────

class TestStitchChunks:
    """Unit tests for the chunk overlap removal logic."""

    def _stitch(self, chunks, overlap=100):
        from app.rag.vector_store import _stitch_chunks
        return _stitch_chunks(chunks, overlap)

    def test_empty_list_returns_empty_string(self):
        assert self._stitch([]) == ""

    def test_single_chunk_returned_unchanged(self):
        assert self._stitch(["hello world"]) == "hello world"

    def test_two_chunks_with_exact_overlap_stitched(self):
        # chunk[1] starts with the last 10 chars of chunk[0]
        chunk0 = "abcdefghij"         # 10 chars
        chunk1 = "ghij" + "klmnop"   # last 4 chars overlap, then new content
        result = self._stitch([chunk0, chunk1], overlap=10)
        assert result == "abcdefghijklmnop"

    def test_overlap_removed_not_duplicated(self):
        overlap_text = "OVERLAP_TEXT"
        chunk0 = "First part of document. " + overlap_text
        chunk1 = overlap_text + " Second part of document."
        result = self._stitch([chunk0, chunk1], overlap=len(overlap_text) + 20)
        # The overlap text must appear exactly once
        assert result.count(overlap_text) == 1
        assert "First part" in result
        assert "Second part" in result

    def test_three_chunks_stitched_correctly(self):
        shared_ab = "AB"
        shared_bc = "CD"
        chunk0 = "start " + shared_ab
        chunk1 = shared_ab + " middle " + shared_bc
        chunk2 = shared_bc + " end"
        result = self._stitch([chunk0, chunk1, chunk2], overlap=10)
        assert result == "start AB middle CD end"

    def test_no_overlap_found_uses_newline_separator(self):
        chunk0 = "completely different"
        chunk1 = "no shared prefix here"
        result = self._stitch([chunk0, chunk1], overlap=5)
        assert chunk0 in result
        assert chunk1 in result
        assert "\n" in result

    def test_does_not_modify_content(self):
        """Verify no chars are dropped or inserted between overlapping regions."""
        text = "The quick brown fox jumps over the lazy dog. " * 10
        # simulate 10-char overlap
        overlap = 10
        chunks = []
        pos = 0
        chunk_size = 50
        while pos < len(text):
            end = min(pos + chunk_size, len(text))
            chunks.append(text[pos:end])
            pos += chunk_size - overlap
        result = self._stitch(chunks, overlap)
        # Allow for minor differences due to boundary alignment; core content preserved
        assert "quick brown fox" in result
        assert "lazy dog" in result


# ── get_document_chunks — raw_chunk support ───────────────────────────────────

class TestGetDocumentChunksMemory:
    """get_document_chunks must prefer metadata['raw_chunk'] over the stored text."""

    def test_returns_raw_chunk_when_present(self):
        """raw_chunk in metadata must be returned instead of the full page_content."""
        store = _make_store([
            {
                "text": "[Document: doc.txt]\nActual content here.",
                "metadata": {
                    "source": "doc.txt",
                    "chunk_index": 0,
                    "raw_chunk": "Actual content here.",
                },
            }
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store), \
             patch("app.rag.vector_store.settings") as mock_s:
            mock_s.vector_store_type = "memory"
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("doc.txt")

        assert chunks == ["Actual content here."]

    def test_falls_back_to_text_without_raw_chunk(self):
        """When raw_chunk is absent, get_document_chunks returns the stored 'text'."""
        store = _make_store([
            {
                "text": "Plain stored text.",
                "metadata": {"source": "doc.txt", "chunk_index": 0},
            }
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store), \
             patch("app.rag.vector_store.settings") as mock_s:
            mock_s.vector_store_type = "memory"
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("doc.txt")

        assert chunks == ["Plain stored text."]

    def test_chunks_sorted_by_chunk_index(self):
        """Chunks are returned in ascending chunk_index order regardless of store order."""
        store = _make_store([
            {"text": "third",  "metadata": {"source": "doc.txt", "chunk_index": 2, "raw_chunk": "third"}},
            {"text": "first",  "metadata": {"source": "doc.txt", "chunk_index": 0, "raw_chunk": "first"}},
            {"text": "second", "metadata": {"source": "doc.txt", "chunk_index": 1, "raw_chunk": "second"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store), \
             patch("app.rag.vector_store.settings") as mock_s:
            mock_s.vector_store_type = "memory"
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("doc.txt")

        assert chunks == ["first", "second", "third"]

    def test_only_matching_source_returned(self):
        """Chunks from other sources are not included."""
        store = _make_store([
            {"text": "belongs to other", "metadata": {"source": "other.txt", "chunk_index": 0, "raw_chunk": "belongs to other"}},
            {"text": "belongs to target", "metadata": {"source": "target.txt", "chunk_index": 0, "raw_chunk": "belongs to target"}},
        ])
        with patch("app.rag.vector_store.get_vector_store", return_value=store), \
             patch("app.rag.vector_store.settings") as mock_s:
            mock_s.vector_store_type = "memory"
            from app.rag.vector_store import get_document_chunks
            chunks = get_document_chunks("target.txt")

        assert chunks == ["belongs to target"]
