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

## Engineering Challenges & Limitations

→ [Limitations & Development Challenges](project/CHALLENGES.md) — serverless persistence, chunking/retrieval quality, hallucination control, agent orchestration, secrets management, role isolation, voice security, testing strategy, and all known limitations.

## Submission Checklist

- Source code is present under `backend/`, `frontend/`, `scripts/`, `docs/`, and `.specify/`.
- [Documentation](../README.md#submission-reference) explains setup, architecture, agent roles, deployment, limitations, and challenges.
- `pitch.html` summarizes the capstone mapping and production-grade additions.
- `agentic-rag-poc-submission.zip` can be regenerated after final validation.
- Tests cover backend unit/integration, frontend unit, Playwright E2E, live dependency checks, Ragas evaluation, and deployment scripts.

→ Known limitations are listed in [Limitations & Development Challenges](project/CHALLENGES.md#known-limitations).
