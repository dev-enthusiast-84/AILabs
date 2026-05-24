# Tasks: Chunk-Level Citations + Retriever Team Fan-Out

**Input**: `.specify/specs/010-chunk-level-citations/spec.md`  
**Status**: Implemented and verified with deterministic unit/integration/frontend tests  
**Scope**: Query citation payloads, source normalization, frontend citation cards, and deterministic Retriever Team fan-out.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when files do not overlap.
- **Story**: US1 = exact evidence, US2 = full document access, US3 = role/session safety, US4 = Retriever Team determinism.
- TDD order: tests are listed before the implementation they cover.

---

## Phase 1: Backend Citation Contract

- [x] T001 [US1] Add unit coverage in `backend/tests/unit/test_pipeline.py` for stable source ordering and citation construction from `source`, `filename`, `chunk_index`, `raw_chunk`, page markers, and sheet markers.
- [x] T002 [US1] Implement shared citation helpers in `backend/app/rag/pipeline.py`: `stable_sources()` and `build_source_citations()`.
- [x] T003 [US1] Return `citations` from `run_simple_rag()` while preserving legacy `sources`.
- [x] T004 [US1] Return `citations` from `run_agent()` and carry citation state through retriever, grader, and reranker nodes.

## Phase 2: API Normalization And Data-Exposure Controls

- [x] T005 [US3] Add query integration coverage for admin session-prefixed citation normalization in `backend/tests/integration/test_api_query.py`.
- [x] T006 [US3] Add query integration coverage for guest cross-session citation filtering in `backend/tests/integration/test_api_query.py`.
- [x] T007 [US1] Add simple-mode endpoint coverage to assert simple responses use the same citation contract as agentic responses.
- [x] T008 [US3] Normalize citations through the same role/session display rules as `sources` in `backend/app/api/query.py`.
- [x] T009 [US3] Redact and bound citation excerpts before serialization; strip contextual document headers and internal session source keys.

## Phase 3: Frontend Citation Experience

- [x] T010 [US1] Update frontend query/chat types in `frontend/src/types/index.ts` with `SourceCitation` and optional `citations`.
- [x] T011 [US1] Render citation cards with filename, page/section/chunk location, and bounded excerpt in `frontend/src/components/chat/ChatMessageList.tsx`.
- [x] T012 [US2] Preserve legacy source buttons as fallback and route citation clicks through the existing document viewer.
- [x] T013 [US1] Add frontend unit coverage in `frontend/tests/unit/ChatInterface.test.tsx` for citation cards replacing duplicate source pills.

## Phase 4: Retriever Team Fan-Out

- [x] T014 [US4] Add unit coverage for retrieval-agent task deduplication and query-text preservation in `backend/tests/unit/test_rag_agent.py`.
- [x] T015 [US4] Add unit coverage for deterministic RRF ordering when parallel retrieval tasks complete out of order.
- [x] T016 [US4] Implement `RetrievalAgentTask` and `_retrieval_agent_tasks()` in `backend/app/agents/rag_agent.py`.
- [x] T017 [US4] Update `retriever_node()` to fan out named retrieval-agent tasks (`primary`, `variant_n`, `hyde`) while preserving stable RRF input order.

## Phase 5: Documentation And Specs

- [x] T018 [P] Update `.specify/specs/query-pipeline/spec.md` with the seven-node pipeline, Retriever Team fan-out, citation contract, and safety requirements.
- [x] T019 [P] Update `.specify/specs/010-chunk-level-citations/spec.md` with deterministic Retriever Team requirements and verification criteria.
- [x] T020 [P] Update `docs/API-SCHEMAS.md` with citation examples, field reference, and safety rules.
- [x] T021 [P] Update `docs/AGENT-PIPELINE.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, and `docs/CAPSTONE-AUDIT.md` for Retriever Team + citations.
- [x] T022 [P] Update `docs/TESTING.md` and `docs/TESTING-FRONTEND.md` with the new test coverage.

## Phase 6: Verification

- [x] T023 Run focused backend citation + Retriever Team tests:
  `backend/.venv/bin/python -m pytest backend/tests/integration/test_api_query.py::test_query_normalizes_chunk_level_citations backend/tests/integration/test_api_query.py::test_query_filters_guest_citations_to_current_session backend/tests/integration/test_api_query.py::test_simple_mode_returns_chunk_level_citations backend/tests/unit/test_rag_agent.py::TestRetrieverFanOut -q -o addopts=`
- [x] T024 Run full query integration coverage:
  `backend/.venv/bin/python -m pytest backend/tests/integration/test_api_query.py -q -o addopts=`
- [x] T025 Run backend RAG unit coverage:
  `backend/.venv/bin/python -m pytest backend/tests/unit/test_rag_agent.py backend/tests/unit/test_pipeline.py -q -o addopts=`
- [x] T026 Run frontend citation-card unit coverage:
  `npm test -- --run tests/unit/ChatInterface.test.tsx -t "renders chunk-level citations"`
- [x] T027 Run formatting safety check:
  `git diff --check`

## External Gates

- [ ] T028 Run live provider verification: `cd backend && bash ../scripts/test/run-live-tests.sh agent`.
  **Blocked locally**: requires `OPENAI_API_KEY`; no key is present in this environment.
- [ ] T029 Run Docker startup verification: `docker compose up --build`, health check, and `docker compose down`.
  **Blocked locally**: Docker CLI is not installed in this environment.

These external gates are intentionally left unchecked because they require local credentials or tooling outside the current workspace. They should be completed by the operator before release if live-provider or Docker deployment assurance is required.
