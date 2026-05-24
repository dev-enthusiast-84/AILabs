# Agent Pipeline Engineering Challenges

> [← Limitations & Challenges](project/CHALLENGES.md) · [← Agent Pipeline](architecture/AGENT-PIPELINE.md) · [← Home](README.md)

Implementation challenges encountered while building the seven-node LangGraph pipeline, along with the specific resolutions applied. For broader architectural trade-offs see [Limitations & Challenges](project/CHALLENGES.md). For retrieval-specific decisions see [Retrieval & Reranking](project/CHALLENGES-RETRIEVAL.md).

---

| Challenge | Resolution |
|-----------|------------|
| `TypedDict` + `Annotated` reducers conflicting with LangGraph versions | Used `operator.add` only on `messages`; last-write-wins on all other fields |
| Token accumulation across nodes with no shared context manager | Wrapped every LLM call in `get_usage_metadata_callback()`, accumulated in `AgentState` |
| ChromaDB `@lru_cache` causing state leakage between test runs | Patched `get_vector_store` at session scope in `conftest.py` before any import |
| `with_structured_output` chains returning Pydantic model instead of string | Changed planner to invoke chain separately and extract fields explicitly |
| HyDE generating conversational prose, degrading embedding quality | Refined system prompt to require 3–5 sentence factual prose, no preamble |
| Contextual headers appearing in LLM context and document viewer | Stored original text in `metadata["raw_chunk"]`; `format_context()` reads from it |
| RRF deduplication key slow/memory-intensive for large chunks | Truncated to first 200 characters as practical deduplication key |
| `rank_bm25==0.8.1` not found on PyPI | Corrected to `rank-bm25==0.2.2` (latest available) |
| `sentence_transformers` heavy optional dep breaking tests + cold starts | Wrapped import in `try/except ImportError`; node falls back silently |
| Integration test isolation — `@lru_cache` on `get_vector_store` caused state leakage between test runs | Patched at session scope in `conftest.py` via `pytest_sessionstart` before any app import; `_LIVE_MODE` flag preserves real calls for live suite |
| Vercel + ChromaDB — ChromaDB persists to local files, but Vercel serverless instances are ephemeral and do not share writable storage | Production Vercel deployments use `VECTOR_STORE_TYPE=pinecone` for durable vectors/chunks. Blob is repositioned as `FILE_STORE_TYPE=blob` for original uploaded files, with `VECTOR_STORE_TYPE=blob` kept only for small full-stack demos/fallbacks |
| Multi-format ingestion — CSV/Excel with mixed dtypes produce inconsistent string output | Used `pandas` with `to_string(index=False)` for consistent column-aligned text |
| Stored prompt injection in document content can poison the vector store | Added regex-based injection detection in `guardrails/safety.py`; generator prompt explicitly rejects fabrication |
| Self-RAG grader mock wiring — chain is `PROMPT \| LLM` (one pipe) but tests used two nested `__or__` levels | Fixed to single `__or__`: `mock_prompt.__or__ = MagicMock(return_value=mock_chain)` |
| `AgentState` field expansion — adding 6 new telemetry fields required touching every test that constructed a state dict | Updated `_base_agent_state()` helper in `test_rag_agent.py` to include all new fields with safe defaults |
