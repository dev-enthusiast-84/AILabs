import logging
import threading
import time as _time
import json
import math
import uuid
from contextvars import ContextVar
from functools import lru_cache
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config import get_settings
from app.runtime.settings_store import (
    get_effective_blob_read_write_token,
    get_effective_embedding_model,
    get_effective_pinecone_api_key,
    get_effective_retriever_fetch_k,
    get_effective_retriever_k,
    get_effective_retriever_use_mmr,
    get_effective_similarity_score_threshold,
    get_effective_vector_store_type,
    sync_effective_blob_token_to_env,
)

logger = logging.getLogger(__name__)

settings = get_settings()
_BLOB_CHUNK_PREFIX = "rag/chunks/"
_retrieval_metadata_filter: ContextVar[dict | None] = ContextVar("retrieval_metadata_filter", default=None)


def set_retrieval_metadata_filter(metadata_filter: dict | None) -> None:
    _retrieval_metadata_filter.set(metadata_filter)


def _metadata_matches_filter(metadata: dict, metadata_filter: dict | None) -> bool:
    if not metadata_filter:
        return True
    for key, expected in metadata_filter.items():
        actual = metadata.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$eq" in expected and actual != expected["$eq"]:
                return False
            continue
        if actual != expected:
            return False
    return True


def _apply_retrieval_filter(docs: list[Document]) -> list[Document]:
    metadata_filter = _retrieval_metadata_filter.get()
    if not metadata_filter:
        return docs
    return [doc for doc in docs if _metadata_matches_filter(doc.metadata or {}, metadata_filter)]


def _blob_token_configured() -> bool:
    token = get_effective_blob_read_write_token()
    if token:
        sync_effective_blob_token_to_env()
    return bool(token)


def _vector_store_type() -> str:
    """Resolve the active vector store type.

    Existing Vercel deployments may still have VECTOR_STORE_TYPE=memory from
    earlier scripts. When a Blob store is connected, prefer durable blob storage
    automatically to avoid serverless instance drift.
    """
    import os

    store_type = get_effective_vector_store_type()

    if store_type == "memory" and os.environ.get("VERCEL") and _blob_token_configured():
        return "blob"
    if store_type == "blob" and not _blob_token_configured():
        logger.warning("blob_vector_store_requested_without_token_falling_back_to_memory")
        return "memory"
    if store_type == "pinecone" and not get_effective_pinecone_api_key():
        logger.warning("pinecone_vector_store_requested_without_api_key_falling_back_to_memory")
        return "memory"
    return store_type

# ── BM25 document cache (P1) ──────────────────────────────────────────────────
# get_all_documents() fetches every chunk from ChromaDB — expensive at scale.
# Cache the result with a TTL; invalidate on upload/delete.
_doc_cache: list | None = None
_doc_cache_ts: float = 0.0
_doc_cache_lock = threading.Lock()
_DOC_CACHE_TTL = 60.0  # seconds


def invalidate_doc_cache() -> None:
    """Force the next get_all_documents() call to fetch fresh data."""
    global _doc_cache, _doc_cache_ts
    with _doc_cache_lock:
        _doc_cache = None
        _doc_cache_ts = 0.0


class _DynamicOpenAIEmbeddings(Embeddings):
    """Reads API key at call time so settings changes don't require a store reset.

    Caches the underlying OpenAIEmbeddings client (and its HTTP connection pool)
    keyed on the current API key. When the key changes the old client is evicted
    and a new one is built — avoiding the cost of reconstructing the HTTP client
    on every embed call.
    """

    _lock: threading.Lock = threading.Lock()
    _cache: dict[tuple[str, str], "OpenAIEmbeddings"] = {}  # type: ignore[name-defined]

    def _get_client(self):
        from langchain_openai import OpenAIEmbeddings
        from app.runtime.settings_store import get_effective_api_key
        key = get_effective_api_key() or ""
        model = get_effective_embedding_model()
        cache_key = (key, model)
        with self._lock:
            if cache_key not in self._cache:
                self._cache.clear()  # evict stale client when key changes
                self._cache[cache_key] = OpenAIEmbeddings(
                    model=model,
                    openai_api_key=key or None,
                )
            return self._cache[cache_key]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._get_client().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._get_client().embed_query(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class BlobVectorStore:
    """Small durable vector store backed by Vercel Blob.

    Each chunk is stored as a JSON blob containing text, metadata, and its
    embedding. This keeps Vercel deployments consistent across cold starts and
    function instances without requiring a local writable filesystem.

    Payload cache (P1 performance):
        _load_payloads() fetches every blob object on each call.  With many
        chunks this becomes O(n) network round-trips per query.  The class-level
        cache stores the full payload list with a TTL so that multiple reads
        within the same window reuse the already-fetched result.  The cache is
        invalidated whenever add_documents or delete_document mutates the store.
    """

    # ── class-level payload cache ─────────────────────────────────────────────
    # All instances share the same Blob namespace so the cache is class-level.
    _payload_cache: list | None = None
    _payload_cache_ts: float = 0.0
    _payload_cache_lock: threading.Lock = threading.Lock()
    _PAYLOAD_CACHE_TTL: float = 30.0  # seconds

    def __init__(self, embedding: Embeddings, prefix: str = _BLOB_CHUNK_PREFIX):
        self.embedding = embedding
        self.prefix = prefix

    @classmethod
    def _invalidate_payload_cache(cls) -> None:
        """Force the next _load_payloads() call to fetch fresh data from Blob."""
        with cls._payload_cache_lock:
            cls._payload_cache = None
            cls._payload_cache_ts = 0.0

    def _chunk_path(self, chunk_id: str) -> str:
        return f"{self.prefix}{chunk_id}.json"

    def _list_blob_paths(self) -> list[str]:
        sync_effective_blob_token_to_env()
        from vercel.blob import list_objects

        paths: list[str] = []
        cursor: str | None = None
        while True:
            result = list_objects(prefix=self.prefix, cursor=cursor, limit=1000)
            paths.extend(blob.pathname for blob in result.blobs)
            if not result.has_more:
                return paths
            cursor = result.cursor

    def _load_payload(self, pathname: str) -> dict | None:
        sync_effective_blob_token_to_env()
        from vercel.blob import get

        result = get(pathname, access="private")
        if result is None or result.status_code != 200:
            return None
        return json.loads(result.content.decode("utf-8"))

    def _load_payloads(self) -> list[dict]:
        """Return all blob payloads, using the class-level TTL cache when fresh."""
        with BlobVectorStore._payload_cache_lock:
            now = _time.time()
            if (
                BlobVectorStore._payload_cache is not None
                and (now - BlobVectorStore._payload_cache_ts) < BlobVectorStore._PAYLOAD_CACHE_TTL
            ):
                return BlobVectorStore._payload_cache

        payloads: list[dict] = []
        for path in self._list_blob_paths():
            payload = self._load_payload(path)
            if payload:
                payloads.append(payload)

        with BlobVectorStore._payload_cache_lock:
            BlobVectorStore._payload_cache = payloads
            BlobVectorStore._payload_cache_ts = _time.time()
        return payloads

    def add_documents(self, docs: list[Document]) -> list[str]:
        sync_effective_blob_token_to_env()
        from vercel.blob import put

        ids = [str(uuid.uuid4()) for _ in docs]
        vectors = self.embedding.embed_documents([doc.page_content for doc in docs])
        for doc_id, doc, vector in zip(ids, docs, vectors):
            payload = {
                "id": doc_id,
                "text": doc.page_content,
                "metadata": doc.metadata,
                "embedding": vector,
            }
            put(
                self._chunk_path(doc_id),
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                access="private",
                content_type="application/json",
                overwrite=True,
            )
        BlobVectorStore._invalidate_payload_cache()
        invalidate_doc_cache()
        return ids

    def has_documents(self) -> bool:
        return bool(self._list_blob_paths())

    def list_document_sources(self) -> list[str]:
        return _collect_unique_sources(
            (payload.get("metadata") or {}).get("source", "unknown")
            for payload in self._load_payloads()
        )

    def document_exists(self, source: str) -> bool:
        return any(
            (payload.get("metadata") or {}).get("source") == source
            for payload in self._load_payloads()
        )

    def get_all_documents(self) -> list[Document]:
        return [
            Document(
                page_content=payload.get("text", ""),
                metadata=payload.get("metadata") or {},
            )
            for payload in self._load_payloads()
        ]

    def get_document_chunks(self, source: str) -> list[str]:
        chunks: list[tuple[int, str]] = []
        for payload in self._load_payloads():
            meta = payload.get("metadata") or {}
            if meta.get("source") == source:
                text = meta.get("raw_chunk") or payload.get("text", "")
                chunks.append((meta.get("chunk_index", 0), text))
        chunks.sort(key=lambda x: x[0])
        return [text for _, text in chunks]

    def delete_document(self, source: str) -> int:
        sync_effective_blob_token_to_env()
        from vercel.blob import delete

        paths: list[str] = []
        for path in self._list_blob_paths():
            payload = self._load_payload(path)
            if payload and (payload.get("metadata") or {}).get("source") == source:
                paths.append(path)
        if paths:
            delete(paths)
        BlobVectorStore._invalidate_payload_cache()
        invalidate_doc_cache()
        return len(paths)

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4) -> list[tuple[Document, float]]:
        query_vector = self.embedding.embed_query(query)
        scored: list[tuple[Document, float]] = []
        for payload in self._load_payloads():
            vector = payload.get("embedding") or []
            score = _cosine_similarity(query_vector, vector)
            scored.append((
                Document(
                    page_content=payload.get("text", ""),
                    metadata=payload.get("metadata") or {},
                ),
                score,
            ))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def similarity_search(self, query: str, k: int = 4) -> list[Document]:
        return [doc for doc, _score in self.similarity_search_with_relevance_scores(query, k=k)]


@lru_cache(maxsize=1)
def get_vector_store():
    embeddings = _DynamicOpenAIEmbeddings()
    store_type = _vector_store_type()
    if store_type == "chroma":
        from langchain_chroma import Chroma
        return Chroma(
            embedding_function=embeddings,
            collection_name="rag_documents",
            persist_directory=settings.chroma_persist_dir,
        )
    if store_type == "blob":
        return BlobVectorStore(embedding=embeddings)
    if store_type == "pinecone":
        from app.rag.pinecone_store import _PineconeStore
        return _PineconeStore(embedding=embeddings)
    # Ephemeral in-memory store — used on Vercel and in tests.
    # Data is lost when the process restarts.
    from langchain_core.vectorstores import InMemoryVectorStore
    return InMemoryVectorStore(embedding=embeddings)


def _is_chroma_schema_corruption(exc: Exception) -> bool:
    """Return True when *exc* is a ChromaDB metadata-segment schema mismatch.

    This happens after a ChromaDB major-version upgrade changes the SQLite
    column type from BLOB to INTEGER (or vice-versa).  The symptom is an
    InternalError with the text "mismatched types" / "BLOB" in the message.
    """
    msg = str(exc).lower()
    return (
        "mismatched types" in msg
        or ("blob" in msg and "sql type" in msg)
        or "segment reader" in msg
    )


def _try_recover_chroma_schema() -> None:
    """Delete the ChromaDB persist directory to recover from schema corruption.

    This is destructive — all previously indexed documents are removed.
    A WARNING is emitted so operators can re-upload after recovery.
    """
    import shutil
    persist_dir = settings.chroma_persist_dir
    if persist_dir:
        try:
            shutil.rmtree(persist_dir, ignore_errors=True)
            logger.warning(
                "chroma_schema_corruption_auto_reset",
                persist_dir=persist_dir,
                detail="ChromaDB persist directory cleared after schema mismatch. "
                       "All previously indexed documents have been removed — please re-upload.",
            )
        except Exception as e:
            logger.error("chroma_schema_corruption_reset_failed", error=str(e))
    get_vector_store.cache_clear()


def add_documents(docs: list[Document]) -> list[str]:
    store = get_vector_store()
    try:
        return store.add_documents(docs)
    except Exception as exc:
        # Auto-recover from ChromaDB metadata-segment schema corruption that
        # occurs after a ChromaDB major-version upgrade.  The corrupt persist
        # directory is deleted and the operation is retried with a fresh store.
        if _vector_store_type() == "chroma" and _is_chroma_schema_corruption(exc):
            _try_recover_chroma_schema()
            store = get_vector_store()
            return store.add_documents(docs)
        raise


def has_documents() -> bool:
    """Return True if at least one document chunk is indexed.

    Uses a cheap count/peek rather than fetching all metadata, so it is safe
    to call on every request even with large collections.
    """
    store = get_vector_store()
    store_type = _vector_store_type()
    if store_type == "chroma":
        return store._collection.count() > 0
    if store_type in ("blob", "pinecone"):
        return store.has_documents()
    return bool(store.store)


def similarity_search(query: str, k: int | None = None) -> list[Document]:
    """Return the most relevant document chunks for *query*.

    Retrieval strategy (controlled via Settings / env vars):

    1. **MMR** (``retriever_use_mmr=True``): calls
       ``max_marginal_relevance_search`` on Chroma to balance relevance with
       diversity.  InMemoryVectorStore does not support MMR — a warning is
       logged and plain similarity search is used as a fallback.

    2. **Score threshold** (``similarity_score_threshold > 0.0``): calls
       ``similarity_search_with_relevance_scores`` and discards any chunk
       whose cosine-similarity score is below the threshold.

    3. **Default**: plain ``similarity_search`` — existing behaviour,
       unchanged when both features are disabled.

    OWASP A04 — Insecure Design: threshold defaults to 0.0 so that
    disabling the filter (no env var set) keeps existing behaviour.
    """
    from langchain_core.vectorstores import InMemoryVectorStore

    effective_k = k or get_effective_retriever_k()
    store = get_vector_store()

    # ── MMR path ──────────────────────────────────────────────────────────────
    if get_effective_retriever_use_mmr():
        if isinstance(store, InMemoryVectorStore) or _vector_store_type() == "blob":
            logger.warning(
                "retriever_use_mmr=True but this vector store does not support "
                "MMR; falling back to plain similarity_search."
            )
        else:
            return _apply_retrieval_filter(store.max_marginal_relevance_search(
                query,
                k=effective_k,
                fetch_k=get_effective_retriever_fetch_k(),
            ))

    # ── Score-threshold path ───────────────────────────────────────────────────
    threshold = get_effective_similarity_score_threshold()
    if threshold > 0.0:
        scored: list[tuple[Document, float]] = store.similarity_search_with_relevance_scores(
            query, k=effective_k
        )
        before = len(scored)
        docs = [doc for doc, score in scored if score >= threshold]
        filtered = before - len(docs)
        if filtered:
            logger.info(
                "similarity_search: filtered %d/%d chunks below threshold %.3f",
                filtered,
                before,
                threshold,
            )
        return _apply_retrieval_filter(docs)

    # ── Default path ──────────────────────────────────────────────────────────
    return _apply_retrieval_filter(store.similarity_search(query, k=effective_k))


def _collect_unique_sources(source_iter) -> list[str]:
    """Deduplicate sources while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for src in source_iter:
        if src not in seen:
            seen.add(src)
            result.append(src)
    return result


def list_document_sources() -> list[str]:
    store = get_vector_store()
    store_type = _vector_store_type()
    if store_type == "chroma":
        results = store._collection.get(include=["metadatas"])
        return _collect_unique_sources(
            meta.get("source", "unknown") for meta in (results.get("metadatas") or [])
        )
    if store_type in ("blob", "pinecone"):
        return store.list_document_sources()
    return _collect_unique_sources(
        v.get("metadata", {}).get("source", "unknown") for v in store.store.values()
    )


def document_exists(source: str) -> bool:
    """Return True if at least one chunk for *source* is already indexed."""
    store = get_vector_store()
    store_type = _vector_store_type()
    if store_type == "chroma":
        results = store._collection.get(where={"source": source}, include=[], limit=1)
        return len(results.get("ids") or []) > 0
    if store_type in ("blob", "pinecone"):
        return store.document_exists(source)
    return any(
        v.get("metadata", {}).get("source") == source
        for v in store.store.values()
    )


def _fetch_all_documents_from_db() -> list[Document]:
    """Unconditionally fetch all stored chunks from the backing store."""
    store = get_vector_store()
    store_type = _vector_store_type()
    if store_type == "chroma":
        collection = store._collection
        results = collection.get(include=["documents", "metadatas"])
        return [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(
                results.get("documents") or [],
                results.get("metadatas") or [],
            )
        ]
    if store_type in ("blob", "pinecone"):
        return store.get_all_documents()
    # InMemoryVectorStore
    return [
        Document(page_content=v.get("text", ""), metadata=v.get("metadata", {}))
        for v in store.store.values()
    ]


def get_all_documents() -> list[Document]:
    """Return all stored chunks as Document objects.

    Used by the BM25 hybrid retriever to build an in-memory lexical index over
    the full corpus at query time. Only called when RETRIEVER_HYBRID_BM25=true.

    Results are cached for up to _DOC_CACHE_TTL seconds and invalidated on
    upload/delete to avoid rebuilding the BM25 index from scratch every query.
    """
    global _doc_cache, _doc_cache_ts
    with _doc_cache_lock:
        now = _time.monotonic()
        if _doc_cache is not None and (now - _doc_cache_ts) < _DOC_CACHE_TTL:
            return _apply_retrieval_filter(_doc_cache)
        fresh = _fetch_all_documents_from_db()
        _doc_cache = fresh
        _doc_cache_ts = now
        return _apply_retrieval_filter(_doc_cache)


def get_document_chunks(source: str) -> list[str]:
    """Return all stored chunk texts for a source document, sorted by chunk_index."""
    store = get_vector_store()
    store_type = _vector_store_type()
    if store_type == "chroma":
        collection = store._collection
        results = collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )
        pairs = list(zip(
            results.get("documents") or [],
            results.get("metadatas") or [],
        ))
        pairs.sort(key=lambda p: p[1].get("chunk_index", 0))
        return [meta.get("raw_chunk", text) for text, meta in pairs]
    if store_type in ("blob", "pinecone"):
        return store.get_document_chunks(source)
    # InMemoryVectorStore
    chunks: list[tuple[int, str]] = []
    for v in store.store.values():
        meta = v.get("metadata", {})
        if meta.get("source") == source:
            text = meta.get("raw_chunk") or v.get("text", "")
            chunks.append((meta.get("chunk_index", 0), text))
    chunks.sort(key=lambda x: x[0])
    return [text for _, text in chunks]


def _stitch_chunks(chunks: list[str], overlap: int) -> str:
    """Reconstruct full document text from overlapping chunks.

    RecursiveCharacterTextSplitter stores ~overlap chars of each chunk at the
    start of the next chunk.  This function scans for the actual shared suffix/
    prefix and removes the repeated portion so the viewer shows continuous text.
    """
    if not chunks:
        return ""
    result = chunks[0]
    search_window = max(overlap * 2, 50)
    for chunk in chunks[1:]:
        scan = min(search_window, len(result), len(chunk))
        joined = False
        for trim in range(scan, 0, -1):
            if result.endswith(chunk[:trim]):
                result += chunk[trim:]
                joined = True
                break
        if not joined:
            result += "\n" + chunk
    return result


def get_document_content(source: str) -> str:
    """Return the full reconstructed text for a source document.

    Retrieves stored chunks in order and stitches them using _stitch_chunks to
    eliminate the chunk_overlap duplication introduced during indexing.
    """
    chunks = get_document_chunks(source)
    return _stitch_chunks(chunks, settings.chunk_overlap)


def delete_document(source: str) -> int:
    store = get_vector_store()
    store_type = _vector_store_type()
    if store_type == "chroma":
        collection = store._collection
        results = collection.get(where={"source": source}, include=["metadatas"])
        ids = results.get("ids") or []
        if ids:
            collection.delete(ids=ids)
        return len(ids)
    if store_type in ("blob", "pinecone"):
        return store.delete_document(source)
    # InMemoryVectorStore: filter by source metadata
    ids_to_delete = [
        id_ for id_, v in store.store.items()
        if v.get("metadata", {}).get("source") == source
    ]
    if ids_to_delete:
        store.delete(ids_to_delete)
    return len(ids_to_delete)
