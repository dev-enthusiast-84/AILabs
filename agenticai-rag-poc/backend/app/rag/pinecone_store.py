"""Pinecone-backed vector store for persistent, scalable document indexing."""

from __future__ import annotations

import logging
import math
import time
import uuid

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config import get_settings
from app.settings_store import (
    get_effective_embedding_model,
    get_effective_pinecone_api_key,
    get_effective_pinecone_cloud,
    get_effective_pinecone_index_name,
    get_effective_pinecone_namespace,
    get_effective_pinecone_region,
)

logger = logging.getLogger(__name__)

settings = get_settings()

_EMBEDDING_DIM: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
_DEFAULT_DIM = 1536
_UPSERT_BATCH = 100  # Pinecone recommends ≤100 vectors per upsert call
_QUERY_TOP_K = 10_000


def _dim() -> int:
    return _EMBEDDING_DIM.get(get_effective_embedding_model(), _DEFAULT_DIM)


def _zero_vector() -> list[float]:
    # Pinecone requires a real vector for metadata-only queries; a zero vector
    # satisfies the API contract without biasing which vectors are returned when
    # the query is used purely as a metadata filter (document_exists, get_chunks).
    return [0.0] * _dim()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class _PineconeStore:
    """Managed serverless vector store backed by Pinecone (raw SDK, no LangChain wrapper)."""

    def __init__(self, embedding: Embeddings) -> None:
        self.embedding = embedding
        self._pc_index = None
        self._pc_index_key: tuple[str, str] | None = None

    def _get_index(self):
        index_key = (get_effective_pinecone_api_key(), get_effective_pinecone_index_name())
        if self._pc_index is not None and self._pc_index_key == index_key:
            return self._pc_index

        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=get_effective_pinecone_api_key())
        name = get_effective_pinecone_index_name()
        existing = [idx.name for idx in pc.list_indexes()]

        if name not in existing:
            logger.info("pinecone.creating_index name=%s dimension=%d", name, _dim())
            pc.create_index(
                name=name,
                dimension=_dim(),
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=get_effective_pinecone_cloud(),
                    region=get_effective_pinecone_region(),
                ),
            )
            while not pc.describe_index(name).status["ready"]:
                time.sleep(1)
            logger.info("pinecone.index_ready name=%s", name)
        else:
            logger.info("pinecone.index_exists name=%s", name)

        self._pc_index = pc.Index(name)
        self._pc_index_key = index_key
        return self._pc_index

    def _ns(self) -> str | None:
        return get_effective_pinecone_namespace() or None

    def _query_metadata_matches(self, filter: dict | None = None, top_k: int = _QUERY_TOP_K):
        """Fetch vectors by metadata query.

        Pinecone's ID listing path can lag behind query visibility in serverless
        deployments. The upload duplicate check, chunk retrieval, and delete
        paths already use metadata queries, so listing should use the same
        source of truth to avoid "duplicate but not listed" document states.
        """
        resp = self._get_index().query(
            vector=_zero_vector(),
            filter=filter,
            top_k=top_k,
            include_metadata=True,
            include_values=False,
            namespace=self._ns(),
        )
        return list(resp.matches or [])

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_documents(self, docs: list[Document]) -> list[str]:
        index = self._get_index()
        ids = [str(uuid.uuid4()) for _ in docs]
        vectors = self.embedding.embed_documents([doc.page_content for doc in docs])
        to_upsert = [
            {
                "id": doc_id,
                "values": vec,
                "metadata": {"text": doc.page_content, **doc.metadata},
            }
            for doc_id, doc, vec in zip(ids, docs, vectors)
        ]
        for i in range(0, len(to_upsert), _UPSERT_BATCH):
            index.upsert(vectors=to_upsert[i : i + _UPSERT_BATCH], namespace=self._ns())
        return ids

    # ── Metadata operations ───────────────────────────────────────────────────

    def has_documents(self) -> bool:
        stats = self._get_index().describe_index_stats()
        ns = get_effective_pinecone_namespace()
        if ns:
            ns_stats = stats.namespaces.get(ns)
            return ns_stats is not None and ns_stats.vector_count > 0
        return stats.total_vector_count > 0

    def list_document_sources(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for match in self._query_metadata_matches():
            src = (match.metadata or {}).get("source", "unknown")
            if src not in seen:
                seen.add(src)
                result.append(src)
        return result

    def document_exists(self, source: str) -> bool:
        matches = self._query_metadata_matches(
            filter={"source": {"$eq": source}},
            top_k=1,
        )
        return len(matches) > 0

    def get_all_documents(self) -> list[Document]:
        docs: list[Document] = []
        for match in self._query_metadata_matches():
            meta = dict(match.metadata or {})
            page_content = meta.pop("text", "")
            docs.append(Document(page_content=page_content, metadata=meta))
        return docs

    def get_document_chunks(self, source: str) -> list[str]:
        matches = self._query_metadata_matches(
            filter={"source": {"$eq": source}},
            top_k=_QUERY_TOP_K,
        )
        chunks: list[tuple[int, str]] = []
        for match in matches:
            meta = match.metadata or {}
            text = meta.get("raw_chunk") or meta.get("text", "")
            chunks.append((meta.get("chunk_index", 0), text))
        chunks.sort(key=lambda x: x[0])
        return [t for _, t in chunks]

    def delete_document(self, source: str) -> int:
        resp = self._get_index().query(
            vector=_zero_vector(),
            filter={"source": {"$eq": source}},
            top_k=_QUERY_TOP_K,
            include_metadata=False,
            namespace=self._ns(),
        )
        ids = [m.id for m in resp.matches]
        if ids:
            self._get_index().delete(ids=ids, namespace=self._ns())
        return len(ids)

    # ── Similarity search ─────────────────────────────────────────────────────

    def similarity_search_with_relevance_scores(
        self, query: str, k: int = 4
    ) -> list[tuple[Document, float]]:
        query_vec = self.embedding.embed_query(query)
        resp = self._get_index().query(
            vector=query_vec,
            top_k=k,
            include_metadata=True,
            include_values=False,
            namespace=self._ns(),
        )
        results: list[tuple[Document, float]] = []
        for match in resp.matches:
            meta = dict(match.metadata or {})
            page_content = meta.pop("text", "")
            results.append((Document(page_content=page_content, metadata=meta), match.score or 0.0))
        return results

    def similarity_search(self, query: str, k: int = 4) -> list[Document]:
        return [doc for doc, _ in self.similarity_search_with_relevance_scores(query, k=k)]

    def max_marginal_relevance_search(
        self, query: str, k: int = 4, fetch_k: int = 20
    ) -> list[Document]:
        query_vec = self.embedding.embed_query(query)
        resp = self._get_index().query(
            vector=query_vec,
            top_k=fetch_k,
            include_metadata=True,
            include_values=True,  # vectors needed for MMR cosine scoring
            namespace=self._ns(),
        )
        if not resp.matches:
            return []
        candidates = [
            (dict(m.metadata or {}), m.values or [])
            for m in resp.matches
        ]
        selected: list[Document] = []
        selected_vecs: list[list[float]] = []
        remaining = list(range(len(candidates)))
        while len(selected) < k and remaining:
            if not selected_vecs:
                best_i = remaining[0]
            else:
                best_score, best_i = float("-inf"), remaining[0]
                for i in remaining:
                    _, vec = candidates[i]
                    rel = _cosine(query_vec, vec)
                    red = max(_cosine(vec, sv) for sv in selected_vecs)
                    score = rel - red
                    if score > best_score:
                        best_score, best_i = score, i
            remaining.remove(best_i)
            meta, vec = candidates[best_i]
            page_content = meta.pop("text", "")
            selected.append(Document(page_content=page_content, metadata=meta))
            selected_vecs.append(vec)
        return selected
