# Limitations & Development Challenges

> [← Home](README.md) · [Capstone Audit](project/CAPSTONE-AUDIT.md) · [Operational Limits](deployment/DEPLOY-LIMITS.md) · [Vercel Deployment](deployment/DEPLOY-VERCEL.md)

This document captures the architectural decisions, trade-offs, and known limitations encountered during development. Hard operational limits (upload caps, rate limits, timeouts) are in [Operational Limits](deployment/DEPLOY-LIMITS.md).

---

## Serverless Persistence (Core Challenge)

**Problem:** ChromaDB persists vectors to a local writable filesystem, which works reliably in local dev and Docker Compose. Vercel full-stack deployments run on ephemeral serverless function instances — `/tmp` is not shared across concurrent instances and is wiped on cold start. A file-backed Chroma store therefore loses data between requests or across horizontal scale-out, causing uploaded documents to appear intermittently in list, query, and delete operations.

**Solution:** Production Vercel deployments use `VECTOR_STORE_TYPE=pinecone`. Pinecone provides a managed, durable vector layer that all function instances share. Original uploaded files (for preview/download) use `FILE_STORE_TYPE=blob` backed by Vercel Blob object storage. Both are configurable through the Settings UI without a redeploy.

**Remaining constraint:** Vercel's serverless request body limit caps uploads at ~4.5 MB; the backend enforces 4 MB for admin uploads on Vercel vs 20 MB locally. Guest uploads are capped at 2 MB on both.

**`VECTOR_STORE_TYPE=blob`** is retained only as a small Vercel demo/fallback vector option. Larger production systems should pair a hosted vector database with object storage.

---

## Document Format Variability

Each supported format (TXT, PDF, CSV, XLSX/XLS) requires different parsing, encoding handling, empty-content detection, and validation. The ingestion layer normalises all formats into plain text before chunking. Validation happens at the upload boundary: file type, MIME type, size, zip-bomb expansion ratio, stored prompt injection regex, and optional ClamAV scan.

---

## Chunking and Retrieval Quality

RAG quality is sensitive to chunk size, overlap, metadata, and retrieval parameters. Approaches evaluated:

- **Recursive chunking** (default) — fast, deterministic, low token cost.
- **Semantic chunking** — splits on embedding-similarity boundaries; better quality on prose-heavy docs but slower and costs extra tokens.
- **Contextual chunk headers** — each chunk is prefixed with `[Document: <source>]` before embedding, so the vector captures document provenance alongside content semantics.
- **HyDE** — a hypothetical answer passage is embedded alongside the user question; this improves recall for abstract or ambiguous questions where the question and the answer text occupy different vector-space regions.
- **Multi-query fan-out + RRF** — the Planner generates 2 query re-phrasings; all 3 queries plus the HyDE embedding fan out in parallel and are fused with Reciprocal Rank Fusion.
- **BM25 hybrid** — optional lexical BM25 search fused with dense results via RRF; improves recall on exact-term queries (enabled by default: `RETRIEVER_HYBRID_BM25=true`).
- **Reranking** — three modes: `none` (default env value), `cross-encoder` (`sentence-transformers` re-score, activates automatically when the package is installed, ~80 MB model download), and `llm-judge` (LLM-based reranking, no heavy deps). A smart runtime default applies: Vercel deployments and environments without `sentence-transformers` use `llm-judge`; environments with `sentence-transformers` installed promote to `cross-encoder`. Set `RERANKER_TYPE` explicitly to override.

**Trade-off:** Each additional retrieval feature adds latency and LLM cost. Defaults are chosen to balance quality and cost for a capstone deployment.

---

## Grounded Generation and Hallucination Control

LLMs can produce confident-sounding answers even when the retrieved context does not contain the information. Mitigations:

- Generator is prompted to answer **only** from retrieved context and to state when information is absent.
- **Validator node** independently re-reads the question and generated answer against the retrieved context and classifies the response as `VALID` or `NEEDS_REVISION`; the pipeline retries generation up to 2 times on low-confidence responses.
- Answer exposes `validation` field and `tokens_used` per-node trace in the API response so users and operators can inspect reasoning.

**Remaining constraint:** The Validator uses the same underlying LLM, so systematic hallucination in the model family may not be caught. External human review or automated Ragas evaluation is recommended for critical use cases.

---

## Agent Orchestration Complexity

The full agentic path has 7 nodes, optional branches (Grader, Reranker), and a retry loop. Complexity mitigations:

- `mode="simple"` bypasses planning, HyDE, Grader, Reranker, and Validator — a single retrieve-generate step ~3× faster and suitable when latency matters more than reasoning depth.
- Each node is independently configurable (model override, enable/disable flags) without code changes.
- LangSmith tracing can be enabled at runtime via `LANGCHAIN_TRACING_V2=true` for per-node visibility.

---

## Safe Configuration and Secrets

Provider credentials (OpenAI, Pinecone, Blob, LangSmith) must be available at runtime but must not appear in logs, responses, or exported content. Mitigations:

- Production mode ignores env-supplied provider credentials; they must be entered through the Settings UI.
- Startup credential banner (username + password) is suppressed in `APP_ENV=production`.
- API responses use masked sources; raw keys are never returned.
- Settings UI is role-aware: guests may configure keys exactly once per session; admins may update without restriction.

**Test isolation:** Unit and integration tests run without real provider credentials using mocks. Live-dependency tests (`backend/tests/live/`) require real keys and are intentionally excluded from the standard CI suite.

---

## Role and Session Isolation

Guest and admin sessions must not share documents, settings, or corpus state. Enforcement:

- Guest documents are tagged with the session JTI at index time; admin list/query/delete views filter them out.
- Guest settings are stored per-session and expire with the guest JWT (15 min TTL).
- One-time settings gate: once a guest saves credentials, the endpoint rejects further updates for that session.
- JTI blocklist prevents reuse of logged-out tokens (bounded LRU, 10 000 entries).

---

## Backend Redaction as Privacy Boundary

Frontend redaction provides UX feedback but cannot be trusted as a security control. Transcript export and voice/audio synthesis both apply backend redaction (guardrail engine) before any data leaves the server. Tests assert that sensitive pattern values do not appear in exported transcripts or TTS synthesis input.

---

## Multilingual Retrieval Quality

Language selection for answers is a presentation concern, not a retrieval concern. The query API keeps the user's original question (in any language) for embedding and retrieval; language instructions are injected only into the Generator prompt. This preserves semantic retrieval quality across language boundaries.

---

## Voice and Browser Security

Voice-to-voice chat requires microphone permission while the rest of the app should keep camera and geolocation disabled. Vercel production headers allow `Permissions-Policy: microphone=(self)` and disable all other browser features. CSP, `X-Content-Type-Options`, `X-Frame-Options`, referrer policy, and HSTS are enforced in production.

---

## Async Voice Export Jobs

The in-process async job store enforces TTL-based expiry (job TTL 900 s, artifact TTL 600 s). Expired entries are evicted lazily on the next status check — there is no background sweep thread.

**Constraint:** In long-lived processes with high job creation volume, memory grows until access-based eviction catches up. A production system at scale should use an external job store (Redis, database) with a background expiry sweep.

---

## Optional Heavy Dependencies

| Feature | Dependency | Size | Default |
|---------|-----------|------|---------|
| Reranking (`cross-encoder`) | `sentence-transformers` | ~80 MB model download | Smart default: `llm-judge` on Vercel or without the package; `cross-encoder` when installed |
| Semantic chunking | `langchain-experimental` + embedding calls | Extra token cost | Disabled (`CHUNKER_TYPE=recursive`) |
| BM25 hybrid search | `rank-bm25` | Lightweight | Enabled (`RETRIEVER_HYBRID_BM25=true`) |
| ClamAV antivirus | External `clamd` daemon | Docker Compose only | Disabled unless `CLAMAV_HOST` set |
| Ragas evaluation | `ragas` | Heavy ML dependencies | Disabled unless `RAGAS_EVALUATION_ENABLED=true` |

---

## Testing Challenges

### Test Isolation Without Live Providers

Unit and integration tests must run in CI without real API keys. The solution separates three test layers:

- **Unit tests** (`backend/tests/unit/`) — fully mocked; no network calls; deterministic and idempotent.
- **Integration tests** (`backend/tests/integration/`) — use the FastAPI `TestClient` with mocked vector stores and LLM responses; no external provider calls.
- **Live tests** (`backend/tests/live/`) — hit real OpenAI, Pinecone, and ChromaDB; excluded from standard CI; require `OPENAI_API_KEY` and other credentials.

**Challenge:** Mocked tests can pass while the real integration silently breaks (e.g., embedding dimension mismatch after a provider update, Pinecone index schema change). The live test suite exists specifically to catch this drift, but it is opt-in and not gated in CI.

### Coverage Guardrail

Backend coverage is gated at ≥ 98% (`pytest --cov=app`). Maintaining this while adding features with provider-dependent code paths (Pinecone, Blob, OpenAI) requires careful dependency injection so branches can be exercised with mocks. The cost is additional mock complexity in test setup.

### Frontend E2E Test Fragility

Playwright E2E tests run against a live stack. Tests that depend on LLM responses (query assertions, agent trace content) are non-deterministic by nature. The test suite focuses on structural assertions (element presence, status codes, access control) rather than response content to keep tests deterministic and reproducible.

### Ragas Evaluation

Ragas evaluation (`backend/tests/live/test_live_ragas.py`) requires a populated vector store and real API credentials. It is not automated in CI because:
- It consumes OpenAI tokens.
- It requires pre-indexed documents.
- Scores are stored in `RAGAS_SCORES_FILE` and surfaced in the admin dashboard — not suited to per-commit CI gates.

### Determinism in Time-Sensitive Tests

JWT expiry, rate limiting, and guest session TTL tests are sensitive to clock timing. The test suite uses monkeypatching and explicit TTL injection rather than `time.sleep` to keep tests fast and deterministic.

---

## Known Limitations

- **OpenAI dependency:** All embedding and generation require an OpenAI-compatible API key. There is no offline or alternative-provider fallback in the current implementation.
- **Vercel upload cap:** Admin uploads are limited to 4 MB on Vercel due to serverless request-body constraints (20 MB locally/Docker).
- **Reranker on Vercel:** Cross-encoder reranking is disabled on Vercel because the ~80 MB model download is incompatible with serverless function cold-start constraints.
- **Semantic chunker on Vercel:** Semantic chunking requires extra embedding API calls and falls back to recursive chunking if the dependency is absent.
- **In-memory test store:** `VECTOR_STORE_TYPE=memory` is for tests only; data is lost on process restart.
- **Blob vector store:** `VECTOR_STORE_TYPE=blob` is a small demo/fallback only; it does not scale to production RAG workloads.
- **Live tests:** `backend/tests/live/` require external services (OpenAI, Pinecone) and are excluded from standard CI.
- **Ragas evaluation:** Requires real documents and API keys; not automated in CI.
- **Guest doc retention:** Guest session documents expire after 1 hour (`GUEST_DOC_RETENTION_SECONDS=3600`) but eviction is lazy — no background sweep is running.
