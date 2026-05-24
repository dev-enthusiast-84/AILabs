# Agentic RAG — Enterprise Document Q&A

An AI agent–based knowledge and decision support system built for the **Edureka / Illinois Tech Generative AI & ML Capstone**. Upload enterprise documents (PDF, TXT, CSV, Excel) and ask natural-language questions — a **7-node LangGraph agent pipeline** retrieves the most relevant content and produces grounded, validated answers via OpenAI GPT-4o-mini.

> **Full documentation, submission reference, and walkthrough:** [GitHub Pages →](https://dev-enthusiast-84.github.io/AILabs/)  
> **Capability Showcase (all 10 tasks, pipeline demo, metrics):** [Capability Showcase →](https://dev-enthusiast-84.github.io/AILabs/pitch.html)  
> **Capstone submission reference:** [CAPSTONE-AUDIT.md](docs/project/CAPSTONE-AUDIT.md) — all 10 requirements mapped to implementation, tests, and documentation

---

## Quick Navigation

| Getting Started | System | Reference |
|---|---|---|
| [Quick Start](#quick-start) | [Feature Highlights](#feature-highlights) | [Submission Reference](#submission-reference) |
| [Live Demo](#live-demo) | [Access Modes](#access-modes) | [Documentation Index](#documentation) |
| [Deployment](#deployment-steps) | [Agent Pipeline](#agent-pipeline) | [Environment Variables](#key-environment-variables) |
| [SDD Workflow](#spec-driven-development-sdd) | [Technology Stack](#technology-stack) | [Limitations & Challenges](#submission-reference) |

---

## Live Demo

| | |
|--|--|
| **Deployed app** | [agenticai-rag-poc.vercel.app](https://agenticai-rag-poc.vercel.app) |
| **Walkthrough videos** | [GitHub Pages gallery →](https://dev-enthusiast-84.github.io/AILabs/walkthrough/) |

---

## Quick Start

```bash
git clone https://github.com/dev-enthusiast-84/AILabs && cd AILabs/agenticai-rag-poc
bash scripts/local/setup.sh        # auto-detects Python 3.11–3.13, installs deps, copies .env
nano backend/.env                  # optional: OPENAI_API_KEY=<your-key>  (or enter via Settings UI)
bash scripts/local/dev.sh --open   # starts backend :8000 + frontend :5173, opens browser
```

Login: username `admin`, password shown in the startup banner.

```bash
make setup && make dev      # via Makefile
docker compose up --build   # full stack on :3000 + :8000
```

→ [Full Setup Guide](docs/deployment/SETUP.md) — prerequisites, Windows/Linux install, Docker Compose, Vercel.

---

## Feature Highlights

| Feature | Details |
|---------|---------|
| **Document types** | PDF, TXT, CSV, XLSX/XLS |
| **7-node agent pipeline** | Planner → HyDE → Retriever → Grader → Reranker → Generator → Validator |
| **Voice + multilingual chat** | Voice input/playback, English/Spanish/French answers, backend-redacted transcript/audio export |
| **Guest mode** | No credentials needed — TXT uploads, 15-min sessions |
| **Content guardrails** | Configurable block / redact / flag rules on input, output, export, and voice transcript surfaces |
| **Token transparency** | `tokens_used` per response + per-node breakdown via AgentTrace |
| **Production hardening** | Role/session isolation, backend-redacted exports, safe audit logs, readiness endpoint, CSP/Permissions-Policy |
| **Rate limiting** | 10 req/min on login and query endpoints |
| **One-command deploy** | `bash scripts/remote/deploy-vercel.sh` |

---

## Access Modes

| Capability | Guest | Admin |
|------------|:-----:|:-----:|
| Chat against indexed documents | ✅ | ✅ |
| List documents | ✅ | ✅ |
| Upload TXT (max 2 MB) | ✅ | ✅ |
| Upload PDF / CSV / Excel (up to 20 MB) | ❌ | ✅ |
| Delete documents | ❌ | ✅ |
| Set OpenAI / Pinecone / Blob keys | ✅ once / session | ✅ |
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

→ [Agent Pipeline docs](docs/architecture/AGENT-PIPELINE.md) — per-node inputs/outputs, search features, retry logic, limitations.

---

## Technology Stack

**Backend** — FastAPI · LangGraph · ChromaDB / Pinecone · OpenAI (GPT-4o-mini + text-embedding-3-small)  
**Frontend** — React 18 · TypeScript · Vite · Tailwind CSS · Zustand  
**Auth** — JWT (python-jose) · bcrypt  
**Testing** — pytest · Vitest · Playwright  
**Deploy** — Docker Compose · Vercel (serverless)

---

## Key Environment Variables

Production ignores billing-bearing provider values — enter OpenAI, Pinecone, Blob, LangSmith, model, and token settings through the app **Settings UI** after deployment.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Local dev only; production uses Settings UI |
| `SECRET_KEY` | insecure default | JWT signing key — `openssl rand -hex 32` in prod |
| `ADMIN_PASSWORD` | _(auto-generated)_ | Login password — printed at startup in dev |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` (local/Docker), `pinecone` (production/Vercel), `memory` (tests) |
| `FILE_STORE_TYPE` | `local` | `blob` to persist uploaded files for preview/download on Vercel |
| `BLOB_READ_WRITE_TOKEN` | — | Local dev only; production uses Settings UI |
| `PINECONE_API_KEY` | — | Local dev only; production uses Settings UI |

→ [Full Environment Variables Reference](docs/deployment/DEPLOY-LOCAL-ENV.md) — all retrieval, chunking, reranker, LLM, rate-limit, and observability variables.

---

## Submission Reference

Capstone submission requirements map directly to the dedicated documentation below.

### System Setup

Step-by-step installation for macOS, Windows, and Linux, covering Python 3.11–3.13, Node.js 20 LTS+, virtual environment, npm dependencies, `.env` generation, and one-command startup.

| Guide | Covers |
|-------|--------|
| [Setup Guide](docs/deployment/SETUP.md) | Prerequisites, `setup.sh` walkthrough, all platforms |
| [Local & Docker Deployment](docs/deployment/DEPLOY-LOCAL.md) | Dev server, production-like build, Docker Compose |
| [Environment Variables](docs/deployment/DEPLOY-LOCAL-ENV.md) | All `backend/.env` variables with defaults and purpose |

### Architecture

Full system design including component diagram, data-flow from upload through chunking, embedding, retrieval, and generation, frontend auth flow, and storage layer options.

| Guide | Covers |
|-------|--------|
| [Architecture](docs/architecture/ARCHITECTURE.md) | System overview, data-flow diagrams, component responsibilities |
| [Architecture Structure](docs/architecture/ARCHITECTURE-STRUCTURE.md) | Project directory layout, module boundaries |

### Agent Roles

Each of the 7 LangGraph nodes is documented — its purpose, inputs, outputs, and connection to the next node in the reasoning chain.

| Guide | Covers |
|-------|--------|
| [Agent Pipeline](docs/architecture/AGENT-PIPELINE.md) | All 7 nodes, HyDE, RRF fusion, self-RAG grader, reranker, retry loop |

**Pipeline at a glance:**

| Node | Role |
|------|------|
| **Planner** | Rewrites the user question into 3 search variants |
| **HyDE** | Generates a hypothetical answer passage for embedding-space alignment |
| **Retriever** | Fan-out search across all variants; fuses results with RRF (BM25 optional) |
| **Grader** | Self-RAG LLM filter — drops irrelevant chunks before generation (opt-in) |
| **Reranker** | Cross-encoder precision sort of retrieved chunks (opt-in) |
| **Generator** | Produces a grounded answer strictly from retrieved context |
| **Validator** | Independently verifies grounding quality; retries Generator up to 2× |

### Deployment Steps

Four fully scripted deployment targets, each documented end-to-end.

| Guide | Target |
|-------|--------|
| [Local & Docker](docs/deployment/DEPLOY-LOCAL.md) | `dev.sh` hot reload · `deploy-local.sh` production-like build · Docker Compose |
| [Vercel Deployment](docs/deployment/DEPLOY-VERCEL.md) | Full-stack serverless · frontend-only + external backend · interactive deploy |
| [Vercel Advanced](docs/deployment/DEPLOY-VERCEL-ADVANCED.md) | CI/non-interactive deploy · multi-environment · teardown |

**Quick deploy commands:**

```bash
# Vercel (serverless)
bash scripts/remote/deploy-vercel.sh --fullstack          # full-stack, Pinecone default
bash scripts/remote/deploy-vercel.sh --frontend-only \
    --backend-url https://my-api.railway.app              # frontend CDN + external backend
bash scripts/remote/redeploy-vercel.sh --sample-data --sample-topic "Healthcare Policy"
bash scripts/remote/undeploy-vercel.sh

# Docker Compose (persistent ChromaDB)
make docker
make docker-sample-data TOPIC="Healthcare Policy"
```

### Limitations & Challenges

Local and Docker deployments use ChromaDB (writable filesystem). Vercel serverless instances are ephemeral — `/tmp` is not shared — so a file-backed Chroma store loses data across cold starts. Production Vercel deployments use `VECTOR_STORE_TYPE=pinecone` for durable shared vector storage and `FILE_STORE_TYPE=blob` for original file storage, both configurable through the Settings UI without a redeploy.

| Guide | Covers |
|-------|--------|
| [Limitations & Development Challenges](docs/project/CHALLENGES.md) | Serverless persistence, chunking/retrieval, hallucination control, agent complexity, secrets, role isolation, voice security, testing strategy, known limitations |
| [Operational Limits](docs/deployment/DEPLOY-LIMITS.md) | Upload caps, voice export limits, rate limits — all hard-coded values |
| [Vercel Deployment](docs/deployment/DEPLOY-VERCEL.md) | Serverless trade-offs, cold-start latency, 4 MB upload cap on Vercel |

---

## Spec-Driven Development (SDD)

This project uses [Spec-Kit](https://github.com/github/spec-kit) as its SDD framework. Feature specs live in `.specify/specs/`. Run `make spec-check` to validate specs in CI.

→ [SDD Workflow](docs/project/SDD.md) — slash commands, brownfield back-specs, governance, and the 6-step workflow.

---

## Documentation

Setup, architecture, deployment, and limitations docs are organized in the [Submission Reference](#submission-reference) above. The guides below cover the remaining reference areas.

**API**

| Guide | Description |
|-------|-------------|
| [API Reference](docs/api/API.md) | All endpoints, access modes, guest/admin flows |
| [API Schemas & Examples](docs/api/API-SCHEMAS.md) | Request/response examples, AgentTrace, rate limits |

**Security**

| Guide | Description |
|-------|-------------|
| [Security](docs/security/SECURITY.md) | OWASP Top 10 controls, auth, input validation, upload safety |
| [Content Guardrails](docs/security/GUARDRAILS.md) | Rule types, built-ins, UI/API management |

**Testing**

| Guide | Description |
|-------|-------------|
| [Backend Testing](docs/testing/TESTING.md) | Unit + integration test suite, running commands |
| [Frontend & E2E Tests](docs/testing/TESTING-FRONTEND.md) | Playwright, live tests, Ragas evaluation, coverage |
| [Coverage Matrix](docs/testing/COVERAGE-MATRIX.md) | Guardrail, redaction, role/session isolation coverage |

**Project**

| Guide | Description |
|-------|-------------|
| [Capstone Audit](docs/project/CAPSTONE-AUDIT.md) | Edureka task mapping, submission checklist |
| [Spec 005 Compliance](docs/project/SPEC-005-COMPLIANCE.md) | Production-hardening checklist |
| [SDD Workflow](docs/project/SDD.md) | Spec-Kit slash commands, brownfield specs, governance |
