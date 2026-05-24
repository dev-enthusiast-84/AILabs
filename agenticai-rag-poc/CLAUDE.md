# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Default requirements for every change

Apply **all six** for every change, no exceptions:

### 1 — Tests
- Add or update unit/integration/E2E tests for the changed behaviour.
- Backend: `backend/tests/unit/`, `backend/tests/integration/`. Frontend: `frontend/tests/unit/`, `frontend/tests/e2e/`.
- Run the full test suite before marking a task complete.
- **Coverage guardrail**: Backend coverage must remain ≥ 98% (`pytest --cov=app`). All tests must be deterministic and idempotent — no time-dependent, order-dependent, or I/O-racy tests.
- **Never suppress errors** — do not use `try/except pass`, warning filters, or `skipIf` as a substitute for fixing a real error. Diagnose and fix the root cause; consult the user before any workaround.

### 2 — OWASP check
- Review against OWASP Top 10: A01 (access control), A02 (crypto), A03 (injection), A05 (config), A07 (auth), A09 (logging).
- Fix any issue before shipping; document accepted risks in the module docstring. Never hardcode credentials.

### 3 — Performance
- Profile hot paths for I/O, vector ops, LLM calls. Avoid duplicate round-trips. Use `useMemo`/`useCallback` for expensive frontend computations. Lazy-import heavy optional deps.

### 4 — Documentation

| Change type | Files to update |
|-------------|-----------------|
| New API endpoint or schema change | `docs/api/API.md` + `docs/api/API-SCHEMAS.md` |
| New env var | `README.md` + `docs/deployment/DEPLOY-LOCAL.md` + `backend/.env.example` |
| Auth / security control | `docs/security/SECURITY.md` + module docstring |
| Architecture change (service, agent node, store) | `docs/architecture/ARCHITECTURE.md` |
| Agent pipeline change (nodes, search features) | `docs/architecture/AGENT-PIPELINE.md` |
| Docker / local deployment change | `docs/deployment/DEPLOY-LOCAL.md` |
| Vercel deployment change | `docs/deployment/DEPLOY-VERCEL.md` |
| Test strategy change | `docs/testing/TESTING.md` or `docs/testing/TESTING-FRONTEND.md` |
| New Python/npm dependency | `docs/deployment/DEPLOY-LOCAL.md` + `requirements.txt`/`package.json` |
| Guardrail engine change | `docs/security/GUARDRAILS.md` |

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

# Full suite + Docker
bash scripts/test/run-tests.sh && RUN_E2E=true bash scripts/test/run-tests.sh
docker compose up --build                 # full stack :3000 + :8000

# Live tests (real OpenAI + ChromaDB — never in CI)
OPENAI_API_KEY=<key> bash scripts/test/run-live-tests.sh

# Spec-Kit SDD workflow
/speckit-specify [feature] → /speckit-plan → /speckit-tasks → /speckit-implement
make spec-check                           # validate spec format
```

## Architecture

**Backend** — FastAPI + LangGraph + ChromaDB. Entry: `backend/app/main.py`.  
Key modules: `auth/` (JWT+bcrypt), `agents/rag_agent.py` (7-node LangGraph StateGraph), `guardrails/engine.py` (block/redact/flag), `rag/` (ingestion, chunking, vector store, BM25).

**Frontend** — React 18 + TypeScript + Vite + Tailwind CSS. Auth in Zustand `authStore` (sessionStorage); JWT via axios interceptor; 401 → `/login`.

Full reference: `docs/architecture/ARCHITECTURE.md` · `backend/.env.example` · `docs/testing/TESTING.md`.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
`.specify/specs/005-enterprise-production-hardening/plan.md`
<!-- SPECKIT END -->
