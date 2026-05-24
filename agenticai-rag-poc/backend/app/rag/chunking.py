from langchain_core.documents import Document

from app.config import get_settings
from app.runtime.settings_store import (
    get_effective_embedding_model,
    get_effective_chunker_type,
    get_effective_chunk_size,
    get_effective_chunk_overlap,
)


def chunk_text(text: str, metadata: dict) -> list[Document]:
    """Split text into chunks using the runtime-effective chunker strategy."""
    chunker_type = get_effective_chunker_type()
    if chunker_type == "semantic":
        return _semantic_chunk(text, metadata)
    return _recursive_chunk(text, metadata)


def _recursive_chunk(text: str, metadata: dict) -> list[Document]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=get_effective_chunk_size(),
        chunk_overlap=get_effective_chunk_overlap(),
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_text(text)
    source = metadata.get("source", "")
    # Contextual header prepended to page_content so the embedding encodes document
    # provenance alongside content. raw_chunk stores the header-free text for display
    # and overlap-stitching (vector_store.get_document_chunks reads raw_chunk).
    header = f"[Document: {source}]\n" if source else ""
    return [
        Document(
            page_content=header + chunk,
            metadata={**metadata, "chunk_index": i, "raw_chunk": chunk},
        )
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def _get_openai_embeddings():
    """Return a cached OpenAIEmbeddings client keyed on the current API key.

    Reuses the HTTP connection pool across semantic chunking calls so we don't
    rebuild the client for every document upload.
    """
    from langchain_openai import OpenAIEmbeddings
    from app.runtime.settings_store import get_effective_api_key
    key = get_effective_api_key() or ""
    model = get_effective_embedding_model()
    if not hasattr(_get_openai_embeddings, "_cache"):
        _get_openai_embeddings._cache: dict = {}
    cache = _get_openai_embeddings._cache
    cache_key = (key, model)
    if cache_key not in cache:
        cache.clear()  # evict stale client when key rotates
        cache[cache_key] = OpenAIEmbeddings(model=model, openai_api_key=key or None)
    return cache[cache_key]


def _semantic_chunk(text: str, metadata: dict) -> list[Document]:
    # Lazy import — langchain_experimental is optional; not installed on Vercel.
    try:
        from langchain_experimental.text_splitter import SemanticChunker
    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "langchain_experimental not installed — falling back to recursive chunker. "
            "Install it with: pip install langchain-experimental"
        )
        return _recursive_chunk(text, metadata)

    settings = get_settings()
    embeddings = _get_openai_embeddings()
    splitter = SemanticChunker(
        embeddings,
        breakpoint_threshold_type=settings.semantic_breakpoint_threshold_type,
    )
    docs = splitter.create_documents([text], metadatas=[metadata])
    source = metadata.get("source", "")
    header = f"[Document: {source}]\n" if source else ""
    for i, doc in enumerate(docs):
        raw = doc.page_content
        doc.metadata["chunk_index"] = i
        doc.metadata["raw_chunk"] = raw
        if header:
            doc.page_content = header + raw
    return docs
