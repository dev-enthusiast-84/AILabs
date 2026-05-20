import logging
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.rag.chunking import chunk_text, _recursive_chunk, _semantic_chunk


# ── Existing tests (preserved) ─────────────────────────────────────────────────

def test_chunk_text_produces_documents():
    text = "This is a test sentence. " * 100
    docs = chunk_text(text, metadata={"source": "test.txt"})
    assert len(docs) > 0


def test_chunk_text_metadata_preserved():
    docs = chunk_text("Short content here.", metadata={"source": "file.txt", "tag": "test"})
    assert all(d.metadata["source"] == "file.txt" for d in docs)
    assert all("chunk_index" in d.metadata for d in docs)


def test_chunk_text_no_empty_chunks():
    docs = chunk_text("   \n\n   ", metadata={"source": "empty.txt"})
    assert all(d.page_content.strip() for d in docs)


def test_chunk_text_long_document():
    text = ("Enterprise policy document content. " * 200)
    docs = chunk_text(text, metadata={"source": "big.txt"})
    assert len(docs) >= 2


# ── New tests for chunking strategies ─────────────────────────────────────────

def test_recursive_chunker_is_default():
    """With chunker_type='recursive', chunk_text delegates to _recursive_chunk."""
    with patch("app.rag.chunking.get_effective_chunker_type", return_value="recursive"), \
         patch("app.rag.chunking.get_effective_chunk_size", return_value=800), \
         patch("app.rag.chunking.get_effective_chunk_overlap", return_value=100):

        text = "Some document content. " * 50
        metadata = {"source": "test.txt"}
        docs = chunk_text(text, metadata)

        assert len(docs) > 0
        assert all("chunk_index" in d.metadata for d in docs)
        assert all(d.metadata["source"] == "test.txt" for d in docs)


def test_semantic_chunker_selected_by_config_falls_back_when_not_installed(caplog):
    """When chunker_type='semantic' but langchain_experimental is missing, falls back to recursive."""
    with patch("app.rag.chunking.get_effective_chunker_type", return_value="semantic"), \
         patch("app.rag.chunking.get_effective_chunk_size", return_value=800), \
         patch("app.rag.chunking.get_effective_chunk_overlap", return_value=100), \
         patch("app.rag.chunking.get_settings") as mock_settings:
        mock_settings.return_value.semantic_breakpoint_threshold_type = "percentile"

        text = "Fallback test content. " * 20
        metadata = {"source": "fallback.txt"}

        # Simulate langchain_experimental not being installed
        with patch.dict("sys.modules", {"langchain_experimental": None,
                                        "langchain_experimental.text_splitter": None}):
            with caplog.at_level(logging.WARNING, logger="app.rag.chunking"):
                docs = chunk_text(text, metadata)

        # Should fall back to recursive chunks
        assert len(docs) > 0
        assert all("chunk_index" in d.metadata for d in docs)
        assert any("langchain_experimental" in r.message for r in caplog.records)


def test_semantic_chunker_adds_chunk_index():
    """_semantic_chunk adds chunk_index to each doc returned by SemanticChunker."""
    fake_docs = [
        Document(page_content=f"Chunk {i}", metadata={"source": "doc.txt"})
        for i in range(3)
    ]

    mock_splitter = MagicMock()
    mock_splitter.create_documents.return_value = fake_docs

    mock_embeddings_instance = MagicMock()
    mock_embeddings_cls = MagicMock(return_value=mock_embeddings_instance)
    mock_semantic_cls = MagicMock(return_value=mock_splitter)

    mock_experimental_module = MagicMock()
    mock_experimental_module.SemanticChunker = mock_semantic_cls
    mock_openai_module = MagicMock()
    mock_openai_module.OpenAIEmbeddings = mock_embeddings_cls

    with patch("app.settings_store.get_effective_api_key", return_value="sk-fake-key"), \
         patch("app.rag.chunking.get_settings") as mock_settings, \
         patch.dict("sys.modules", {
             "langchain_experimental": MagicMock(),
             "langchain_experimental.text_splitter": mock_experimental_module,
             "langchain_openai": mock_openai_module,
         }):

        mock_settings.return_value.semantic_breakpoint_threshold_type = "percentile"

        docs = _semantic_chunk("Some text", {"source": "doc.txt"})

    assert len(docs) == 3
    for i, doc in enumerate(docs):
        assert doc.metadata["chunk_index"] == i


def test_recursive_chunk_preserves_metadata():
    """Source metadata is propagated to every chunk from _recursive_chunk."""
    metadata = {"source": "policy.pdf", "author": "HR", "year": 2024}
    text = "Employee handbook content. " * 100

    with patch("app.rag.chunking.get_effective_chunk_size", return_value=200), \
         patch("app.rag.chunking.get_effective_chunk_overlap", return_value=20):

        docs = _recursive_chunk(text, metadata)

    assert len(docs) > 0
    for doc in docs:
        assert doc.metadata["source"] == "policy.pdf"
        assert doc.metadata["author"] == "HR"
        assert doc.metadata["year"] == 2024
        assert "chunk_index" in doc.metadata


# ── Contextual Chunk Header tests ──────────────────────────────────────────────

def test_recursive_chunk_adds_contextual_header():
    """_recursive_chunk must prepend [Document: <source>] to page_content."""
    with patch("app.rag.chunking.get_effective_chunk_size", return_value=200), \
         patch("app.rag.chunking.get_effective_chunk_overlap", return_value=20):
        docs = _recursive_chunk("Some policy content. " * 10, {"source": "hr-policy.pdf"})

    assert len(docs) > 0
    for doc in docs:
        assert doc.page_content.startswith("[Document: hr-policy.pdf]\n")


def test_recursive_chunk_stores_raw_chunk_in_metadata():
    """raw_chunk in metadata must equal chunk text without the contextual header."""
    with patch("app.rag.chunking.get_effective_chunk_size", return_value=200), \
         patch("app.rag.chunking.get_effective_chunk_overlap", return_value=20):
        docs = _recursive_chunk("Employee handbook content. " * 10, {"source": "handbook.txt"})

    for doc in docs:
        assert "raw_chunk" in doc.metadata
        raw = doc.metadata["raw_chunk"]
        assert doc.page_content == f"[Document: handbook.txt]\n{raw}"


def test_recursive_chunk_no_header_when_source_missing():
    """No header when metadata lacks 'source'; raw_chunk must still be stored."""
    with patch("app.rag.chunking.get_effective_chunk_size", return_value=200), \
         patch("app.rag.chunking.get_effective_chunk_overlap", return_value=20):
        docs = _recursive_chunk("Anonymous content. " * 10, {})

    assert len(docs) > 0
    for doc in docs:
        assert not doc.page_content.startswith("[Document:")
        assert "raw_chunk" in doc.metadata
        assert doc.page_content == doc.metadata["raw_chunk"]


def test_semantic_chunk_adds_contextual_header_and_raw_chunk():
    """_semantic_chunk must prepend the contextual header and store raw_chunk."""
    fake_docs = [
        Document(page_content=f"Semantic chunk {i}", metadata={"source": "sem.txt"})
        for i in range(2)
    ]
    mock_splitter = MagicMock()
    mock_splitter.create_documents.return_value = fake_docs

    mock_experimental = MagicMock()
    mock_experimental.SemanticChunker = MagicMock(return_value=mock_splitter)
    mock_openai = MagicMock()
    mock_openai.OpenAIEmbeddings = MagicMock(return_value=MagicMock())

    with patch("app.settings_store.get_effective_api_key", return_value="sk-fake"), \
         patch("app.rag.chunking.get_settings") as mock_settings, \
         patch.dict("sys.modules", {
             "langchain_experimental": MagicMock(),
             "langchain_experimental.text_splitter": mock_experimental,
             "langchain_openai": mock_openai,
         }):
        mock_settings.return_value.semantic_breakpoint_threshold_type = "percentile"

        docs = _semantic_chunk("text", {"source": "sem.txt"})

    assert len(docs) == 2
    for i, doc in enumerate(docs):
        assert doc.page_content.startswith("[Document: sem.txt]\n"), \
            f"chunk {i} missing contextual header"
        assert "raw_chunk" in doc.metadata
        assert doc.page_content == f"[Document: sem.txt]\n{doc.metadata['raw_chunk']}"


def test_semantic_chunk_no_header_when_source_missing():
    """_semantic_chunk with no 'source' must not add header but must store raw_chunk."""
    fake_docs = [Document(page_content="Chunk A", metadata={})]
    mock_splitter = MagicMock()
    mock_splitter.create_documents.return_value = fake_docs

    mock_experimental = MagicMock()
    mock_experimental.SemanticChunker = MagicMock(return_value=mock_splitter)
    mock_openai = MagicMock()
    mock_openai.OpenAIEmbeddings = MagicMock(return_value=MagicMock())

    with patch("app.settings_store.get_effective_api_key", return_value="sk-fake"), \
         patch("app.rag.chunking.get_settings") as mock_settings, \
         patch.dict("sys.modules", {
             "langchain_experimental": MagicMock(),
             "langchain_experimental.text_splitter": mock_experimental,
             "langchain_openai": mock_openai,
         }):
        mock_settings.return_value.semantic_breakpoint_threshold_type = "percentile"

        docs = _semantic_chunk("text", {})

    assert len(docs) == 1
    assert not docs[0].page_content.startswith("[Document:")
    assert docs[0].metadata["raw_chunk"] == "Chunk A"
