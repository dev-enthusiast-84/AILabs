# Implementation Plan: Dual RAG Mode

**Branch**: `002-dual-rag-mode` | **Date**: 2026-05-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-dual-rag-mode/spec.md`

## Summary

Add a `mode` parameter (`"simple"` | `"agentic"`, default `"agentic"`) to the query endpoint.
Simple mode does a single retrieve → generate pass (no planner, no validator) and returns
`validation: "N/A"`. Agentic mode is the existing four-stage pipeline — unchanged.
The UI gains a segmented toggle to select the mode before or between messages; responses
are visually labelled with their mode. Both modes share guardrails and rate limiting.

## Technical Context

**Language/Version**: Python 3.11–3.13 (backend) · TypeScript / React 18 (frontend)
**Primary Dependencies**: FastAPI 0.115, LangGraph 0.2, LangChain-OpenAI, React 18, Tailwind CSS
**Storage**: ChromaDB (persistent) or InMemoryVectorStore (test/Vercel)
**Testing**: pytest (backend unit + integration) · Vitest + Testing Library (frontend unit) · Playwright (E2E)
**Target Platform**: Docker / Vercel serverless (backend) · browser (frontend)
**Project Type**: Web application (REST API + SPA)
**Performance Goals**: Simple mode should return an answer faster than agentic mode (one fewer LLM call)
**Constraints**: Both modes must pass through `sanitize_query()` + guardrail engine; rate limit unchanged
**Scale/Scope**: Single-tenant; existing 267-test baseline must not regress

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Tests exist for every change | ✅ Planned | TDD: test tasks ordered before implementation in tasks.md |
| OWASP A03 — Injection | ✅ | `sanitize_query()` called in both modes; guardrail engine on input + output |
| OWASP A01 — Access Control | ✅ | `get_current_user` dependency unchanged; no new auth bypass |
| OWASP A04 — Resource Limits | ✅ | Rate limit applied to unified endpoint; token budget honoured by `_llm()` |
| OWASP A09 — Security Logging | ✅ | `structlog` events emitted in both pipeline branches |
| Docs updated | ✅ Planned | `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md` |
| No hardcoded credentials | ✅ | API key and model read from `settings_store.py` |

## Project Structure

### Documentation (this feature)

```text
specs/002-dual-rag-mode/
├── plan.md          ← this file
├── research.md      ← Phase 0
├── data-model.md    ← Phase 1
├── contracts/       ← Phase 1 (api-spec.json)
└── tasks.md         ← /speckit-tasks output
```

### Source Code changes

```text
backend/app/
├── api/query.py              ← add mode routing; update QueryRequest + QueryResponse
├── rag/pipeline.py           ← add run_simple_rag() function
└── agents/rag_agent.py       ← no changes (existing pipeline unchanged)

backend/tests/
├── unit/test_pipeline.py     ← new: unit tests for run_simple_rag()
├── integration/test_api_query.py  ← extend: simple-mode, mode field in response
└── live/test_live_agent.py   ← extend: add simple-mode live stage

frontend/src/
├── types/index.ts            ← add mode to QueryRequest + ChatMessage
├── services/api.ts           ← pass mode in ask()
└── components/ChatInterface.tsx  ← mode toggle + labelled responses

frontend/tests/
└── unit/ChatInterface.test.tsx   ← extend: mode toggle behaviour
```

## Complexity Tracking

No constitution violations. No justification table needed.
