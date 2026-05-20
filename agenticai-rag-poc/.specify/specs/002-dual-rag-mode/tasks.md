# Tasks: Dual RAG Mode

**Input**: Design documents from `specs/002-dual-rag-mode/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api-spec.json ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no pending dependencies)
- **[Story]**: User story this task belongs to
- TDD order: test tasks are numbered **before** the implementation tasks they cover

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared type and schema changes that all stories depend on.

- [x] T001 Update `QueryRequest` Pydantic model — add `mode: Literal["simple","agentic"] = "agentic"` in `backend/app/api/query.py`
- [x] T002 Update `QueryResponse` Pydantic model — add `mode: str` field in `backend/app/api/query.py`
- [x] T003 [P] Update frontend `QueryRequest` interface — add `mode?: "simple" | "agentic"` in `frontend/src/types/index.ts`
- [x] T004 [P] Update frontend `QueryResponse` interface — add `mode: string` in `frontend/src/types/index.ts`
- [x] T005 [P] Update frontend `ChatMessage` interface — add `mode?: string` in `frontend/src/types/index.ts`
- [x] T006 Update `queryApi.ask()` to forward `mode` in request body in `frontend/src/services/api.ts`

**Checkpoint**: Shared types ready — backend and frontend compile with the new fields.

---

## Phase 2: Foundational (Simple RAG Engine)

**Purpose**: The `run_simple_rag()` function is a shared dependency for US1 and must be tested and in place before the endpoint wires it up.

**⚠️ CRITICAL**: US1 integration tests depend on this phase.

### Tests — Simple RAG engine

- [x] T007 Write unit tests for `run_simple_rag()` in `backend/tests/unit/test_pipeline.py` — cover: returns `answer`, `sources`, `validation="N/A"`, `mode="simple"`, `tokens_used > 0`; mock `similarity_search` and LLM chain

### Implementation — Simple RAG engine

- [x] T008 Implement `run_simple_rag(question: str) -> dict` in `backend/app/rag/pipeline.py` — single retrieve → generate pass using `similarity_search()`, `format_context()`, and a direct `ChatPromptTemplate | _llm()` chain; return `{"answer", "sources", "validation": "N/A", "mode": "simple", "tokens_used"}`

**Checkpoint**: `pytest tests/unit/test_pipeline.py` passes; `run_simple_rag()` is callable.

---

## Phase 3: User Story 1 — Simple RAG Endpoint (Priority: P1) 🎯 MVP

**Goal**: `POST /api/query/` with `mode="simple"` routes through `run_simple_rag()` and returns a response with `validation="N/A"` and `mode="simple"`.

**Independent Test**: Send `{"question": "...", "mode": "simple"}` to the endpoint → get `200` with `validation="N/A"` and `mode="simple"`.

### Tests for US1

- [x] T009 [P] [US1] Write integration tests for simple mode in `backend/tests/integration/test_api_query.py`:
  - `test_simple_mode_returns_na_validation` — mock `run_simple_rag`, assert `validation="N/A"`, `mode="simple"`
  - `test_simple_mode_calls_simple_rag_not_agent` — mock both pipelines, assert only `run_simple_rag` is called
  - `test_simple_mode_guardrails_applied` — blocked input returns 400 in simple mode too
  - `test_simple_mode_token_count_returned` — `tokens_used` is int ≥ 0

### Implementation for US1

- [x] T010 [US1] Update `query_documents` endpoint in `backend/app/api/query.py` — branch on `body.mode`: call `run_simple_rag()` for `"simple"`, `run_agent()` for `"agentic"`; include `mode` in the returned `QueryResponse`

**Checkpoint**: `pytest tests/integration/test_api_query.py` passes; simple mode endpoint works end-to-end.

---

## Phase 4: User Story 2 — Agentic Mode Echoes `mode` Field (Priority: P1)

**Goal**: Existing agentic pipeline responses now include `mode="agentic"` in the response body. Zero behaviour regression.

**Independent Test**: Send `{"question": "..."}` (no mode) → response includes `mode="agentic"` alongside existing `validation` badge.

### Tests for US2

- [x] T011 [P] [US2] Extend existing agentic-mode tests in `backend/tests/integration/test_api_query.py`:
  - `test_agentic_mode_is_default` — omit `mode`, assert `mode="agentic"` in response
  - `test_explicit_agentic_mode` — send `mode="agentic"`, assert `mode="agentic"` and `validation` in `{"VALID","NEEDS_REVISION"}`
  - `test_invalid_mode_rejected` — send `mode="turbo"`, assert `422`

### Implementation for US2

- [x] T012 [US2] Update `run_agent()` return dict in `backend/app/agents/rag_agent.py` to include `"mode": "agentic"` — the `QueryResponse` already has the field after T002

**Checkpoint**: All existing query tests still pass; agentic mode responses include `mode` field.

---

## Phase 5: User Story 3 — Mode Selector UI (Priority: P2)

**Goal**: Chat header shows a "Simple / Agentic" toggle. Selected mode is passed in each request. Responses are labelled with their mode; validation badge is hidden for simple-mode responses.

**Independent Test**: Toggle to Simple, send a message — response footer shows "Simple RAG" label and no validation badge. Toggle back to Agentic — next response shows validation badge.

### Tests for US3

- [x] T013 [P] [US3] Write / extend frontend unit tests in `frontend/tests/unit/ChatInterface.test.tsx`:
  - `renders mode toggle with Agentic selected by default`
  - `clicking Simple sets mode to simple and passes it in query request`
  - `simple-mode response shows mode label and no validation badge`
  - `agentic-mode response shows validation badge`

### Implementation for US3

- [x] T014 [P] [US3] Add mode toggle (segmented control: "⚡ Simple" | "🤖 Agentic") to `ChatInterface.tsx` header — `useState<"simple"|"agentic">("agentic")`; pass `mode` into `queryApi.ask()`
- [x] T015 [US3] Update assistant message bubble in `ChatInterface.tsx` — add mode label ("⚡ Simple RAG" / "🤖 Agentic RAG") in the message footer; show validation badge only when `msg.mode === "agentic"`
- [x] T016 [US3] Store `mode` from response on the `ChatMessage` object in `ChatInterface.tsx` so the label is accurate even in mixed-mode conversations

**Checkpoint**: `npm test` passes; UI toggle works, mode label appears on every assistant message.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T017 [P] Update `docs/API.md` — document `mode` field in `POST /api/query/` request and response; add 422 row for invalid mode value
- [x] T018 [P] Update `docs/ARCHITECTURE.md` — update query flow diagram to show the mode branch; note `run_simple_rag()` in the RAG utilities row
- [x] T019 [P] Update `docs/TESTING.md` — update sample queries table to show both modes; add simple-mode row to live test section
- [x] T020 [P] Update live test default question + agent seed docs to use Generative AI content (already done) — update `LIVE_QUESTION` hint in `run-live-tests.sh` to mention mode flag; update `SKIP_API_TESTS` note
- [x] T021 Update `backend/tests/live/test_live_agent.py` — add a simple-mode stage (Stage 6) that calls the compiled graph bypassed via `run_simple_rag()` directly with the prompt question
- [x] T022 Run full test suite and confirm no regressions: `bash run-tests.sh` (backend unit + integration + frontend unit)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (types must exist before engine uses them)
- **Phase 3 (US1)**: Depends on Phase 2 — `run_simple_rag()` must exist
- **Phase 4 (US2)**: Depends on Phase 1 — only adds `mode` echo to existing return dict
- **Phase 5 (US3)**: Depends on Phases 1 + 3 + 4 — UI depends on both modes working
- **Phase 6 (Polish)**: Depends on all prior phases

### Parallel Opportunities Within Phases

- **Phase 1**: T003, T004, T005 (frontend types) can run in parallel with T001, T002 (backend types)
- **Phase 3 + 4**: T009 and T011 (test writing) can run in parallel after Phase 1/2 complete
- **Phase 5**: T013 (tests) and T014 (toggle implementation) can run in parallel

---

## Parallel Example: US1 + US2 Together

```
After Phase 2 completes:
  Subagent A → T009, T010  (US1 — simple mode endpoint)
  Subagent B → T011, T012  (US2 — agentic mode echo)
Both complete → T013–T016  (US3 — UI)
```

---

## Implementation Strategy

### MVP (US1 + US2 only — no UI changes)

1. Phase 1 (T001–T006)
2. Phase 2 (T007–T008)
3. Phase 3 (T009–T010)
4. Phase 4 (T011–T012)
5. **Validate**: `bash run-tests.sh` passes; API works with `curl`

### Full delivery (adds UI mode selector)

6. Phase 5 (T013–T016)
7. Phase 6 (T017–T022)
