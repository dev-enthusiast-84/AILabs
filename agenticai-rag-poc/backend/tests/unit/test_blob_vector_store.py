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
