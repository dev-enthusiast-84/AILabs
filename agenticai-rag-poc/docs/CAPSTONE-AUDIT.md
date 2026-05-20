# Edureka Capstone Audit

This audit maps `docs/requirements/edureka-project.pdf` to the implemented system, tests, documentation, and submission package expectations.

## Requirement Coverage

| # | PDF task | Implementation evidence | Validation evidence |
|---|----------|-------------------------|---------------------|
| 1 | Set up project foundation | `backend/`, `frontend/`, `scripts/local/setup.sh`, `Makefile`, Docker, Vercel scripts, Spec-Kit specs under `.specify/specs/` | `scripts/test/run-tests.sh`, setup scripts, spec compliance check |
| 2 | Design user interaction layer | React dashboard with upload, indexed document list, chat window, Settings, Guardrails, guest/admin flows; FastAPI REST API | Frontend unit tests, Playwright E2E structural tests, backend integration API tests |
| 3 | Implement document ingestion | `backend/app/rag/ingestion.py` supports TXT, PDF, CSV, XLSX/XLS; upload scanner validates file type, size, zip bombs, stored prompt injection, optional ClamAV | `backend/tests/unit/test_ingestion.py`, `backend/tests/integration/test_api_documents.py` |
| 4 | Prepare data for semantic search | `backend/app/rag/chunking.py` recursive and semantic chunking, contextual chunk headers, raw chunk metadata | `backend/tests/unit/test_chunking.py`, document chunk/content endpoint tests |
| 5 | Build vector knowledge store | `backend/app/rag/vector_store.py` supports Chroma, Pinecone, memory, and small Blob fallback; Pinecone is production/Vercel default; Blob stores original uploaded files | vector store unit tests, Pinecone unit tests, Blob vector/file store tests, live Chroma tests |
| 6 | Intelligent retrieval | Similarity search, score threshold, MMR, multi-query retrieval, HyDE, RRF fusion, optional BM25 hybrid retrieval and reranking | `test_rag_agent.py`, `test_vector_store.py`, live agent tests |
| 7 | RAG pipeline | Simple retrieve-generate path and 7-node LangGraph agentic path return grounded answer, sources, validation, token telemetry | `test_pipeline.py`, `test_api_query.py`, live API/agent tests |
| 8 | Agent-based reasoning | Planner, HyDE, Retriever, Grader, Reranker, Generator, Validator with retry loop and trace telemetry | `test_rag_agent.py`, `test_live_agent.py` |
| 9 | Reliability and safety controls | Guardrails, Pydantic validation, rate limits, JWT/bcrypt auth, upload scanner, grounded answer validation | auth, guardrails, query, documents, and agent tests |
| 10 | Deploy and document | Vercel Services full-stack, frontend-only deployment, Docker Compose, local dev scripts, setup/architecture/API/testing/security docs, pitch page | deployment script tests, docs, `pitch.html`, generated zip package |

## Project-Scope Engineering Challenges

These challenges are directly relevant to the capstone PDF expectation that documentation explain setup, architecture, agent roles, deployment steps, limitations, and challenges faced during development.

### Document Format Variability

The project accepts TXT, PDF, CSV, and Excel files. Each format requires different parsing behavior, encoding handling, validation, and empty-content detection. The ingestion layer normalizes these formats into text before chunking, while tests verify each supported format.

### Chunking and Retrieval Quality

RAG quality depends on chunk size, overlap, metadata, and retrieval parameters. The project uses contextual chunk headers, configurable recursive or semantic chunking, similarity search, MMR, score thresholds, and optional BM25/reranking to improve retrieval while keeping defaults simple enough for a capstone deployment.

### Grounded Generation and Hallucination Control

LLMs can answer confidently even when documents do not contain enough information. The implementation keeps generation constrained to retrieved context, returns sources, validates outputs with a Validator agent, and exposes a verification badge and trace so users can understand answer reliability.

### Agent Orchestration Complexity

The agentic path has several moving parts: planning, HyDE query expansion, retrieval, optional grading/reranking, generation, validation, and retries. The project keeps a simpler `simple` RAG mode alongside the full agentic path so users can compare speed and reasoning depth.

### Deployment Environment Differences

Local, Docker, persistent backend hosts, and Vercel serverless deployments have different filesystem and process-lifetime behavior. The documentation calls out which vector/file stores are appropriate for each environment so uploaded documents remain predictable.

### Safe Configuration and Testing

The app needs secrets for live LLM/vector behavior, but normal unit and integration tests must run without real provider calls. The test strategy separates mocked unit/integration tests from opt-in live dependency tests.

## Additional Feature-Specific Engineering Notes

The following items are beyond the base capstone expectations. They are documented separately so they do not inflate the stated project scope.

### Serverless Persistence Beyond The Base Requirement

ChromaDB is appropriate for local and Docker deployments where the backend has a durable writable filesystem. Vercel full-stack deployments run on serverless instances where local filesystem state is ephemeral and not shared across instances. The production path therefore uses `VECTOR_STORE_TYPE=pinecone` for vector persistence and `FILE_STORE_TYPE=blob` for original uploaded files. `VECTOR_STORE_TYPE=blob` remains only a small demo/fallback vector option.

### Role and Session Isolation Hardening

Guests and admins must not see or query each other’s documents or settings. Guest documents are scoped by session metadata, admin views exclude guest documents, and guest settings are limited to one update per session. This extends the base capstone with stricter multi-role behavior.

### Backend Redaction as Privacy Boundary

Frontend redaction is useful for immediate UX, but export privacy cannot depend on browser code. Transcript export and voice/audio export use backend redaction as the authoritative layer. Tests assert sensitive values do not appear in exported transcripts or synthesis input.

### Multilingual Retrieval Quality

Answer-language selection is presentation behavior, not retrieval intent. The query API keeps the clean user question for retrieval and passes language instructions only to generation. This is a feature-specific quality improvement beyond the original PDF.

### Voice and Browser Security

Voice-to-voice chat requires microphone permission and speech playback, while the rest of the app keeps camera/geolocation disabled. Vercel headers allow `microphone=(self)` only and keep CSP, `nosniff`, `X-Frame-Options`, referrer policy, and HSTS in production.

### Runtime Settings Without Secret Leakage

OpenAI, Pinecone, Blob, LangSmith, model, and token settings can be supplied through role-aware Settings UI paths. Responses use masked sources and safe metadata; vector store type is deployment configuration and is not runtime-mutable from the UI.

## Submission Checklist

- Source code is present under `backend/`, `frontend/`, `scripts/`, `docs/`, and `.specify/`.
- Documentation explains setup, architecture, agent roles, deployment, limitations, and challenges.
- `pitch.html` summarizes the capstone mapping and production-grade additions.
- `agentic-rag-poc-submission.zip` can be regenerated after final validation.
- Tests cover backend unit/integration, frontend unit, Playwright E2E, live dependency checks, Ragas evaluation, and deployment scripts.

## Known Limitations

- The base capstone path requires an OpenAI-compatible API key for embeddings and generation.
- Live tests require external services and are intentionally separate from the normal test suite.
- Cross-encoder reranking and semantic chunking require optional heavier dependencies.
- Vercel serverless deployments should use hosted vector/object storage; local filesystem persistence is only reliable in local/Docker or persistent-backend deployments.
- Large voice/audio exports are an additional feature-specific area; higher-scale production use may require async jobs and object-storage signed URLs.
