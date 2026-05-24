"""Unit tests for app/rag/pipeline.py — pure helper functions only (no LLM calls)."""
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.rag.pipeline import format_context


# ── format_context (pure function) ────────────────────────────────────────────

def test_format_context_single_document():
    docs = [Document(page_content="Remote work: up to 3 days.", metadata={"source": "policy.txt"})]
    result = format_context(docs)
    assert "[Source 1: policy.txt]" in result
    assert "Remote work" in result


def test_format_context_multiple_documents_uses_separator():
    docs = [
        Document(page_content="Remote policy.", metadata={"source": "remote.txt"}),
        Document(page_content="Leave policy.", metadata={"source": "leave.txt"}),
    ]
    result = format_context(docs)
    assert "[Source 1: remote.txt]" in result
    assert "[Source 2: leave.txt]" in result
    assert "---" in result   # separator between chunks


def test_format_context_unknown_source_fallback():
    docs = [Document(page_content="Some content.", metadata={})]
    result = format_context(docs)
    assert "unknown" in result


def test_format_context_respects_max_context_chunks():
    """format_context must cap chunks at the effective runtime setting."""
    docs = [
        Document(page_content=f"Content {i}", metadata={"source": f"doc{i}.txt"})
        for i in range(8)
    ]
    with patch("app.rag.pipeline.get_effective_max_context_chunks", return_value=4):
        result = format_context(docs)
    source_count = result.count("[Source ")
    assert source_count <= 4


def test_format_context_empty_list_returns_empty():
    result = format_context([])
    assert result == ""


def test_format_context_numbering_is_sequential():
    docs = [
        Document(page_content="A", metadata={"source": "a.txt"}),
        Document(page_content="B", metadata={"source": "b.txt"}),
        Document(page_content="C", metadata={"source": "c.txt"}),
    ]
    result = format_context(docs)
    assert "[Source 1:" in result
    assert "[Source 2:" in result
    assert "[Source 3:" in result


def test_format_context_uses_raw_chunk_over_page_content():
    """When raw_chunk is present in metadata, format_context must use it, not page_content."""
    docs = [
        Document(
            page_content="[Document: policy.txt]\nActual readable text.",
            metadata={"source": "policy.txt", "raw_chunk": "Actual readable text."},
        )
    ]
    result = format_context(docs)
    assert "Actual readable text." in result
    assert "[Document: policy.txt]" not in result


def test_format_context_backward_compat_no_raw_chunk():
    """When raw_chunk is absent (pre-header chunks), page_content is used as fallback."""
    docs = [
        Document(
            page_content="Legacy chunk without header.",
            metadata={"source": "legacy.txt"},
        )
    ]
    result = format_context(docs)
    assert "Legacy chunk without header." in result


# ── run_simple_rag (mocked LLM + vector store) ────────────────────────────────

def _make_fake_callback(total_tokens: int = 150):
    """Return a context-manager mock that exposes usage_metadata."""
    cb = MagicMock()
    cb.usage_metadata = {"m": {"total_tokens": total_tokens, "input_tokens": 0, "output_tokens": 0}}
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cb)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, cb


def test_run_simple_rag_happy_path():
    """run_simple_rag returns expected keys and values when documents are found."""
    fake_docs = [
        Document(page_content="RAG grounds answers in documents.", metadata={"source": "doc1.txt"}),
    ]
    fake_cb_cm, _ = _make_fake_callback(total_tokens=150)
    expected_answer = "RAG grounds answers in retrieved context."

    # Build a chain mock that returns the expected answer when invoked
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = expected_answer

    # mock_llm_instance is the return value of _llm()
    mock_llm_instance = MagicMock()

    # Patch the three external dependencies of run_simple_rag
    with patch("app.rag.pipeline.similarity_search", return_value=fake_docs), \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=mock_llm_instance) as _mock_llm, \
         patch("app.rag.pipeline.StrOutputParser") as mock_parser_cls:

        # Wire: prompt | llm → chain_a; chain_a | parser → chain_b (== mock_chain)
        # We achieve this by making the __or__ operator return mock_chain at every step.
        mock_parser_instance = MagicMock()
        mock_parser_cls.return_value = mock_parser_instance
        # chain_a = _SIMPLE_RAG_PROMPT | llm_instance  → MagicMock
        # chain_b = chain_a | parser_instance          → mock_chain (returns expected_answer)
        # We need to ensure the final .invoke() call returns expected_answer.
        # The safest way: patch the whole prompt template to return a chain directly.

        # Re-patch _SIMPLE_RAG_PROMPT so that prompt | llm → chain_a, chain_a | parser → mock_chain
        mock_chain_a = MagicMock()
        mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

        with patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:
            mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)

            from app.rag.pipeline import run_simple_rag
            result = run_simple_rag("What is RAG?")

    assert isinstance(result["answer"], str)
    assert result["answer"] == expected_answer
    assert isinstance(result["sources"], list)
    assert result["validation"] == "N/A"
    assert result["mode"] == "simple"
    assert isinstance(result["tokens_used"], int)
    assert result["tokens_used"] >= 0


def test_run_simple_rag_no_chunks_returns_empty_sources():
    """When similarity_search returns nothing, sources should be [] and mode still 'simple'."""
    fake_cb_cm, _ = _make_fake_callback(total_tokens=50)
    expected_answer = "I could not find sufficient information."

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = expected_answer
    mock_chain_a = MagicMock()
    mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

    with patch("app.rag.pipeline.similarity_search", return_value=[]), \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=MagicMock()), \
         patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:

        mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)

        from app.rag.pipeline import run_simple_rag
        result = run_simple_rag("What is quantum entanglement?")

    assert result["sources"] == []
    assert result["validation"] == "N/A"
    assert result["mode"] == "simple"


def test_run_simple_rag_token_count_included():
    """tokens_used must reflect the value from get_openai_callback."""
    expected_tokens = 200
    fake_docs = [
        Document(page_content="Generative AI uses transformers.", metadata={"source": "ai.txt"}),
    ]
    fake_cb_cm, _ = _make_fake_callback(total_tokens=expected_tokens)

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "Transformers power modern AI."
    mock_chain_a = MagicMock()
    mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

    with patch("app.rag.pipeline.similarity_search", return_value=fake_docs), \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=MagicMock()), \
         patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:

        mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)

        from app.rag.pipeline import run_simple_rag
        result = run_simple_rag("How does generative AI work?")

    assert result["tokens_used"] == expected_tokens


def test_run_simple_rag_multiple_sources_deduped():
    """Duplicate source filenames must appear only once in the sources list."""
    fake_docs = [
        Document(page_content="Chunk 1.", metadata={"source": "policy.txt"}),
        Document(page_content="Chunk 2.", metadata={"source": "policy.txt"}),
        Document(page_content="Chunk 3.", metadata={"source": "other.txt"}),
    ]
    fake_cb_cm, _ = _make_fake_callback(total_tokens=100)

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "Policy answer."
    mock_chain_a = MagicMock()
    mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

    with patch("app.rag.pipeline.similarity_search", return_value=fake_docs), \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=MagicMock()), \
         patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:

        mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)

        from app.rag.pipeline import run_simple_rag
        result = run_simple_rag("What is the leave policy?")

    assert len(result["sources"]) == 2
    assert set(result["sources"]) == {"policy.txt", "other.txt"}


def test_run_simple_rag_spanish_language_keeps_retrieval_query_clean():
    """Language instructions go to generation, not the retrieval query."""
    question = "¿Cuál es la política de trabajo remoto?"
    answer_instruction = (
        "Answer in Spanish. Keep source grounding and do not translate source filenames."
    )
    fake_docs = [
        Document(page_content="Remote work is allowed.", metadata={"source": "policy.txt"}),
    ]
    fake_cb_cm, _ = _make_fake_callback(total_tokens=80)

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "La política permite trabajo remoto."
    mock_chain_a = MagicMock()
    mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

    with patch("app.rag.pipeline.similarity_search", return_value=fake_docs) as mock_search, \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=MagicMock()), \
         patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:

        mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)

        from app.rag.pipeline import run_simple_rag
        result = run_simple_rag(question, answer_instruction=answer_instruction)

    mock_search.assert_called_once_with(question)
    generation_payload = mock_chain.invoke.call_args.args[0]
    assert generation_payload["question"] == question
    # Instruction is normalized with a trailing newline so it stays separated
    # from the rule sentence that follows it in the prompt template.
    assert generation_payload["answer_instruction"] == answer_instruction.rstrip() + "\n"
    assert "Answer in Spanish" not in mock_search.call_args.args[0]
    assert result["answer"] == "La política permite trabajo remoto."


# ── _pipeline_docs_to_citations helper ───────────────────────────────────────

def test_pipeline_docs_to_citations_basic():
    """_pipeline_docs_to_citations converts Documents to plain dicts."""
    from app.rag.pipeline import _pipeline_docs_to_citations
    docs = [
        Document(
            page_content="chunk body",
            metadata={"source": "doc.txt", "chunk_index": 1, "raw_chunk": "chunk body"},
        )
    ]
    result = _pipeline_docs_to_citations(docs)
    assert len(result) == 1
    assert result[0]["source"] == "doc.txt"
    assert result[0]["chunk_index"] == 1
    assert result[0]["text"] == "chunk body"


def test_pipeline_docs_to_citations_truncates_to_300():
    """_pipeline_docs_to_citations truncates text to 300 chars."""
    from app.rag.pipeline import _pipeline_docs_to_citations
    long_text = "y" * 500
    docs = [Document(page_content=long_text, metadata={"source": "f.txt", "raw_chunk": long_text})]
    result = _pipeline_docs_to_citations(docs)
    assert len(result[0]["text"]) == 300


def test_pipeline_docs_to_citations_falls_back_to_page_content():
    """When raw_chunk is absent, page_content is used."""
    from app.rag.pipeline import _pipeline_docs_to_citations
    docs = [Document(page_content="fallback", metadata={"source": "x.txt"})]
    result = _pipeline_docs_to_citations(docs)
    assert result[0]["text"] == "fallback"


def test_run_simple_rag_returns_citations_key():
    """run_simple_rag must include 'citations' in the result dict."""
    fake_docs = [
        Document(
            page_content="chunk text",
            metadata={"source": "doc.txt", "chunk_index": 0, "raw_chunk": "chunk text"},
        ),
    ]
    fake_cb_cm, _ = _make_fake_callback(total_tokens=100)

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "answer"
    mock_chain_a = MagicMock()
    mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

    with patch("app.rag.pipeline.similarity_search", return_value=fake_docs), \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=MagicMock()), \
         patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:
        mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)
        from app.rag.pipeline import run_simple_rag
        result = run_simple_rag("What is RAG?")

    assert "citations" in result
    assert isinstance(result["citations"], list)
    assert len(result["citations"]) == 1
    assert result["citations"][0]["source"] == "doc.txt"
    assert result["citations"][0]["text"] == "chunk text"


def test_run_simple_rag_no_docs_returns_empty_citations():
    """When no docs are found, citations must be an empty list."""
    fake_cb_cm, _ = _make_fake_callback(total_tokens=50)
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = "No info found."
    mock_chain_a = MagicMock()
    mock_chain_a.__or__ = MagicMock(return_value=mock_chain)

    with patch("app.rag.pipeline.similarity_search", return_value=[]), \
         patch("app.rag.pipeline.get_usage_metadata_callback", return_value=fake_cb_cm), \
         patch("app.agents.rag_agent._llm", return_value=MagicMock()), \
         patch("app.rag.pipeline._SIMPLE_RAG_PROMPT") as mock_prompt:
        mock_prompt.__or__ = MagicMock(return_value=mock_chain_a)
        from app.rag.pipeline import run_simple_rag
        result = run_simple_rag("unknown topic")

    assert result["citations"] == []
