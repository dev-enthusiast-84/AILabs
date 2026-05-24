# Agent Pipeline

> [← Home](README.md) · [Architecture](architecture/ARCHITECTURE.md)

Seven-node LangGraph StateGraph. State flows as a typed `AgentState` dict; per-node token counts and latency are recorded and returned as an `AgentTrace` object.

---

## Pipeline Graph

```
planner → hyde → retriever → grader → reranker → generator → validator → END
                                                      ↑              │
                                              NEEDS_REVISION (≤2 retries)
```

---

## Node Descriptions

| Node | Role | Key Config | Input → Output |
|------|------|-----------|----------------|
| **Planner** | Rewrites the question into a precise primary query + 2 alternative phrasings using structured output (`_PlannerOutput`) | `PLANNER_MODEL` | question → `refined_query` + `query_variants[2]` |
| **HyDE** | Generates a short hypothetical document passage that *would* answer the question — embeds natural prose instead of a bare question for better semantic alignment | `PLANNER_MODEL` | refined query → `hypothetical_answer` |
| **Retriever** | Fans out across primary + 2 variants + HyDE (up to 4 searches); fuses results with Reciprocal Rank Fusion (RRF); optional BM25 adds a 5th lexical list; supports MMR and score-threshold | `RETRIEVER_K`, `RETRIEVER_FUSION_MODE`, `RETRIEVER_HYBRID_BM25`, `RETRIEVER_USE_MMR`, `SIMILARITY_SCORE_THRESHOLD` | queries → `retrieved_docs` + `sources` |
| **Grader** | Self-RAG relevance filter — presents all chunks to an LLM in one call; drops irrelevant chunks before generation; keeps full set if all graded irrelevant | `RELEVANCE_GRADER_ENABLED`, `PLANNER_MODEL` | docs → filtered `retrieved_docs` + `chunks_after_grading` |
| **Reranker** | Two modes: **llm-judge** (default) — single OpenAI batch call scores all chunks 0–10 using `RERANKER_JUDGE_MODEL` (default `gpt-4.1-mini`); structured output via `_LLMJudgeScores`; 8 s timeout with graceful fallback; works on Vercel. **cross-encoder** — `sentence_transformers.CrossEncoder` scores (question, chunk) pairs; lazy-imports; silently disabled if package absent; not available on Vercel (~80 MB model); `_cross_encoder_cache` dict keyed by model name prevents repeated downloads. Cross-encoder authentication: passes `token=HF_TOKEN` (if set) or `token=False` (explicit opt-out) to suppress unauthenticated-request warnings. `RERANKER_JUDGE_MODEL` is configurable at runtime via Settings UI without restart. | `RERANKER_TYPE`, `RERANKER_JUDGE_MODEL`, `RERANKER_MODEL`, `RERANKER_TOP_K`, `HF_TOKEN` | filtered docs → reordered docs + `chunks_after_rerank` |
| **Generator** | Grounded answer constrained strictly to retrieved context; refuses fabrication; prepends revision hint on retries; token budget enforced | `GENERATOR_MODEL`, `MAX_COMPLETION_TOKENS` | context + question → answer text |
| **Validator** | Structured output (`_ValidationResult`) classifies `VALID` or `NEEDS_REVISION`; routes back to Generator via conditional edge up to `_MAX_RETRIES = 2` | `VALIDATOR_MODEL` | answer + context → `validation` + `validation_reason` |

---

## Search Improvement Features

Seven complementary techniques are layered into the agentic pipeline. All features are on by default.

| # | Feature | How it works | Default | Config key |
|---|---------|-------------|---------|------------|
| 1 | **Multi-Query Retrieval** | Planner generates 2 variant phrasings; Retriever fans out across all 3 | Yes | — (core planner) |
| 2 | **HyDE** | Hypothetical document embedding improves abstract-query recall | Yes | — (core HyDE node) |
| 3 | **Contextual Chunk Headers** | `[Document: source]` prefix embedded; raw text kept clean for LLM | Yes | — (applied at index time) |
| 4 | **LLM-as-Judge Reranking** | Single OpenAI batch call scores chunks 0–10; graceful fallback on timeout/failure; works on Vercel | Yes | `RERANKER_TYPE=llm-judge`, `RERANKER_JUDGE_MODEL=gpt-4.1-mini` |
| 5 | **RAG Fusion / RRF** | Reciprocal Rank Fusion combines rankings from all query variants | Yes | `RETRIEVER_FUSION_MODE=rrf` |
| 6 | **Self-RAG Relevance Grader** | LLM grades chunk relevance; drops irrelevant context before generation | Yes | `RELEVANCE_GRADER_ENABLED=true` |
| 7 | **Hybrid BM25 + Dense Search** | BM25 lexical results fused with dense results via RRF | Yes | `RETRIEVER_HYBRID_BM25=true` |

---

## Simple RAG Mode

`mode="simple"` bypasses all seven nodes. `run_simple_rag()` in `app/rag/pipeline.py` executes a single retrieve → generate pass. `validation` is always `"N/A"`. LLM cost is roughly one-third of agentic mode. Use for fast, low-cost queries where hallucination risk is acceptable.

---

## Limitations

| Limitation | Details |
|------------|---------|
| **Single user namespace** | All users share one document index — no per-user isolation |
| **No streaming** | Full 7-node pipeline finishes before responding (typically 8–20 s) |
| **No conversational memory** | Each query is independent; follow-ups have no prior context |
| **Serverless persistence** | On Vercel / Lambda use `VECTOR_STORE_TYPE=pinecone` for durable vectors/chunks; use `FILE_STORE_TYPE=blob` for durable original files |
| **Document update** | Re-uploading the same filename appends chunks — delete first, then re-upload |
| **Vercel rate limits** | `slowapi` counters are per function instance, not global |
| **Token cost scales with pipeline** | All 7 features enabled = up to 5 LLM calls per query (planner + HyDE + grader + llm-judge + generator+validator) |
| **BM25 IDF accuracy** | IDF ≈ 0 with fewer than ~10 documents; hybrid search works best with larger corpora |
| **Cross-encoder not on Vercel** | `sentence_transformers` (~80 MB model) exceeds serverless constraints; use `RERANKER_TYPE=llm-judge` (the default) on Vercel |
| **Self-RAG grader latency** | Adds ~1–3 s per query; disable with `RELEVANCE_GRADER_ENABLED=false` if latency is priority |
| **llm-judge reranker latency** | Adds ~1–3 s per query for the scoring call; 8 s timeout with pass-through fallback ensures no answer is lost |

---

## Key Engineering Challenges

| Challenge | Resolution |
|-----------|------------|
| `TypedDict` + `Annotated` reducers conflicting with LangGraph versions | Used `operator.add` only on `messages`; last-write-wins on all other fields |
| Token accumulation across nodes with no shared context manager | Wrapped every LLM call in `get_openai_callback()`, accumulated in `AgentState` |
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
