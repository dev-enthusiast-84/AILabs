# Tasks: LangGraph / LangChain Ecosystem Upgrade

**Input**: Design documents from `.specify/specs/005-enterprise-production-hardening/`  
**Prerequisites**: plan.md ✓ | spec.md ✓ | research.md ✓ | data-model.md ✓ | contracts/requirements-target.txt ✓

**Scope**: This tasks.md covers the LangGraph/LangChain upgrade (Foundational phase for spec 005).  
Enterprise production hardening user stories (US1–US7) follow in subsequent sessions once the  
dependency foundation is stable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label — US0 = foundational upgrade, US6 = Operational Readiness (spec.md)
- Exact file paths included in every task description

---

## Phase 1: Setup (Rollback Preparation)

**Purpose**: Capture a clean baseline and prepare rollback artefacts before any file changes.  
Every step in this phase is a safety net for the 3-level rollback plan in plan.md.

- [x] T001 Confirm current test baseline passes: run `cd backend && source .venv/bin/activate && pytest tests/unit/ tests/integration/ -v --tb=short` and record pass count (expect 280 unit + 158 integration)
- [x] T002 Record current installed package versions: run `pip freeze | grep -E "langchain|langgraph|openai|chromadb"` and save output to `.specify/specs/005-enterprise-production-hardening/baseline-packages.txt`
- [x] T003 [P] Verify git working tree is clean: run `git status` — commit or stash any uncommitted changes before proceeding so Level 3 rollback is safe

---

## Phase 2: Foundational (TDD Gate — Tests Before Code)

**Purpose**: Write and verify the regression tests that will guard the upgrade.  
**⚠️ CRITICAL**: These tests must exist and produce a known result BEFORE any package version changes.  
No upgrade work begins until this phase is complete.

- [x] T004 Verify existing compile test covers the new entry-point pattern: open `backend/tests/unit/test_rag_agent.py` and confirm `test_graph_compiles_without_error` calls `build_agent_graph()` or equivalent and asserts no exception — if absent, add it
- [x] T005 Add smoke-import test for `get_openai_callback` in `backend/tests/unit/test_rag_agent.py`: assert `from langchain_community.callbacks import get_openai_callback` does not raise `ImportError` — this test must PASS on current deps, then PASS again after upgrade
- [x] T006 [P] Add smoke-import test for `langchain_chroma.Chroma` in a new test `backend/tests/unit/test_vector_store_imports.py`: assert `from langchain_chroma import Chroma` does not raise and `Chroma` is a class
- [x] T007 Run `pytest tests/unit/ -v -k "compile or import" --tb=short` and confirm T004–T006 tests pass on current deps — record as green baseline

**Checkpoint**: TDD gate complete — regression tests are green on current deps.

---

## Phase 3: Code Fix (US0 — Confirmed Breaking Change)

**Purpose**: Apply the single confirmed API-removal fix BEFORE bumping package versions,  
so the code is compatible with both 0.2.x (still installed) and 1.x (coming).

- [x] T008 In `backend/app/agents/rag_agent.py` line 64: add `START` to the langgraph import — change `from langgraph.graph import END, StateGraph` to `from langgraph.graph import END, START, StateGraph`
- [x] T009 In `backend/app/agents/rag_agent.py` line 645: replace `graph.set_entry_point("planner")` with `graph.add_edge(START, "planner")`
- [x] T010 Run `pytest tests/unit/ -v -k "compile or route or agent" --tb=short` to confirm the graph still compiles and existing route tests pass with the new entry-point style

**Checkpoint**: Code fix applied and verified on current langgraph 0.2.73 — graph compiles cleanly.

---

## Phase 4: Dependency Upgrade (US0 — Version Bumps)

**Purpose**: Bump all seven packages together (they share a hard `langchain-core>=1.4.0` boundary  
and cannot be upgraded one at a time). Remove the bridge pin and suppression filters added in the  
previous session.

- [x] T011 Update `backend/requirements.txt`: apply the following changes per `contracts/requirements-target.txt`:
  - Change `langchain==0.3.18` → `langchain==1.3.1`
  - Change `langchain-core==0.3.86` → `langchain-core==1.4.0`
  - Change `langchain-openai==0.3.6` → `langchain-openai==1.2.1`
  - Change `langchain-community==0.3.17` → `langchain-community==0.4.1`
  - Change `langgraph==0.2.73` → `langgraph==1.2.0`
  - Add `langchain-text-splitters==1.1.2` (new package, split from langchain)

- [x] T012 Update `backend/requirements-dev.txt`: apply the following changes:
  - Change `langchain==0.3.18` → `langchain==1.3.1`
  - Change `langchain-openai==0.3.6` → `langchain-openai==1.2.1`
  - Change `langchain-community==0.3.17` → `langchain-community==0.4.1`
  - Change `langchain-chroma==0.2.2` → `langchain-chroma==1.1.0`
  - Change `langchain-experimental==0.3.4` → `langchain-experimental==0.4.1`
  - Change `langgraph==0.2.73` → `langgraph==1.2.0`
  - Add `langchain-text-splitters==1.1.2`
  - Change `openai==1.61.1` → `openai==2.37.0` (forced by langchain-openai 1.2.1)

- [x] T013 [P] Remove the bridge warning suppression added in the previous session — these are now obsolete:
  - In `backend/pytest.ini`: remove the line `ignore::langchain_core._api.deprecation.LangChainPendingDeprecationWarning`
  - In `backend/tests/live/conftest.py`: remove the `warnings.filterwarnings(...)` block for `LangChainPendingDeprecationWarning` (lines added in prior session) and the `import warnings` line if it was added solely for that filter

- [x] T014 Install the new dependencies: run `cd backend && source .venv/bin/activate && pip install -r requirements-dev.txt` and confirm it completes without resolution errors

**Checkpoint**: New packages installed. No rollback yet — T015–T016 verify before committing.

---

## Phase 5: Import Verification (US0 — Verify At Runtime)

**Purpose**: Confirm the two "verify-at-runtime" items from research.md resolve cleanly  
before running the full suite. Fix if needed; update test mocks to match.

- [x] T015 Verify `get_openai_callback` import path in the newly installed environment: run `python -c "from langchain_community.callbacks import get_openai_callback; print('OK')"` inside the venv — if it raises `ImportError`, update the import in `backend/app/agents/rag_agent.py:58` and `backend/app/rag/pipeline.py:15` to the new path (likely `langchain_community.callbacks.openai_info`) and update the four test mocks in `backend/tests/unit/test_rag_agent.py` at lines 165, 195, 443, 472 to patch the new module path

- [x] T016 [P] Verify `langchain_chroma.Chroma` constructor compatibility: run `python -c "from langchain_chroma import Chroma; print(Chroma.__module__)"` inside the venv — if it raises, inspect `backend/app/rag/vector_store.py:286` and update the `Chroma(...)` constructor kwargs to match langchain-chroma 1.x API (typically `persist_directory` and `embedding_function` args are unchanged; `client_settings` may differ)

**Checkpoint**: Both import paths verified. Any needed fixes applied and tested locally.

---

## Phase 6: Full Test Suite (US0 / US6 — Verification Gate)

**Purpose**: Confirm zero regressions across unit and integration layers.  
This is the primary go/no-go gate before Docker and live testing.

- [x] T017 Run the full backend unit test suite: `cd backend && pytest tests/unit/ -v --tb=short` — all tests must pass; any failure triggers Level 2 rollback per plan.md

- [x] T018 [P] Run the full backend integration test suite: `cd backend && pytest tests/integration/ -v --tb=short` — all tests must pass; any failure triggers Level 2 rollback

- [ ] T019 Run the live agent pipeline test: `cd backend && bash ../scripts/test/run-live-tests.sh agent` — all 6 tests must pass with **0 warnings** (the `LangChainPendingDeprecationWarning` must no longer appear) — **EXTERNAL GATE: requires OPENAI_API_KEY; current environment has no key**

**Checkpoint**: Full test suite green on new deps. Ready for Docker and deployment verification.

---

## Phase 7: Deployment Verification (US6 — Operational Readiness)

**Purpose**: Confirm the upgraded stack builds and starts cleanly in the Docker environment.

- [ ] T020 Build and start the full stack: run `docker compose up --build` from the project root — both backend (:8000) and frontend (:3000) containers must start without errors — **EXTERNAL GATE: Docker CLI is not installed in the current environment**

- [ ] T021 [P] Verify the health endpoint responds after Docker start: run `curl -sf http://localhost:8000/api/health` — expect HTTP 200 with a JSON body; any non-200 triggers investigation before proceeding — **EXTERNAL GATE: blocked until T020 can run**

- [ ] T022 Stop Docker containers: run `docker compose down` — **EXTERNAL GATE: blocked until T020 can run**

**Checkpoint**: Docker build passes. Upgrade is functionally complete.

---

## Phase 8: Polish & Documentation (US6)

**Purpose**: Update all documentation that references the old LangGraph/LangChain versions  
so future agents and developers have accurate context.

- [x] T023 Update `CLAUDE.md` constitution tech-stack table: change `| Agent pipeline | LangGraph StateGraph | 0.2.73 |` to `1.2.0` and update the `langchain` row from `0.3.18` to `1.3.1`

- [x] T024 [P] Update `docs/ARCHITECTURE.md` tech-stack section: update the LangGraph and LangChain version references to 1.2.0 and 1.3.1 respectively

- [x] T025 [P] Update `backend/.env.example` if any new env vars were introduced by the upgrade (expect none — verify by scanning the langchain-core 1.x and langgraph 1.x changelogs for new required config)

- [x] T026 Update `PENDING_TASKS.md` at the project root: mark the LangGraph upgrade as complete, note that enterprise production hardening user stories US1–US7 are next

**Checkpoint**: Documentation complete. PR ready for review.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (TDD Gate)**: Depends on Phase 1 completion — must confirm green baseline first
- **Phase 3 (Code Fix)**: Depends on Phase 2 — apply fix only after baseline tests exist
- **Phase 4 (Version Bumps)**: Depends on Phase 3 — bump versions only after code is compatible
- **Phase 5 (Import Verification)**: Depends on Phase 4 — verify only after install completes
- **Phase 6 (Test Suite)**: Depends on Phase 5 — run suite only after imports are clean
- **Phase 7 (Docker)**: Depends on Phase 6 — Docker gate after test suite passes
- **Phase 8 (Docs)**: Depends on Phase 7 — document only after deployment verified

### Rollback Decision Points

| After phase | Trigger | Action |
|-------------|---------|--------|
| Phase 2 | Baseline tests fail | Investigate; fix existing code before proceeding |
| Phase 3 | Compile test fails after code fix | Fix rag_agent.py; do NOT proceed to T011 |
| Phase 4 | `pip install` resolution error | Check constraints; do NOT run T015 |
| Phase 5 | Import error not fixable in <30 min | Level 2 rollback — `git checkout` all files + recreate venv |
| Phase 6 | Any new test failure | Level 2 rollback |
| Phase 6 | Live test warning still present | Investigate; not a blocker but note in PR |
| Phase 7 | Docker build fails | Level 2 rollback |

### Parallel Opportunities

```bash
# Phase 2 — T005 and T006 can run in parallel (different test files):
Task T005: smoke-import test for get_openai_callback in test_rag_agent.py
Task T006: smoke-import test for Chroma in test_vector_store_imports.py

# Phase 4 — T011, T012, T013 can be edited in parallel (different files):
Task T011: requirements.txt
Task T012: requirements-dev.txt
Task T013: pytest.ini + conftest.py cleanup

# Phase 5 — T015 and T016 can be verified in parallel (independent imports):
Task T015: get_openai_callback path
Task T016: langchain_chroma.Chroma constructor

# Phase 6 — T017 and T018 can run in parallel (separate pytest paths):
Task T017: tests/unit/
Task T018: tests/integration/

# Phase 8 — T023, T024, T025 can be edited in parallel (different docs):
Task T023: CLAUDE.md
Task T024: docs/ARCHITECTURE.md
Task T025: backend/.env.example
```

---

## Implementation Strategy

### MVP (Minimum Viable Upgrade)

1. Complete Phase 1 — baseline captured
2. Complete Phase 2 — TDD gate green
3. Complete Phase 3 — code fix applied
4. Complete Phase 4 — versions bumped and installed
5. Complete Phase 5 — imports verified
6. Complete Phase 6 — full test suite green
7. **STOP AND VALIDATE**: 0 test regressions, 0 new warnings → ready to merge

Phases 7 and 8 (Docker + docs) complete the merge checklist but are non-blocking for a dev-environment validation.

### Total Task Count: 26 tasks across 8 phases

| Phase | Tasks | Parallelisable |
|-------|-------|---------------|
| 1 — Setup | T001–T003 | T002, T003 |
| 2 — TDD Gate | T004–T007 | T005, T006 |
| 3 — Code Fix | T008–T010 | — |
| 4 — Version Bumps | T011–T014 | T011, T012, T013 |
| 5 — Import Verification | T015–T016 | T015, T016 |
| 6 — Test Suite | T017–T019 | T017, T018 |
| 7 — Docker | T020–T022 | T021 |
| 8 — Documentation | T023–T026 | T023, T024, T025 |

---

## Notes

- All tasks follow the confirmed code path from `research.md` — no speculative changes
- `[P]` tasks operate on different files with no shared write dependency
- Level 2 rollback (5 min) is available at any point through Phase 6
- Level 3 rollback (git revert) is available after any commit
- Enterprise production hardening US1–US7 from spec.md are the next iteration after this upgrade lands
