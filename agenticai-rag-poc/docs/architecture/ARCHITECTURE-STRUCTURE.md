# Project Structure

> [← Home](README.md) · [Architecture](architecture/ARCHITECTURE.md)

Directory layout and component annotations for the full-stack Agentic RAG application.

---

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
│   │   ├── runtime/settings_store.py # Runtime overrides: model, API key, LangSmith
│   │   └── main.py           # FastAPI app: middleware, routers, lifespan
│   ├── tests/
│   │   ├── unit/             # Pure-function tests (282 tests)
│   │   ├── integration/      # FastAPI TestClient, mocked (158 tests)
│   │   └── live/             # Real OpenAI + ChromaDB (23 tests)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatToolbar.tsx        # Mode selector, language picker, export/clear actions
│   │   │   │   ├── ChatMessageList.tsx    # Message bubbles with trace viewer, copy/play actions
│   │   │   │   └── ChatComposer.tsx       # Input box, submit button, voice recording trigger
│   │   │   ├── ChatInterface.tsx          # Root chat container, state orchestration
│   │   │   ├── DocumentUpload.tsx         # Drag-and-drop upload with progress feedback
│   │   │   ├── DocumentList.tsx           # Document list with delete and preview actions
│   │   │   ├── DocumentViewerModal.tsx    # Chunks/file viewer modal
│   │   │   ├── SettingsModal.tsx          # Runtime settings panel (API key, model, pipeline flags)
│   │   │   ├── GuardrailsModal.tsx        # Guardrail rules manager + test console
│   │   │   ├── RagasDashboardModal.tsx    # Ragas quality metrics with manual and auto-trigger (every 50 queries)
│   │   │   ├── Header.tsx                 # App header with nav actions and user info
│   │   │   └── ProtectedRoute.tsx         # JWT-gated route wrapper
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
