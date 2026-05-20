# Architecture

> [← Home](README.md)

System design, data flow, ingestion pipeline, and project structure.

---

## System Overview

```
Browser
  │ JWT (Bearer) · HTTPS
  ▼
┌──────────────────────────────────────────┐
│  React 18 + TypeScript + Vite            │
│  Tailwind CSS · Zustand authStore        │
│  @vercel/analytics · @vercel/speed-insights │
│  Pages: LoginPage · DashboardPage        │
│  Components: DocumentUpload · DocumentList│
│   ChatInterface · SettingsModal          │
│   GuardrailsModal · DocumentViewerModal  │
└──────────────┬───────────────────────────┘
               │ /api/*
               ▼
┌──────────────────────────────────────────┐
│  FastAPI (uvicorn)                       │
│  Security headers · CORS · slowapi       │
│  POST /api/auth/{login,guest}            │
│  GET|POST|DELETE /api/documents/         │
│  POST /api/query/                        │
│  GET|POST /api/settings/                 │
│  GET|POST|PATCH|DELETE /api/guardrails/  │
└──────┬────────────────────────┬──────────┘
       │ embed + store          │ query
       ▼                        ▼
┌────────────┐  ┌───────────────────────────────┐
│  Vector    │  │  Query Pipeline               │
│  store     │  │  [Guardrail Engine — input]   │
│  + OpenAI  │  │         ↓                     │
│  text-emb  │  │  mode="agentic" (default)     │
└────────────┘  │    Planner → HyDE             │
                │    Retriever (dense + BM25)   │
                │    Grader (opt-in)            │
                │    Reranker (opt-in)          │
                │    Generator → Validator      │
                │         ↓                     │
                │  mode="simple"                │
                │    Retriever → Generator      │
                │    validation = "N/A"         │
                │         ↓                     │
                │  [Guardrail Engine — output]  │
                │  { answer, sources, trace }   │
                └───────────────────────────────┘
```

---

## Document Ingestion Flow

```
File upload → extension + size validation
  → text extraction (PDF/TXT/CSV/XLSX)
  → text sanitisation (null bytes, whitespace)
  → chunker (CHUNKER_TYPE env var):
      "recursive" — RecursiveCharacterTextSplitter (chunk_size=800, overlap=100)
      "semantic"  — SemanticChunker (OpenAI embeddings, breakpoint threshold)
  → Contextual Chunk Header prepended:
      page_content = "[Document: <source>]\n" + chunk_text
      metadata["raw_chunk"] = raw_chunk_text   ← clean text for LLM display
  → OpenAI text-embedding-3-small
  → configured vector store:
      ChromaDB for local/Docker or persistent backend
      Pinecone for Vercel/full-stack production
```

### Chunking Strategies

| Strategy | Env var | Quality | Speed | Token cost |
|----------|---------|---------|-------|------------|
| Recursive (default) | `CHUNKER_TYPE=recursive` | Good — fixed-size with overlap | Fast | None |
| Semantic | `CHUNKER_TYPE=semantic` | Better — splits at topic boundaries | Slower | Yes (embedding API calls) |

> **Switching strategies requires re-indexing.** Delete all documents via `DELETE /api/documents/{filename}` then re-upload.

### Vector Store Backends

| Backend | `VECTOR_STORE_TYPE` | Persistence | Best for |
|---------|---------------------|-------------|---------|
| ChromaDB (default) | `chroma` | Local filesystem | Development, Docker |
| In-memory | `memory` | Process lifetime | Tests only |
| Vercel Blob | `blob` | Vercel Blob object store | Small serverless demos/fallbacks |
| **Pinecone** | `pinecone` | Managed cloud | Production, high-scale RAG |

Pinecone uses serverless indexes (cosine metric). The index is auto-created on first write if it does not exist. Set `VECTOR_STORE_TYPE=pinecone` as deployment configuration, then enter the Pinecone API key through Settings UI in production. Falls back to `memory` if the effective runtime API key is not configured. Blob remains useful as `FILE_STORE_TYPE=blob` for durable original uploaded files, while `VECTOR_STORE_TYPE=blob` is kept only for small demos or fallback deployments.

---

## Project Structure

```
.
├── api/
│   └── index.py              # Vercel serverless entry — mounts FastAPI app
├── backend/
│   ├── app/
│   │   ├── auth/             # JWT + bcrypt: models, router, utils
│   │   ├── rag/
│   │   │   ├── ingestion.py  # PDF (PyMuPDF/pypdf), TXT, CSV, Excel extractors
│   │   │   ├── chunking.py   # RecursiveCharacterTextSplitter + SemanticChunker
│   │   │   ├── vector_store.py # Chroma/Pinecone/Blob/memory routing + retrieval
│   │   │   ├── pipeline.py   # run_simple_rag() + format_context()
│   │   │   ├── bm25.py       # BM25 lexical search helper
│   │   │   ├── file_store.py # Raw file storage for viewer endpoint
│   │   │   └── scanner.py    # ZIP-bomb, ClamAV, stored prompt-injection checks
│   │   ├── agents/
│   │   │   └── rag_agent.py  # LangGraph 7-node StateGraph + AgentTrace telemetry
│   │   ├── api/              # REST routers: documents, query, settings, guardrails
│   │   ├── guardrails/       # safety.py, store.py, engine.py
│   │   ├── config.py         # pydantic-settings: all tunables from .env
│   │   ├── settings_store.py # Runtime overrides: model, API key, LangSmith
│   │   └── main.py           # FastAPI app: middleware, routers, lifespan
│   ├── tests/
│   │   ├── unit/             # Pure-function tests (282 tests)
│   │   ├── integration/      # FastAPI TestClient, mocked (158 tests)
│   │   └── live/             # Real OpenAI + ChromaDB (23 tests)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # Header · Upload · List · Chat · Modals
│   │   ├── pages/            # LoginPage · DashboardPage
│   │   ├── services/         # Axios client with JWT interceptor + 401 redirect
│   │   ├── store/            # Zustand authStore (sessionStorage-backed)
│   │   └── types/            # TypeScript interfaces
│   ├── tests/unit/           # Vitest + Testing Library (~80 tests)
│   └── tests/e2e/            # Playwright end-to-end (55 tests)
├── docs/                     # Documentation (rendered via Docsify / GitHub Pages)
├── sample-data/              # generate_samples.py (output gitignored)
├── scripts/
│   ├── local/                # setup.sh · dev.sh · deploy-local.sh
│   ├── remote/               # deploy-vercel.sh · redeploy-vercel.sh · undeploy-vercel.sh
│   └── test/                 # run-tests.sh · run-live-tests.sh
├── docker-compose.yml        # Full stack: backend + frontend + ChromaDB volume
└── vercel.json               # Vercel build config, rewrites, security headers
```

See [Agent Pipeline](AGENT-PIPELINE.md) for full node details, search features, limitations, and engineering challenges.
