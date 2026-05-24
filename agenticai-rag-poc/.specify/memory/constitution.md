# Agentic RAG — Project Constitution

## I. Testing (NON-NEGOTIABLE)

Every code change MUST include tests. No exceptions.

- Write tests BEFORE implementation (TDD ordering in tasks.md — test tasks precede implementation tasks)
- Unit tests: `backend/tests/unit/` (pure functions, no LLM calls, no network) and `frontend/tests/unit/`
- Integration tests: `backend/tests/integration/` (FastAPI TestClient, all LLM/vector store mocked at session scope via `conftest.py`)
- E2E tests: `frontend/tests/e2e/` (Playwright, requires both servers running)
- Run `pytest tests/unit/ tests/integration/ -v` (backend) and `npm test` (frontend) before marking any task complete
- Live tests (`backend/tests/live/`) require a real `OPENAI_API_KEY` and a running server — run separately via `bash run-live-tests.sh`

**Test count baseline (2026-05-04):** 83 unit + 53 integration + 19 frontend unit + 11 E2E + 23 live = 245 total. New features must add to this count.

## II. Security — OWASP Top 10 (NON-NEGOTIABLE)

Every change MUST be reviewed against OWASP Top 10 before shipping.

| OWASP ID | Key control | Where enforced |
|----------|-------------|----------------|
| A01 Broken Access Control | `require_full_access` dependency on write endpoints; `validate_filename()` for path traversal | `app/auth/utils.py`, `app/guardrails/safety.py` |
| A02 Cryptographic Failures | bcrypt passwords (cost 12); HS256 JWT; `SECRET_KEY` ≥ 32 chars; never log credentials | `app/auth/utils.py`, `app/main.py` |
| A03 Injection | `sanitize_query()` (bleach + 12 injection regexes); Pydantic type/length enforcement | `app/guardrails/safety.py`, all Pydantic models |
| A05 Security Misconfiguration | `security_headers_middleware` (X-Frame-Options, CSP, nosniff); CORS allowlist; Server header stripped | `app/main.py` |
| A07 Auth Failures | Login rate-limited 10/min; uniform error ("Invalid credentials"); JWT 30-min expiry | `app/auth/router.py` |
| A09 Security Logging | `structlog` on every request; never log tokens, passwords, or API keys | `app/main.py`, `app/settings_store.py` |

**Rules:**
- NEVER store or hardcode credentials — always read from environment variables or `settings_store.py`
- Run guardrail engine on ALL query input AND output before returning to client
- Document any accepted security risk in the relevant router/module docstring

## III. Performance

- Profile hot paths when touching I/O, vector operations, or LLM calls
- Lift shared state to avoid duplicate network/DB round-trips (use `@lru_cache` for singletons: `get_settings()`, `get_vector_store()`)
- Use `useMemo`/`useCallback` for expensive frontend computations
- Prefer lazy imports for heavy optional dependencies (e.g. `langchain_chroma`)
- Cap LLM context: `MAX_CONTEXT_CHUNKS=4` chunks max per query; `MAX_COMPLETION_TOKENS=1024`
- Agent singleton (`_AGENT` in `rag_agent.py`) is cleared on settings change — reset is intentional

## IV. Documentation

Update documentation for every user-visible or behavioural change. Use the map below:

| Change type | Files to update |
|-------------|-----------------|
| New API endpoint | `docs/API.md` — add to endpoints table |
| API request/response schema change | `docs/API.md` — update JSON examples |
| Guest vs admin permission change | `README.md` capability matrix + `docs/API.md` |
| New environment variable | `README.md` env vars table + `docs/DEPLOYMENT.md` + `backend/.env.example` |
| New guardrail rule or engine change | `docs/GUARDRAILS.md` |
| Auth / security control change | `docs/SECURITY.md` + module docstring |
| Architecture change | `docs/ARCHITECTURE.md` — diagram + component table |
| New frontend component | `docs/ARCHITECTURE.md` project structure |
| Docker / Vercel change | `docs/DEPLOYMENT.md` |
| Test strategy change | `docs/TESTING.md` |
| Installation step change | `docs/SETUP.md` |

**Rules:**
- Do NOT create new top-level `.md` files — use existing `docs/*.md`
- Add docstrings for every new public function/class
- Keep `README.md` concise: feature matrix, env vars, quick-start commands, links to `docs/`

## V. Deployment

- After any backend change: verify Docker Compose still works (`docker compose up --build`)
- After any new environment variable: add it to the env vars table in `README.md`, `CLAUDE.md`, and `backend/.env.example`
- After any Vercel-affecting change: update `deploy-vercel.sh` / `redeploy-vercel.sh` and note in `PENDING_TASKS.md`
- `VECTOR_STORE_TYPE=memory` for Vercel (ephemeral serverless); `chroma` for Docker/local
- Never commit `backend/.env` — it is gitignored and contains real credentials

## VI. Session Management & Context Snapshot

- Before context limit is reached, write pending tasks to `PENDING_TASKS.md` at the repo root
- Format: task title | status (todo/in-progress/done) | brief description | relevant file paths
- At the start of each new session, read `PENDING_TASKS.md` to resume from the previous session
- Use parallel subagents for independent subtasks (independent = no shared state, no write-after-read ordering)
  - Typical split: one subagent for backend changes, one for frontend changes, one for tests if scope is large
  - Block one subagent on another ONLY when there is a genuine data dependency

## Tech Stack

| Layer | Technology | Key version |
|-------|------------|-------------|
| Backend framework | FastAPI | 0.115.6 |
| Agent pipeline | LangGraph StateGraph | 0.2.73 |
| Vector store | ChromaDB | 0.6.3 |
| LLM provider | OpenAI only | `ChatOpenAI` via langchain-openai |
| Auth | python-jose (JWT) + passlib (bcrypt) | HS256, cost 12 |
| Frontend framework | React | 18.3.1 |
| Frontend build | Vite + TypeScript | 6.0.7 / 5.7.2 |
| State management | Zustand (sessionStorage, per-tab) | 5.0.3 |
| Styling | Tailwind CSS | 3.4.17 |
| Python runtime | 3.11–3.13 (3.14+ blocked by pydantic-core) | |
| Node.js runtime | 20+ (Spec-Kit requirement) | |

## File Placement Conventions

| Concern | Location |
|---------|----------|
| API routers | `backend/app/api/` |
| Auth utilities | `backend/app/auth/` |
| Agent pipeline | `backend/app/agents/rag_agent.py` |
| RAG utilities | `backend/app/rag/` |
| Guardrail logic | `backend/app/guardrails/` |
| Configuration | `backend/app/config.py` (pydantic-settings) |
| React components | `frontend/src/components/` |
| Page components | `frontend/src/pages/` |
| API client | `frontend/src/services/api.ts` |
| TypeScript types | `frontend/src/types/index.ts` |
| Zustand stores | `frontend/src/store/` |
| Backend unit tests | `backend/tests/unit/` |
| Backend integration tests | `backend/tests/integration/` |
| Frontend unit tests | `frontend/tests/unit/` |
| Frontend E2E | `frontend/tests/e2e/` |
| Feature specs | `.specify/specs/[capability]/spec.md` |
| Feature plans | `.specify/specs/[capability]/plan.md` |
| Feature tasks | `.specify/specs/[capability]/tasks.md` |

## Spec-Kit Workflow (SDD)

For every new feature or significant change:

1. `/speckit-specify` — write spec.md (user stories + acceptance scenarios + requirements)
2. `/speckit-plan` — write plan.md (technical approach + contracts/api-spec.json)
3. `/speckit-tasks` — generate tasks.md (TDD-ordered: test tasks numbered before implementation)
4. Implement following tasks.md checkboxes
5. `/speckit-analyze` (optional) — cross-artifact consistency check
6. `/speckit-checklist` (optional) — quality gate before merge

Spec files live in `.specify/specs/[capability]/`. Run `specify check` to validate spec format.

## Governance

This constitution supersedes all other practices. It applies to every session and every agent working on this project.

Any amendment to this constitution requires:
1. A written rationale in the PR description
2. A corresponding update to `CLAUDE.md` to keep both files in sync
3. A note in `PENDING_TASKS.md`

**Version**: 1.0.0 | **Ratified**: 2026-05-04 | **Last Amended**: 2026-05-04
