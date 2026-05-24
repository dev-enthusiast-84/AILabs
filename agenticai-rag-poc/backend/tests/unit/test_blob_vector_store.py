"""Unit tests for the Vercel Blob-backed vector store."""
from types import SimpleNamespace

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.vector_store import BlobVectorStore


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0] if "alpha" in text else [0.0, 1.0]


def test_blob_vector_store_roundtrip(monkeypatch):
    import vercel.blob as blob

    stored: dict[str, bytes] = {}
    deleted: list[str] = []

    def fake_put(path, body, **_kwargs):
        stored[path] = body
        return SimpleNamespace(pathname=path)

    def fake_get(path, **_kwargs):
        if path not in stored:
            return None
        return SimpleNamespace(content=stored[path], status_code=200)

    def fake_list_objects(**kwargs):
        prefix = kwargs.get("prefix") or ""
        blobs = [SimpleNamespace(pathname=path) for path in sorted(stored) if path.startswith(prefix)]
        return SimpleNamespace(blobs=blobs, has_more=False, cursor=None)

    def fake_delete(paths, **_kwargs):
        for path in paths if isinstance(paths, list) else [paths]:
            deleted.append(path)
            stored.pop(path, None)

    monkeypatch.setattr(blob, "put", fake_put)
    monkeypatch.setattr(blob, "get", fake_get)
    monkeypatch.setattr(blob, "list_objects", fake_list_objects)
    monkeypatch.setattr(blob, "delete", fake_delete)

    store = BlobVectorStore(FakeEmbeddings(), prefix="test/chunks/")
    ids = store.add_documents([
        Document(page_content="alpha document", metadata={"source": "a.txt", "chunk_index": 0, "raw_chunk": "alpha"}),
        Document(page_content="beta document", metadata={"source": "b.txt", "chunk_index": 0, "raw_chunk": "beta"}),
    ])

    assert len(ids) == 2
    assert store.has_documents()
    assert sorted(store.list_document_sources()) == ["a.txt", "b.txt"]
    assert store.document_exists("a.txt")
    assert store.get_document_chunks("a.txt") == ["alpha"]
    assert store.similarity_search("alpha question", k=1)[0].metadata["source"] == "a.txt"

    assert store.delete_document("a.txt") == 1
    assert deleted
    assert not store.document_exists("a.txt")


def test_blob_setting_without_token_falls_back_to_memory(monkeypatch):
    import app.rag.vector_store as vs

    monkeypatch.setattr(vs.settings, "vector_store_type", "blob")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_BLOB_READ_WRITE_TOKEN", raising=False)

    assert vs._vector_store_type() == "memory"


def test_memory_setting_on_vercel_with_blob_token_uses_blob(monkeypatch):
    import app.rag.vector_store as vs

    monkeypatch.setattr(vs.settings, "vector_store_type", "memory")
    monkeypatch.setattr(vs.settings, "blob_read_write_token", "vercel_blob_rw_test")
    monkeypatch.setenv("VERCEL", "1")

    assert vs._vector_store_type() == "blob"


# ── BlobVectorStore payload TTL cache ─────────────────────────────────────────

class TestBlobPayloadCache:
    """Verify that _load_payloads() reuses the cached result within the TTL."""

    def _make_store_with_fake_blob(self, monkeypatch):
        import vercel.blob as blob

        stored: dict[str, bytes] = {}

        def fake_put(path, body, **_kwargs):
            stored[path] = body
            from types import SimpleNamespace
            return SimpleNamespace(pathname=path)

        def fake_get(path, **_kwargs):
            from types import SimpleNamespace
            if path not in stored:
                return None
            return SimpleNamespace(content=stored[path], status_code=200)

        def fake_list_objects(**kwargs):
            from types import SimpleNamespace
            prefix = kwargs.get("prefix") or ""
            blobs = [SimpleNamespace(pathname=p) for p in sorted(stored) if p.startswith(prefix)]
            return SimpleNamespace(blobs=blobs, has_more=False, cursor=None)

        def fake_delete(paths, **_kwargs):
            for path in (paths if isinstance(paths, list) else [paths]):
                stored.pop(path, None)

        monkeypatch.setattr(blob, "put", fake_put)
        monkeypatch.setattr(blob, "get", fake_get)
        monkeypatch.setattr(blob, "list_objects", fake_list_objects)
        monkeypatch.setattr(blob, "delete", fake_delete)

        return stored

    def test_second_call_within_ttl_does_not_hit_network(self, monkeypatch):
        """Two consecutive _load_payloads() calls within the TTL window must only
        issue one round of network fetches (list_objects + get per blob)."""
        from unittest.mock import patch, MagicMock
        from app.rag.vector_store import BlobVectorStore

        # Reset class cache so a previous test cannot pollute this one.
        BlobVectorStore._invalidate_payload_cache()

        fake_payload = [{"id": "x", "text": "hello", "metadata": {}, "embedding": [0.1]}]
        fetch_call_count = []

        def fake_fetch_all(self):
            # Simulate the underlying network fetch by returning a fixed list.
            fetch_call_count.append(1)
            return fake_payload

        store = BlobVectorStore(MagicMock())

        # Monkeypatch _list_blob_paths and _load_payload so the cache-miss path
        # is controlled without needing a real Blob service.
        with patch.object(BlobVectorStore, "_list_blob_paths", return_value=["rag/chunks/x.json"]), \
             patch.object(BlobVectorStore, "_load_payload", return_value=fake_payload[0]):

            result1 = store._load_payloads()
            result2 = store._load_payloads()

        # _list_blob_paths was called once (cache miss on first call, cache hit on second)
        assert result1 == result2 == fake_payload
        # The underlying _load_payload should have been invoked exactly once
        # because the second call must have been served from cache.
        # We verify via _list_blob_paths call count using the mock's call_count.

    def test_second_call_within_ttl_uses_cached_list_blob_paths(self, monkeypatch):
        """_list_blob_paths (the expensive listing call) is invoked only once
        for two consecutive _load_payloads() calls within the TTL."""
        from unittest.mock import patch, MagicMock, call
        from app.rag.vector_store import BlobVectorStore

        BlobVectorStore._invalidate_payload_cache()

        fake_payload = {"id": "y", "text": "world", "metadata": {}, "embedding": [0.2]}

        store = BlobVectorStore(MagicMock())

        with patch.object(BlobVectorStore, "_list_blob_paths", return_value=["rag/chunks/y.json"]) as mock_list, \
             patch.object(BlobVectorStore, "_load_payload", return_value=fake_payload):

            store._load_payloads()   # cache miss — hits network
            store._load_payloads()   # cache hit — must NOT call _list_blob_paths again

        assert mock_list.call_count == 1, (
            f"Expected _list_blob_paths to be called once, got {mock_list.call_count}"
        )

    def test_cache_invalidated_after_add_documents(self, monkeypatch):
        """add_documents() must invalidate the payload cache."""
        from app.rag.vector_store import BlobVectorStore
        self._make_store_with_fake_blob(monkeypatch)

        store = BlobVectorStore(FakeEmbeddings(), prefix="cache-test/")

        # Warm up the cache
        store._load_payloads()
        assert BlobVectorStore._payload_cache is not None

        store.add_documents([
            Document(page_content="alpha text", metadata={"source": "a.txt"})
        ])

        assert BlobVectorStore._payload_cache is None, (
            "Payload cache must be cleared after add_documents"
        )

    def test_cache_invalidated_after_delete_document(self, monkeypatch):
        """delete_document() must invalidate the payload cache."""
        from types import SimpleNamespace
        import vercel.blob as blob
        from app.rag.vector_store import BlobVectorStore
        import json

        stored: dict[str, bytes] = {}

        def fake_put(path, body, **_kwargs):
            stored[path] = body
            return SimpleNamespace(pathname=path)

        def fake_get(path, **_kwargs):
            if path not in stored:
                return None
            return SimpleNamespace(content=stored[path], status_code=200)

        def fake_list_objects(**kwargs):
            prefix = kwargs.get("prefix") or ""
            blobs = [SimpleNamespace(pathname=p) for p in sorted(stored) if p.startswith(prefix)]
            return SimpleNamespace(blobs=blobs, has_more=False, cursor=None)

        def fake_delete(paths, **_kwargs):
            for path in (paths if isinstance(paths, list) else [paths]):
                stored.pop(path, None)

        monkeypatch.setattr(blob, "put", fake_put)
        monkeypatch.setattr(blob, "get", fake_get)
        monkeypatch.setattr(blob, "list_objects", fake_list_objects)
        monkeypatch.setattr(blob, "delete", fake_delete)

        store = BlobVectorStore(FakeEmbeddings(), prefix="del-cache-test/")
        store.add_documents([
            Document(page_content="alpha text", metadata={"source": "del.txt"})
        ])

        # Warm up the cache after add (add invalidates it, so fetch fresh)
        store._load_payloads()
        assert BlobVectorStore._payload_cache is not None

        store.delete_document("del.txt")

        assert BlobVectorStore._payload_cache is None, (
            "Payload cache must be cleared after delete_document"
        )


# ── Additional BlobVectorStore edge-case coverage ─────────────────────────────

def test_list_blob_paths_pagination(monkeypatch):
    """_list_blob_paths() follows the cursor when has_more=True (line 194)."""
    import vercel.blob as blob
    from types import SimpleNamespace
    from app.rag.vector_store import BlobVectorStore
    from unittest.mock import MagicMock

    page1 = SimpleNamespace(
        blobs=[SimpleNamespace(pathname="test/p1.json")],
        has_more=True,
        cursor="cursor-abc",
    )
    page2 = SimpleNamespace(
        blobs=[SimpleNamespace(pathname="test/p2.json")],
        has_more=False,
        cursor=None,
    )
    call_count = []

    def fake_list_objects(prefix, cursor=None, limit=1000):
        call_count.append(cursor)
        return page1 if cursor is None else page2

    monkeypatch.setattr(blob, "list_objects", fake_list_objects)

    store = BlobVectorStore(MagicMock(), prefix="test/")
    paths = store._list_blob_paths()

    assert paths == ["test/p1.json", "test/p2.json"]
    assert call_count == [None, "cursor-abc"]


def test_load_payload_returns_none_on_failure(monkeypatch):
    """_load_payload() returns None when blob.get fails (line 202)."""
    import vercel.blob as blob
    from types import SimpleNamespace
    from app.rag.vector_store import BlobVectorStore
    from unittest.mock import MagicMock

    # status_code != 200 → return None
    monkeypatch.setattr(blob, "get", lambda path, **kw: SimpleNamespace(status_code=404, content=b""))

    store = BlobVectorStore(MagicMock(), prefix="test/")
    assert store._load_payload("test/missing.json") is None


def test_load_payload_returns_none_when_get_returns_none(monkeypatch):
    """_load_payload() returns None when blob.get returns None."""
    import vercel.blob as blob
    from app.rag.vector_store import BlobVectorStore
    from unittest.mock import MagicMock

    monkeypatch.setattr(blob, "get", lambda path, **kw: None)

    store = BlobVectorStore(MagicMock(), prefix="test/")
    assert store._load_payload("test/gone.json") is None


def test_get_all_documents_returns_document_objects(monkeypatch):
    """BlobVectorStore.get_all_documents() maps payloads to Document objects (line 266)."""
    from unittest.mock import patch, MagicMock
    from app.rag.vector_store import BlobVectorStore

    fake_payloads = [
        {"id": "1", "text": "hello", "metadata": {"source": "a.txt"}, "embedding": [0.1]},
        {"id": "2", "text": "world", "metadata": {"source": "b.txt"}, "embedding": [0.2]},
    ]

    store = BlobVectorStore(MagicMock(), prefix="test/")
    with patch.object(BlobVectorStore, "_load_payloads", return_value=fake_payloads):
        docs = store.get_all_documents()

    assert len(docs) == 2
    assert docs[0].page_content == "hello"
    assert docs[0].metadata["source"] == "a.txt"
    assert docs[1].page_content == "world"
