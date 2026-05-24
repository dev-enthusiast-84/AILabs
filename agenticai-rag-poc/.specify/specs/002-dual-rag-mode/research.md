# Research: Dual RAG Mode

**Date**: 2026-05-14 | **Plan**: [plan.md](plan.md)

## Decision 1: Simple RAG pipeline design

**Decision**: Single retrieve → generate pass. Retrieval uses the same `similarity_search()` helper and `format_context()` formatter as the agentic pipeline. Generation uses one direct `ChatPromptTemplate` + `ChatOpenAI` chain with a concise system prompt instructing the model to answer only from context.

**Rationale**: Reuses proven infrastructure; avoids code duplication; the only new code is a `run_simple_rag(question)` function in `app/rag/pipeline.py`.

**Alternatives considered**:
- Separate router/endpoint — rejected; adds complexity and duplicates guardrail wiring
- LangChain `RetrievalQA` chain — rejected; introduces another abstraction layer that obscures the token budget and complicates testing

---

## Decision 2: `mode` field placement

**Decision**: Add `mode: Literal["simple", "agentic"] = "agentic"` to `QueryRequest` (Pydantic model). The endpoint reads it and branches. The `QueryResponse` adds `mode: str` so the UI knows which pipeline ran.

**Rationale**: Single endpoint (`POST /api/query/`) is already rate-limited and guarded. Adding a field is backward-compatible (existing callers omit `mode` and get `"agentic"` by default).

**Alternatives considered**:
- Two separate endpoints (`/query/simple`, `/query/agentic`) — rejected; duplicates middleware, rate-limit decorator, and guard code
- Header-based mode selection — rejected; non-standard, harder to test and document

---

## Decision 3: `validation` value for simple mode

**Decision**: Return `"N/A"` (string, uppercase) in the `validation` field for simple-mode responses.

**Rationale**: The UI already branches on `validation === "VALID"` / `"NEEDS_REVISION"` to choose badge style. `"N/A"` is a clean third value that is easy to handle in the conditional: hide the badge entirely.

**Alternatives considered**:
- `null` / `None` — cleaner JSON but requires nullable type change everywhere `validation` is used
- Empty string `""` — ambiguous; could indicate an error rather than "not applicable"

---

## Decision 4: UI mode selector widget

**Decision**: Segmented control (two adjacent pill buttons: "⚡ Simple" and "🤖 Agentic") positioned in the chat header area. Selected mode is held in local component state (`useState`), defaulting to `"agentic"`. No persistence beyond page lifetime (per spec assumptions).

**Rationale**: Segmented controls are the standard pattern for mutually exclusive choices. Local state is sufficient; Zustand store is overkill for a per-tab, per-session UI preference.

**Alternatives considered**:
- Dropdown select — harder to scan at a glance for a two-option choice
- Zustand store — adds complexity; spec says reset on page reload is acceptable

---

## Decision 5: Response labelling in chat bubbles

**Decision**: Add a small mode label below the sources/validation row: "⚡ Simple RAG" (sky-blue) or "🤖 Agentic RAG" (indigo). The validation badge is shown only when mode is `"agentic"`.

**Rationale**: Makes it immediately obvious which pipeline produced each answer, especially important in mixed-mode conversations.
