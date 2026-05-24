# Agentic RAG — Enterprise Document Q&A

An AI agent–based knowledge and decision support system built for the **Edureka / Illinois Tech Generative AI & ML Capstone**. Upload enterprise documents (PDF, TXT, CSV, Excel) and ask natural-language questions — a **7-node LangGraph agent pipeline** retrieves the most relevant content and produces grounded, validated answers via OpenAI GPT-4o-mini.

> **Full documentation, submission reference, and walkthrough:** [GitHub Pages →](https://dev-enthusiast-84.github.io/AILabs/)  
> **Capability Showcase (all 10 tasks, pipeline demo, metrics):** [Capability Showcase →](https://dev-enthusiast-84.github.io/AILabs/pitch.html)

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

Login: `admin` / password shown in startup banner. Alternatives: `make setup && make dev` · `docker compose up --build`

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

`mode="agentic"` (default, 3–5 LLM calls) or `mode="simple"` (single retrieve→generate, ~3× faster). → [Agent Pipeline docs](docs/architecture/AGENT-PIPELINE.md) — per-node inputs/outputs, search features, retry logic, limitations.

---

## Technology Stack

**Backend** — FastAPI · LangGraph · ChromaDB / Pinecone · OpenAI (GPT-4o-mini + text-embedding-3-small)  
**Frontend** — React 18 · TypeScript · Vite · Tailwind CSS · Zustand  
**Auth** — JWT (python-jose) · bcrypt · **Testing** — pytest · Vitest · Playwright · **Deploy** — Docker Compose · Vercel

---

## Environment Variables

Production ignores env-supplied provider credentials — enter OpenAI, Pinecone, Blob, and model settings through the Settings UI after deployment.

→ [Full Environment Variables Reference](docs/deployment/DEPLOY-LOCAL-ENV.md) — all auth, upload, rate-limit, retrieval, chunking, and observability variables.

---

## Submission Reference

| Area | Guides |
|------|--------|
| **System Setup** | [Setup Guide](docs/deployment/SETUP.md) · [Local & Docker](docs/deployment/DEPLOY-LOCAL.md) · [Env Vars](docs/deployment/DEPLOY-LOCAL-ENV.md) |
| **Architecture** | [Architecture](docs/architecture/ARCHITECTURE.md) · [Agent Pipeline](docs/architecture/AGENT-PIPELINE.md) · [Project Structure](docs/architecture/ARCHITECTURE-STRUCTURE.md) |
| **Deployment** | [Deployment Overview](docs/deployment/DEPLOYMENT.md) · [Vercel](docs/deployment/DEPLOY-VERCEL.md) · [Vercel Advanced](docs/deployment/DEPLOY-VERCEL-ADVANCED.md) |
| **Limitations** | [Challenges](docs/project/CHALLENGES.md) · [Operational Limits](docs/deployment/DEPLOY-LIMITS.md) · [Vercel Limits](docs/deployment/DEPLOY-VERCEL.md) |
| **Capstone Audit** | [CAPSTONE-AUDIT.md](docs/project/CAPSTONE-AUDIT.md) — all 10 requirements mapped to implementation, tests, and documentation |

---

## Documentation

| Reference Area | Root Guide |
|----------------|-----------|
| **API** | [API Reference](docs/api/API.md) — endpoints, schemas, voice export, guardrails API |
| **Architecture** | [Architecture](docs/architecture/ARCHITECTURE.md) — system design, agent pipeline, project structure |
| **Deployment** | [Deployment](docs/deployment/DEPLOYMENT.md) — setup, Docker, Vercel, env vars, operational limits |
| **Security** | [Security](docs/security/SECURITY.md) — OWASP controls, guardrails, production hardening |
| **Testing** | [Testing](docs/testing/TESTING.md) — unit, integration, frontend, E2E, coverage |
| **Project** | [Project Reference](docs/project/PROJECT.md) — capstone audit, challenges, SDD, videos, future enhancements |
| **SDD** | [SDD Workflow](docs/project/SDD.md) — Spec-Kit slash commands, brownfield back-specs, governance |
