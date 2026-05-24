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
│   RagasDashboardModal                    │
│   chat/ChatToolbar · ChatMessageList     │
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

Full annotated directory layout → [Project Structure](architecture/ARCHITECTURE-STRUCTURE.md).

Key paths:
- `backend/app/agents/rag_agent.py` — LangGraph 7-node StateGraph
- `backend/app/guardrails/` — safety.py, store.py, engine.py
- `frontend/src/components/chat/` — ChatToolbar, ChatMessageList, ChatComposer
- `frontend/src/components/RagasDashboardModal.tsx` — Ragas quality metrics panel

---

## Voice Export Async Flow

Voice export supports sync (inline audio) and async (202 + job_id) modes. The frontend polls `GET /api/chat/voice/export/jobs/{job_id}` every ~3 seconds until status reaches `succeeded` or a terminal state, with a 120-second timeout. Small non-production exports return audio inline in the same response (synchronous path). Production deployments, explicitly deferred requests (`defer: true`), and large transcripts return `202 Accepted` with a job descriptor; the polling loop in `ChatToolbar` resolves the artifact and triggers download once the job completes.

---

See [Agent Pipeline](architecture/AGENT-PIPELINE.md) for full node details, search features, limitations, and engineering challenges.
