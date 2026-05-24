"""Unit tests for the _PineconeStore class and Pinecone vector-store type routing."""
from types import SimpleNamespace

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.pinecone_store import _PineconeStore


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] if "alpha" in t else [0.0, 1.0] for t in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if "alpha" in text else [0.0, 1.0]


class FakeIndex:
    def __init__(self):
        self.vectors: dict[str, SimpleNamespace] = {}
        self.list_returns_empty = False
        self.list_called = 0
        self.fetch_called = 0
        self.query_called = 0

    def list(self, namespace=None):
        self.list_called += 1
        if self.list_returns_empty:
            yield []
            return
        yield list(self.vectors.keys())

    def fetch(self, ids, namespace=None):
        self.fetch_called += 1
        return SimpleNamespace(
            vectors={id_: self.vectors[id_] for id_ in ids if id_ in self.vectors}
        )

    def query(self, vector, filter=None, top_k=4, include_metadata=True,
              include_values=False, namespace=None, **_kwargs):
        self.query_called += 1
        source_eq = (filter or {}).get("source", {}).get("$eq")
        if source_eq is not None:
            pool = {
                id_: v for id_, v in self.vectors.items()
                if (v.metadata or {}).get("source") == source_eq
            }
        else:
            pool = dict(self.vectors)
        matches = []
        for id_, v in list(pool.items())[:top_k]:
            match = SimpleNamespace(
                id=id_,
                metadata=v.metadata if include_metadata else {},
                score=1.0,
            )
            if include_values:
                match.values = v.values
            matches.append(match)
        return SimpleNamespace(matches=matches)

    def delete(self, ids, namespace=None):
        for id_ in ids:
            self.vectors.pop(id_, None)

    def upsert(self, vectors, namespace=None):
        for item in vectors:
            id_ = item["id"]
            self.vectors[id_] = SimpleNamespace(
                id=id_,
                metadata=item.get("metadata", {}),
                values=item.get("values", []),
            )

    def describe_index_stats(self):
        return SimpleNamespace(
            total_vector_count=len(self.vectors),
            namespaces={"agenticai-rag-poc": SimpleNamespace(vector_count=len(self.vectors))},
        )


def _make_fake_store() -> tuple[_PineconeStore, FakeIndex]:
    """Build a _PineconeStore with a pre-injected FakeIndex, bypassing all SDK calls."""
    from app.runtime.settings_store import get_effective_pinecone_api_key, get_effective_pinecone_index_name
    fake_index = FakeIndex()
    store = _PineconeStore(FakeEmbeddings())
    store._pc_index = fake_index
    store._pc_index_key = (get_effective_pinecone_api_key(), get_effective_pinecone_index_name())
    return store, fake_index


# ---------------------------------------------------------------------------
# has_documents
# ---------------------------------------------------------------------------

def test_pinecone_store_has_documents_false_when_empty():
    store, _ = _make_fake_store()
    assert store.has_documents() is False


def test_pinecone_store_has_documents_true():
    store, fake_index = _make_fake_store()
    fake_index.vectors["v1"] = SimpleNamespace(id="v1", metadata={"source": "x.txt"}, values=[])
    fake_index.vectors["v2"] = SimpleNamespace(id="v2", metadata={"source": "y.txt"}, values=[])
    assert store.has_documents() is True


# ---------------------------------------------------------------------------
# Roundtrip: add_documents → list / exists / chunks / delete
# ---------------------------------------------------------------------------

def test_pinecone_store_roundtrip():
    store, _ = _make_fake_store()

    docs = [
        Document(
            page_content="[Document: a.txt]\nalpha chunk",
            metadata={"source": "a.txt", "chunk_index": 0, "raw_chunk": "alpha chunk"},
        ),
        Document(
            page_content="[Document: b.txt]\nbeta chunk",
            metadata={"source": "b.txt", "chunk_index": 0, "raw_chunk": "beta chunk"},
        ),
    ]
    ids = store.add_documents(docs)
    assert len(ids) == 2

    assert store.has_documents() is True
    assert sorted(store.list_document_sources()) == ["a.txt", "b.txt"]
    assert store.document_exists("a.txt") is True
    assert store.document_exists("c.txt") is False
    assert store.get_document_chunks("a.txt") == ["alpha chunk"]

    assert store.delete_document("a.txt") == 1
    assert store.document_exists("a.txt") is False


def test_pinecone_store_list_uses_metadata_query_when_id_list_lags():
    store, fake_index = _make_fake_store()
    fake_index.list_returns_empty = True
    fake_index.vectors["v1"] = SimpleNamespace(
        id="v1",
        metadata={"text": "alpha content", "source": "a.txt"},
        values=[1.0, 0.0],
    )
    fake_index.vectors["v2"] = SimpleNamespace(
        id="v2",
        metadata={"text": "alpha chunk 2", "source": "a.txt"},
        values=[1.0, 0.0],
    )
    fake_index.vectors["v3"] = SimpleNamespace(
        id="v3",
        metadata={"text": "beta content", "source": "b.txt"},
        values=[0.0, 1.0],
    )

    assert store.document_exists("a.txt") is True
    assert store.list_document_sources() == ["a.txt", "b.txt"]
    assert [doc.metadata["source"] for doc in store.get_all_documents()] == [
        "a.txt",
        "a.txt",
        "b.txt",
    ]
    assert fake_index.list_called == 0
    assert fake_index.fetch_called == 0
    assert fake_index.query_called >= 3


# ---------------------------------------------------------------------------
# similarity_search reconstructs Documents from Pinecone matches
# ---------------------------------------------------------------------------

def test_pinecone_store_similarity_search_returns_documents():
    store, fake_index = _make_fake_store()
    fake_index.vectors["id-1"] = SimpleNamespace(
        id="id-1",
        metadata={"text": "alpha content", "source": "a.txt"},
        values=[1.0, 0.0],
    )
    results = store.similarity_search("alpha query", k=1)
    assert len(results) == 1
    assert results[0].page_content == "alpha content"
    assert results[0].metadata["source"] == "a.txt"
    # "text" key must be stripped from metadata — it becomes page_content
    assert "text" not in results[0].metadata


def test_pinecone_store_similarity_search_with_scores():
    store, fake_index = _make_fake_store()
    fake_index.vectors["id-1"] = SimpleNamespace(
        id="id-1",
        metadata={"text": "alpha content", "source": "a.txt"},
        values=[1.0, 0.0],
    )
    results = store.similarity_search_with_relevance_scores("alpha query", k=1)
    assert len(results) == 1
    doc, score = results[0]
    assert isinstance(doc, Document)
    assert isinstance(score, float)


# ---------------------------------------------------------------------------
# max_marginal_relevance_search selects up to k diverse documents
# ---------------------------------------------------------------------------

def test_pinecone_store_mmr_returns_documents():
    store, fake_index = _make_fake_store()
    # Three vectors: two similar (alpha direction), one orthogonal (beta)
    fake_index.vectors["id-0"] = SimpleNamespace(
        id="id-0", metadata={"text": "alpha doc 0", "source": "a0.txt"}, values=[1.0, 0.0]
    )
    fake_index.vectors["id-1"] = SimpleNamespace(
        id="id-1", metadata={"text": "alpha doc 1", "source": "a1.txt"}, values=[0.99, 0.01]
    )
    fake_index.vectors["id-2"] = SimpleNamespace(
        id="id-2", metadata={"text": "beta doc", "source": "b.txt"}, values=[0.0, 1.0]
    )
    results = store.max_marginal_relevance_search("alpha query", k=2, fetch_k=3)
    assert len(results) == 2
    assert all(isinstance(r, Document) for r in results)
    assert "text" not in results[0].metadata


# ---------------------------------------------------------------------------
# vector_store_type routing
# ---------------------------------------------------------------------------

def test_pinecone_fallback_to_memory_without_api_key(monkeypatch):
    import app.rag.vector_store as vs
    monkeypatch.setattr(vs, "get_effective_vector_store_type", lambda: "pinecone")
    monkeypatch.setattr(vs, "get_effective_pinecone_api_key", lambda: "")
    assert vs._vector_store_type() == "memory"


def test_pinecone_type_returned_when_configured(monkeypatch):
    import app.rag.vector_store as vs
    monkeypatch.setattr(vs, "get_effective_vector_store_type", lambda: "pinecone")
    monkeypatch.setattr(vs, "get_effective_pinecone_api_key", lambda: "pc-test-key")
    assert vs._vector_store_type() == "pinecone"


# ---------------------------------------------------------------------------
# _get_index auto-creates the index when it does not exist
# ---------------------------------------------------------------------------

def test_pinecone_store_index_auto_created(monkeypatch):
    import app.rag.pinecone_store as ps
    import pinecone

    create_calls: list[dict] = []

    class FakePc:
        def list_indexes(self):
            return []

        def create_index(self, **kwargs):
            create_calls.append(kwargs)

        def describe_index(self, name):
            return SimpleNamespace(status={"ready": True})

        def Index(self, name):
            return FakeIndex()

    monkeypatch.setattr(ps, "get_effective_pinecone_api_key", lambda: "pc-fake-key")
    monkeypatch.setattr(ps, "get_effective_pinecone_index_name", lambda: "agenticai-rag-poc-documents")
    monkeypatch.setattr(ps, "get_effective_pinecone_cloud", lambda: "aws")
    monkeypatch.setattr(ps, "get_effective_pinecone_region", lambda: "us-east-1")
    monkeypatch.setattr(pinecone, "Pinecone", lambda api_key: FakePc())
    monkeypatch.setattr(
        pinecone, "ServerlessSpec",
        lambda cloud, region: SimpleNamespace(cloud=cloud, region=region),
    )

    store = _PineconeStore(FakeEmbeddings())
    index = store._get_index()

    assert len(create_calls) == 1
    assert create_calls[0]["name"] == "agenticai-rag-poc-documents"
    assert index is not None


def test_pinecone_store_index_creation_timeout(monkeypatch):
    """_get_index raises RuntimeError when the index is not ready within 60 s.

    time.time() is patched to float("inf") so that:
      - _deadline = inf + 60 = inf
      - first loop check: inf >= inf → True → raises immediately (no real wait)
    time.sleep is patched to a no-op as a defensive guard against real sleeps.
    """
    import time
    import app.rag.pinecone_store as ps
    import pinecone

    class FakePcNeverReady:
        def list_indexes(self):
            return []

        def create_index(self, **kwargs):
            pass

        def describe_index(self, name):
            return SimpleNamespace(status={"ready": False})

        def Index(self, name):
            return FakeIndex()

    monkeypatch.setattr(ps, "get_effective_pinecone_api_key", lambda: "pc-fake-key")
    monkeypatch.setattr(ps, "get_effective_pinecone_index_name", lambda: "agenticai-rag-poc-documents")
    monkeypatch.setattr(ps, "get_effective_pinecone_cloud", lambda: "aws")
    monkeypatch.setattr(ps, "get_effective_pinecone_region", lambda: "us-east-1")
    monkeypatch.setattr(pinecone, "Pinecone", lambda api_key: FakePcNeverReady())
    monkeypatch.setattr(
        pinecone, "ServerlessSpec",
        lambda cloud, region: SimpleNamespace(cloud=cloud, region=region),
    )
    # inf >= inf is True, so the first iteration raises without any real wait.
    monkeypatch.setattr(time, "time", lambda: float("inf"))
    # Defensive: prevent any real sleep if the loop order ever changes.
    monkeypatch.setattr(time, "sleep", lambda _: None)

    store = _PineconeStore(FakeEmbeddings())
    import pytest
    with pytest.raises(RuntimeError, match="not ready after 60 s"):
        store._get_index()
