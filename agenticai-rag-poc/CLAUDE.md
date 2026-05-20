# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Default requirements for every change

Apply **all six** for every change, no exceptions:

### 1 — Tests
- Add or update unit/integration/E2E tests for the changed behaviour.
- Backend: `backend/tests/unit/`, `backend/tests/integration/`. Frontend: `frontend/tests/unit/`, `frontend/tests/e2e/`.
- Run the full test suite before marking a task complete.

### 2 — OWASP check
- Review against OWASP Top 10: A01 (access control), A02 (crypto), A03 (injection), A05 (config), A07 (auth), A09 (logging).
- Fix any issue before shipping; document accepted risks in the module docstring.
- Never hardcode credentials — always read from env vars or the runtime settings store.

### 3 — Performance
- Profile hot paths for I/O, vector ops, LLM calls. Avoid duplicate round-trips. Use `useMemo`/`useCallback` for expensive frontend computations. Lazy-import heavy optional deps.

### 4 — Documentation

| Change type | Files to update |
|-------------|-----------------|
| New API endpoint or schema change | `docs/API.md` + `docs/API-SCHEMAS.md` |
| New env var | `README.md` + `docs/DEPLOY-LOCAL.md` + `backend/.env.example` |
| Auth / security control | `docs/SECURITY.md` + module docstring |
| Architecture change (service, agent node, store) | `docs/ARCHITECTURE.md` diagram + project structure |
| Agent pipeline change (nodes, search features) | `docs/AGENT-PIPELINE.md` |
| New frontend component | `docs/ARCHITECTURE.md` project structure |
| Docker / local deployment change | `docs/DEPLOY-LOCAL.md` |
| Vercel deployment change | `docs/DEPLOY-VERCEL.md` |
| Test strategy change | `docs/TESTING.md` or `docs/TESTING-FRONTEND.md` |
| New Python/npm dependency | `docs/DEPLOY-LOCAL.md` + `requirements.txt`/`package.json` |
| Guardrail engine change | `docs/GUARDRAILS.md` |

No new top-level `.md` files. Keep `README.md` as the concise entry point only. One-line docstring for every new public function.

### 5 — Deployment
- Verify Docker Compose still works for any backend change: `docker compose up --build`.
- New env var → `README.md` env table + `backend/.env.example`.
- Note any Vercel-affecting change in `PENDING_TASKS.md`.

### 6 — Context snapshot
- Write pending tasks to `PENDING_TASKS.md` before the session context limit is reached.
- Read `PENDING_TASKS.md` at session start to resume prior work.

## Agent parallelism
- Independent subtasks → always spin parallel subagents, never execute sequentially.
- Typical split: one subagent each for backend, frontend, and tests.

## Commands

```bash
# Setup
bash scripts/local/setup.sh              # Python 3.11–3.13, venv, npm ci, .env

# Backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
pytest tests/unit/ -v && pytest tests/integration/ -v
pytest -v                                 # all + HTML report

# Frontend
cd frontend && npm run dev                # :5173, proxies /api → :8000
npm test && npm run test:e2e              # Vitest + Playwright

# Walkthrough video
bash scripts/record-walkthrough.sh --url <app-url> --headed --interactive-settings

# Full suite + Docker
bash scripts/test/run-tests.sh && RUN_E2E=true bash scripts/test/run-tests.sh
docker compose up --build                 # full stack :3000 + :8000

# Live tests (real OpenAI + ChromaDB — never in CI)
export OPENAI_API_KEY=<your-openai-api-key>
bash scripts/test/run-live-tests.sh                    # all suites
bash scripts/test/run-live-tests.sh agent              # 7-node pipeline only
SKIP_API_TESTS=true bash scripts/test/run-live-tests.sh

# Spec-Kit SDD workflow
/speckit-specify [feature] → /speckit-plan → /speckit-tasks → /speckit-implement
make spec-check                           # validate spec format
```

## Architecture

**Backend** — FastAPI + LangGraph + ChromaDB. Entry: `backend/app/main.py`.

- `main.py` — middleware, routers, lifespan. `_WEAK_SECRETS` raises `RuntimeError` (non-dev) or `WARNING` (dev) on empty/default `SECRET_KEY`.
- `config.py` — pydantic-settings; `secret_key` defaults to `""` — must be set via env.
- `auth/` — JWT + bcrypt. `require_full_access` blocks guests on write endpoints. Guest JWT 15 min.
- `rag/ingestion.py` — PDF, TXT, CSV, XLSX extractors.
- `rag/chunking.py` — recursive (default) or semantic chunking.
- `rag/vector_store.py` — ChromaDB singleton; MMR, score-threshold, and plain search modes.
- `rag/pipeline.py` — simple one-shot RAG chain; `format_context()` shared helper.
- `rag/scanner.py` — ZIP-bomb, ClamAV (optional), stored prompt-injection checks before indexing.
- `rag/bm25.py` — in-memory BM25 index for hybrid dense+sparse search.
- `agents/rag_agent.py` — 7-node LangGraph StateGraph: planner→hyde→retriever→grader→reranker→generator→validator. Returns `AgentTrace`.
- `settings_store.py` — runtime overrides for model, retrieval, and generation params.
- `guardrails/engine.py` — configurable block/redact/flag rules on input and output.
- `api/documents.py` — upload/list/delete; guests TXT ≤2 MB; admin delete only.
- `api/query.py` — 10/min rate limit; simple + agentic modes; guests allowed.
- `api/settings.py` — masked key + model; guest one-time JTI gate.

**Frontend** — React 18 + TypeScript + Vite + Tailwind CSS. Auth in Zustand `authStore` (sessionStorage); JWT via axios interceptor; 401 → `/login`. `@vercel/analytics` + `@vercel/speed-insights` in `App.tsx` (no-op outside Vercel).

## Key environment variables

Full reference in `README.md` and `backend/.env.example`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Required for embeddings and LLM |
| `SECRET_KEY` | _(empty — must set)_ | JWT signing key — `openssl rand -hex 32` |
| `ADMIN_PASSWORD` | _(generated)_ | Admin login password — printed at startup |
| `VECTOR_STORE_TYPE` | `chroma` | `memory` for Vercel/tests; `chroma` for persistence |
| `APP_ENV` | `development` | `production` disables API docs + enforces secret checks |
| `CHUNKER_TYPE` | `recursive` | `semantic` for embedding-boundary chunking |
| `RETRIEVER_HYBRID_BM25` | `false` | `true` enables BM25 + dense hybrid search |
| `RELEVANCE_GRADER_ENABLED` | `false` | `true` adds self-RAG chunk filtering |
| `RERANKER_TYPE` | `none` | `cross-encoder` for precision reranking (Docker only) |
| `CLAMAV_HOST` | — | Set to enable ClamAV virus scanning |

## Testing

| Layer | Tests | Notes |
|-------|-------|-------|
| Backend unit | ~280 | Pure functions, no LLM/network |
| Backend integration | ~158 | FastAPI TestClient, all mocked |
| Frontend unit | ~80 | Vitest + Testing Library |
| Frontend E2E | 55 | Playwright, requires running stack |
| Live dependency | 23 | Real OpenAI + ChromaDB, separate run |

Overall coverage ≥92%. Run `cd backend && pytest --cov` for live numbers. Per-module breakdown in `docs/TESTING.md`.

## OWASP controls quick-reference

| Location | Control |
|----------|---------|
| `main.py` | Security headers, CORS, server header stripped, `_WEAK_SECRETS` guard |
| `auth/router.py` | Login rate limit 10/min, uniform error message |
| `auth/utils.py` | bcrypt passwords, JWT 45-min admin / 15-min guest |
| `api/query.py` | Query rate limit 10/min |
| `api/documents.py` | File size cap, extension allowlist, guest upload rate limit 5/min |
| `guardrails/safety.py` | bleach XSS strip, injection regex, path traversal block |
| `guardrails/engine.py` | Configurable block/redact/flag rules on input + output |
| `rag/scanner.py` | ZIP-bomb detection, ClamAV scan, stored prompt-injection check |
| `config.py` | Token budget, max chunk context |

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
`.specify/specs/005-enterprise-production-hardening/plan.md`
<!-- SPECKIT END -->
