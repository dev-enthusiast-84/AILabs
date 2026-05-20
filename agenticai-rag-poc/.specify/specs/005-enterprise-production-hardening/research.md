# Research: LangGraph / LangChain Ecosystem Upgrade

**Scope**: Upgrade langgraph from 0.2.73 → 1.2.0 and the full LangChain ecosystem to
compatible versions.  
**Status**: Complete — all NEEDS CLARIFICATION items resolved.

---

## Decision Log

### D-001 — Full ecosystem upgrade, not selective version pinning

**Decision**: Upgrade the entire LangChain/LangGraph stack together in one PR.

**Rationale**: langgraph 1.x requires `langchain-core>=1.4.0`. langchain-core 1.x is
incompatible with langchain 0.3.x. Therefore all packages must move together. A partial
upgrade is not pip-resolvable.

**Alternatives considered**:
- Stay on 0.2.73 and only pin langchain-core: viable short-term (current bridge solution),
  but leaves the project on an unmaintained langgraph branch.
- Upgrade only langgraph to 0.2.76 (last 0.2.x patch): not possible — 0.2.76 has the same
  `langchain-core>=0.3.x` constraint and does not fix the `allowed_objects` warning.

---

### D-002 — openai SDK 1.x → 2.x is a forced side-effect

**Decision**: Accept openai 2.37.0 as part of this upgrade.

**Rationale**: `langchain-openai==1.2.1` requires `openai>=2.0.0`. There is no langchain-openai
1.x that supports openai 1.x.

**Impact**: Our code does NOT directly import `openai`; it goes through `langchain-openai` +
`ChatOpenAI`. So the openai 2.x SDK changes (new `OpenAI()` client, different streaming API)
are invisible to our application code. The only exposure is if any test directly uses the
openai package — audit found none.

---

### D-003 — chromadb 0.6.3 → 1.5.9 is a forced side-effect

**Decision**: Accept chromadb 1.5.9 as part of this upgrade.

**Rationale**: `langchain-chroma==1.1.0` requires `chromadb>=1.0.0`. chromadb 1.x introduces
a new `chromadb.EphemeralClient()` / `chromadb.PersistentClient()` API, deprecating the old
`chromadb.Client()` constructor.

**Impact**: Our code accesses Chroma exclusively through `langchain-chroma.Chroma`, not
directly via the `chromadb` client. langchain-chroma 1.1.0 handles the client API internally.
However the `Chroma(...)` constructor arguments need verification (particularly
`client_settings` vs new client types).

---

## Full Upgrade Matrix

| Package | Current | Target | Bump type |
|---------|---------|--------|-----------|
| `langgraph` | 0.2.73 | 1.2.0 | **Major** |
| `langchain-core` | 0.3.86 | 1.4.0 | **Major** |
| `langchain-checkpoint` | 2.1.2 | 4.1.0 | **Major** |
| `langchain` | 0.3.18 | 1.3.1 | **Major** |
| `langchain-openai` | 0.3.6 | 1.2.1 | **Major** |
| `langchain-community` | 0.3.17 | 0.4.1 | Minor |
| `langchain-chroma` | 0.2.2 | 1.1.0 | **Major** |
| `langchain-experimental` | 0.3.4 | 0.4.1 | Minor |
| `langchain-text-splitters` | — | 1.1.2 | New (split from langchain) |
| `langgraph-prebuilt` | — | 1.1.0 | New |
| `langgraph-sdk` | 0.1.74 | 0.3.14 | Minor |
| `openai` (indirect) | 1.61.1 | 2.37.0 | **Major** (forced) |
| `chromadb` (indirect) | 0.6.3 | 1.5.9 | **Major** (forced) |
| `pydantic-settings` (indirect) | 2.7.1 | 2.14.1 | Patch |
| `numpy` (indirect) | current | 2.4.6 | Minor |

---

## API Compatibility Findings

### langgraph: 0.2.x → 1.x

| API | Current usage | Status | Required change |
|-----|--------------|--------|-----------------|
| `from langgraph.graph import END, StateGraph` | `rag_agent.py:64` | **Safe** — both still in 1.x | None |
| `graph.set_entry_point("planner")` | `rag_agent.py:645` | **BREAKING** — removed in 1.x | `from langgraph.graph import START` + `graph.add_edge(START, "planner")` |
| `graph.add_node(name, fn)` | `rag_agent.py:637–643` | **Safe** — unchanged | None |
| `graph.add_edge(a, b)` | `rag_agent.py:646–651` | **Safe** — unchanged | None |
| `graph.add_conditional_edges(src, fn, map)` | `rag_agent.py:652–655` | **Safe** — `path_map` arg still accepted | None |
| `graph.compile()` | `rag_agent.py:658` | **Safe** — unchanged | None |
| `compiled.invoke(state)` | `rag_agent.py:724` | **Safe** — unchanged | None |
| `from langgraph.graph import END` | `tests/unit/test_rag_agent.py:56,66,72,78` | **Safe** | None |

**Code change count for langgraph**: 1 line (`set_entry_point` → `add_edge(START, ...)`) + 1 import.

---

### langchain-core: 0.3.x → 1.x

| API | Files | Status |
|-----|-------|--------|
| `from langchain_core.documents import Document` | `rag_agent.py`, `bm25.py`, `chunking.py`, `pipeline.py`, `pinecone_store.py`, `vector_store.py`, `tests/*` | **Safe** — stable core type, unchanged |
| `from langchain_core.messages import AIMessage, BaseMessage, HumanMessage` | `rag_agent.py:60` | **Safe** — messages API is stable |
| `from langchain_core.output_parsers import StrOutputParser` | `rag_agent.py:61`, `pipeline.py:17` | **Safe** — LCEL parsers unchanged |
| `from langchain_core.prompts import ChatPromptTemplate` | `rag_agent.py:62`, `pipeline.py:18` | **Safe** — prompt API unchanged |
| `from langchain_core.embeddings import Embeddings` | `vector_store.py:10`, `pinecone_store.py:11` | **Safe** — protocol interface unchanged |
| LCEL pipe `chain = prompt \| llm \| parser` | `rag_agent.py` (multiple nodes) | **Safe** — `|` operator preserved in 1.x |

**Code change count for langchain-core**: 0.

---

### langchain-community: 0.3.x → 0.4.x

| API | Files | Status | Required change |
|-----|-------|--------|-----------------|
| `from langchain_community.callbacks import get_openai_callback` | `rag_agent.py:58`, `pipeline.py:15` | **AT RISK** — `get_openai_callback` moved to `langchain_community.callbacks.openai_info` in 0.4.x; old path emits deprecation warning but still works in 0.4.1 | Verify at install time; update import path if old path removed |
| Test mock `patch("app.agents.rag_agent.get_openai_callback")` | `test_rag_agent.py:165,195,443,472` | Depends on import path staying the same | Must update mock target if import path changes |

**Code change count for langchain-community**: 0–2 lines (import path update, low risk).

---

### langchain-openai: 0.3.x → 1.x

| API | Files | Status |
|-----|-------|--------|
| `from langchain_openai import ChatOpenAI` | `rag_agent.py:63` | **Safe** — `ChatOpenAI` constructor args (`model`, `temperature`, `streaming`, `api_key`) unchanged in 1.x |
| `ChatOpenAI` mock in tests | `test_rag_agent.py:89,98,108` | **Safe** — mocked at class level |

**Code change count for langchain-openai**: 0.

---

### langchain-chroma: 0.2.x → 1.x

| API | File | Status | Note |
|-----|------|--------|------|
| `from langchain_chroma import Chroma` (lazy import) | `vector_store.py:286` | **Needs verification** — langchain-chroma 1.x wraps chromadb 1.x client; `Chroma(persist_directory=...)` constructor should still work but `client_settings` param may have changed | Run integration test to confirm |

**Code change count for langchain-chroma**: 0–1 lines depending on constructor compatibility.

---

### langchain-experimental: 0.3.x → 0.4.x

| API | File | Status |
|-----|------|--------|
| `from langchain_experimental.text_splitter import SemanticChunker` (lazy import) | `chunking.py:67` | **Safe** — `SemanticChunker` API unchanged in 0.4.x; it's a lazy optional import so failure degrades gracefully to recursive chunker |

**Code change count for langchain-experimental**: 0.

---

## Test Impact Analysis

| Test file | Risk | Reason |
|-----------|------|--------|
| `tests/unit/test_rag_agent.py` | **Low** | Mocks `ChatOpenAI`, `get_openai_callback` by import path — paths stable unless `get_openai_callback` moves |
| `tests/unit/test_chunking.py` | **Low** | Mocks `langchain_experimental` at `sys.modules` level — robust to version changes |
| `tests/unit/test_bm25.py` | **None** | Only uses `Document` — stable |
| `tests/unit/test_blob_vector_store.py` | **None** | Uses `Document`, `Embeddings` — stable |
| `tests/integration/*` | **Low–Medium** | Integration tests use `TestClient` with mocked OpenAI; no direct langgraph invocation so graph API changes don't surface. ChromaDB mock may need checking. |
| `tests/live/test_live_agent.py` | **Medium** | Invokes the real compiled graph; will catch any runtime behaviour change |

---

## Additional Forced Upgrades (no code impact expected)

- **openai 1.61.1 → 2.37.0**: No direct openai imports in app code. Absorbed by langchain-openai 1.2.1.
- **chromadb 0.6.3 → 1.5.9**: Accessed only through langchain-chroma. New `EphemeralClient` / `PersistentClient` API is managed inside langchain-chroma 1.x.
- **pydantic-settings 2.7.1 → 2.14.1**: Patch-level change; our `config.py` uses standard field types. No changes expected.

---

## Risk Summary

| Risk | Severity | Mitigation |
|------|----------|------------|
| `set_entry_point` removal in langgraph 1.x | **High** (breaks compile-time) | 1-line fix, confirmed in langgraph 1.x changelog |
| `get_openai_callback` import path change | **Medium** (runtime import error) | Verify after install; update import + test mocks if needed |
| langchain-chroma 1.x constructor compat | **Medium** (runtime error in vector ops) | Run integration test against real ChromaDB post-upgrade |
| openai 2.x indirect breakage | **Low** (absorbed by langchain-openai) | Verify via integration tests |
| chromadb 1.x indirect breakage | **Low** (absorbed by langchain-chroma) | Verify via integration tests |
| Regression in 7-node pipeline behaviour | **Medium** | Live agent tests cover full pipeline execution |

**Overall migration effort**: ~4–6 hours. Primarily mechanical (1 code change confirmed, 1–2 import updates to verify). The bulk of time is running the full test suite and verifying live agent behaviour.
