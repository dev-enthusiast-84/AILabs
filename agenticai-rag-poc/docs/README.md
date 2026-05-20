# Agentic RAG — Enterprise Document Q&A

An AI agent–based knowledge and decision support system built for the **Edureka / Illinois Tech Generative AI & ML Capstone**. Upload enterprise documents (PDF, TXT, CSV, Excel) and ask natural-language questions. A **7-node LangGraph pipeline** retrieves the most relevant content from the configured vector store and produces grounded, validated answers via OpenAI GPT-4o-mini.

---

## Quick Start

```bash
git clone https://github.com/dev-enthusiast-84/AILabs && cd AILabs/agenticai-rag-poc
bash scripts/local/setup.sh        # creates venv, installs deps, copies .env
nano backend/.env                  # optional local-only: OPENAI_API_KEY=<your-openai-api-key>
bash scripts/local/dev.sh --open   # starts both servers + opens browser
```

> **Login:** username `admin`, password printed at startup. Retrieve any time: `grep ADMIN_PASSWORD backend/.env`.

**Makefile shortcuts:** `make setup` · `make dev` · `make dev-open` · `make test` · `make docker`

---

## Feature Highlights

| Feature | Details |
|---------|---------|
| **Document types** | PDF, TXT, CSV, XLSX/XLS |
| **7-node agent pipeline** | Planner → HyDE → Retriever → Grader → Reranker → Generator → Validator |
| **Voice + multilingual chat** | Voice input/playback, English/Spanish/French answers, transcript/audio export |
| **Guest mode** | No credentials needed; TXT uploads, 15-min sessions |
| **Content guardrails** | Configurable block / redact / flag rules on input, output, export, and voice transcript surfaces |
| **Token transparency** | `tokens_used` per response + per-node breakdown via AgentTrace |
| **Production hardening** | Role/session isolation, backend-redacted exports, safe audit logs, readiness, CSP/Permissions-Policy |
| **Rate limiting** | 10 req/min on login and query endpoints |
| **Vercel deployment** | One-command deploy: `bash scripts/remote/deploy-vercel.sh` |

---

## Access Modes

| Capability | Guest | Admin |
|------------|:-----:|:-----:|
| Chat against indexed documents | ✅ | ✅ |
| List documents | ✅ | ✅ |
| Upload TXT (max 2 MB) | ✅ | ✅ |
| Upload PDF / CSV / Excel (up to 20 MB) | ❌ | ✅ |
| Delete documents | ❌ | ✅ |
| Set OpenAI/Pinecone/Blob keys | ✅ once / session | ✅ |
| Change LLM model | ✅ once / session | unlimited |
| Session duration | 15 min | 45 min |

---

## Agent Pipeline

```
User question
   ▼ [Planner]    — multi-query rewrite + 2 alternative phrasings
   ▼ [HyDE]       — hypothetical document embedding for better recall
   ▼ [Retriever]  — fan-out across all queries + RRF fusion (BM25 optional)
   ▼ [Grader]     — self-RAG relevance filter (opt-in)
   ▼ [Reranker]   — cross-encoder precision sort (opt-in)
   ▼ [Generator]  — GPT-4o-mini grounded strictly to retrieved context
   ▼ [Validator]  — VALID or NEEDS_REVISION (≤ 2 retries → Generator)
   ▼ { answer, sources, validation, tokens_used, mode, trace }
```

`mode="agentic"` (default, 3–5 LLM calls) or `mode="simple"` (single retrieve→generate, ~3× faster).

---

## Key Environment Variables

Production ignores billing-bearing provider env values. Enter OpenAI, Pinecone,
Blob, LangSmith, model, and token settings through the app Settings UI.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Local development only; production uses Settings UI |
| `SECRET_KEY` | insecure default | JWT signing key — rotate with `openssl rand -hex 32` |
| `ADMIN_PASSWORD` | _(auto-generated)_ | Login password — printed at startup |
| `VECTOR_STORE_TYPE` | `chroma` | `pinecone` for production/Vercel; `blob` only for small Vercel Blob vector demos/fallbacks; `memory` for tests; `chroma` for local persistence |
| `FILE_STORE_TYPE` | `local` | Set to `blob` to persist original uploaded files for preview/download on Vercel |
| `BLOB_READ_WRITE_TOKEN` | — | Local development only; production uses Settings UI |
| `PINECONE_API_KEY` | — | Local development only; production uses Settings UI |
| `CHUNKER_TYPE` | `recursive` | `semantic` for embedding-boundary chunking |
| `RETRIEVER_HYBRID_BM25` | `false` | `true` enables BM25 + dense hybrid search |
| `RERANKER_TYPE` | `none` | `cross-encoder` for precision reranking (Docker only) |
| `RELEVANCE_GRADER_ENABLED` | `false` | `true` adds self-RAG chunk filtering |

---

## Engineering Challenge: Durable RAG Storage on Serverless

ChromaDB is ideal for local and Docker deployments because it persists vectors to a writable filesystem. Vercel full-stack deployments do not provide durable shared filesystem storage: serverless instances can cold-start, scale horizontally, and lose `/tmp` state. That made uploaded documents appear intermittently across list, preview, query, and delete requests.

The production Vercel path therefore uses `VECTOR_STORE_TYPE=pinecone`: chunk embeddings are stored in Pinecone, giving all function instances a shared durable vector layer. The active vector store type is environment/deployment configuration only. Pinecone connection details can be supplied in environment variables or through the Settings UI, including guest mode’s one-time settings flow. Blob storage is still recommended as `FILE_STORE_TYPE=blob` for durable original uploaded files such as previews and downloads; its read/write token can also be supplied through Settings UI when Blob is enabled. `VECTOR_STORE_TYPE=blob` remains available only as a Vercel-native small-demo vector fallback; larger production systems should pair a hosted vector database with Blob/S3-style object storage for originals.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Setup Guide](SETUP.md) | Prerequisites + quick start for all platforms |
| [Capstone Audit](CAPSTONE-AUDIT.md) | Edureka task mapping, submission checklist, engineering challenges |
| [Architecture](ARCHITECTURE.md) | System design, ingestion flow, project structure |
| [Agent Pipeline](AGENT-PIPELINE.md) | 7-node pipeline details, search features, limitations |
| [Local & Docker](DEPLOY-LOCAL.md) | Dev server, production build, Docker Compose |
| [Vercel Deployment](DEPLOY-VERCEL.md) | Modes, step-by-step, CI deploy, teardown |
| [API Reference](API.md) | All endpoints, access modes, guest/admin flows |
| [API Schemas & Examples](API-SCHEMAS.md) | Request/response examples, AgentTrace, rate limits |
| [Backend Testing](TESTING.md) | Unit + integration test suite, running commands |
| [Frontend & E2E Tests](TESTING-FRONTEND.md) | Playwright, live tests, Ragas evaluation, coverage |
| [Coverage Matrix](COVERAGE-MATRIX.md) | Guardrail, redaction, role/session isolation, and deterministic E2E coverage |
| [Spec 005 Compliance](SPEC-005-COMPLIANCE.md) | Production-hardening checklist plus optional cloud extension points |
| [Security](SECURITY.md) | OWASP Top 10 controls, auth, input validation, upload safety |
| [Content Guardrails](GUARDRAILS.md) | Rule types, built-ins, UI/API management |
| [SDD Workflow](SDD.md) | Spec-Kit slash commands, brownfield specs, governance |
