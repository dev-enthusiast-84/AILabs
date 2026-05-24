# Feature Specification: Dual RAG Mode — Simple Lookup + Agentic Pipeline

**Feature Branch**: `002-dual-rag-mode`
**Created**: 2026-05-14
**Status**: Draft
**Input**: User description: "dual-rag-mode: add simple RAG lookup alongside existing agentic RAG pipeline; user selects the mode in UI; both modes share guardrails and rate limiting"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Quick Lookup with Simple RAG (Priority: P1)

A user wants a fast, direct answer from indexed documents without the overhead of a multi-step
planning and validation pipeline. They select "Simple" mode, ask a question, and receive an
answer in noticeably less time than the agentic pipeline requires.

**Why this priority**: Many queries are straightforward lookups where the agentic planner and
validator add latency but no meaningful quality uplift. A simple mode gives users a low-friction
path for routine questions.

**Independent Test**: With at least one document indexed, select Simple mode, submit a question,
and verify an answer is returned with source citations but without a validation badge.

**Acceptance Scenarios**:

1. **Given** the user is on the chat interface and selects "Simple" mode, **When** they submit a
   question, **Then** an answer is returned with source citations and the response is visually
   labelled as Simple mode output.
2. **Given** Simple mode is active, **When** the answer is displayed, **Then** no validation
   status badge is shown (validation is not performed in this mode).
3. **Given** Simple mode is active, **When** a query is blocked by the content guardrail,
   **Then** the same block behaviour (error message) applies as in Agentic mode.

---

### User Story 2 — Deep Analysis with Agentic RAG (Priority: P1)

A user dealing with a complex or ambiguous question selects "Agentic" mode to get a
query-planned, validated answer. The existing four-stage pipeline (planner → retriever →
generator → validator) continues to work exactly as before.

**Why this priority**: The agentic pipeline is the existing default; it must not regress and
must remain the recommended approach for complex questions.

**Independent Test**: Select Agentic mode, submit a question, and verify an answer is returned
with a VALID or NEEDS_REVISION badge alongside source citations and token count.

**Acceptance Scenarios**:

1. **Given** the user selects "Agentic" mode, **When** they submit a question, **Then** the
   full planning-and-validation pipeline is used and a validation badge is shown.
2. **Given** no mode has been explicitly selected, **When** the user submits a question,
   **Then** Agentic mode is used by default.
3. **Given** the user switches from Simple to Agentic mid-conversation, **When** they send
   the next message, **Then** that message uses the Agentic pipeline.

---

### User Story 3 — Mode Persists Within a Session (Priority: P2)

Once a user selects a RAG mode, that choice is remembered for the duration of their session
so they do not need to re-select it for every message.

**Why this priority**: Improves usability for users who consistently prefer one mode; they
should not have to manually re-choose on every turn.

**Independent Test**: Select Simple mode, send three questions in a row without changing the
toggle — all three responses are Simple-mode responses.

**Acceptance Scenarios**:

1. **Given** a user selects Simple mode and sends multiple questions, **When** each response
   arrives, **Then** each response is clearly labelled as Simple mode output without requiring
   the user to re-select.
2. **Given** a user changes the mode between messages, **When** the next message arrives,
   **Then** it uses the newly selected mode.

---

### Edge Cases

- What if both Simple and Agentic modes are called simultaneously from two browser tabs?
  → Each request is stateless; mode is sent per-request. No coordination required.
- What if documents are deleted mid-conversation and the next query finds no results?
  → Both modes return the same "no documents indexed" error already handled today.
- What if the Simple mode retrieves zero relevant chunks?
  → The system returns an answer indicating no relevant information was found; this is the
  same behaviour as the agentic retriever today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The query endpoint MUST accept an optional `mode` parameter with values `"simple"` or `"agentic"`; when omitted, the system MUST default to `"agentic"`.
- **FR-002**: In `"simple"` mode, the system MUST retrieve the most relevant document chunks and generate a direct answer without a query-planning or validation step.
- **FR-003**: In `"agentic"` mode, the system MUST continue to execute the existing four-stage pipeline (planner → retriever → generator → validator) unchanged.
- **FR-004**: Both modes MUST apply the same input and output guardrail checks (content policy enforcement).
- **FR-005**: Both modes MUST be subject to the same per-IP rate limit.
- **FR-006**: The query response MUST include a `mode` field indicating which pipeline processed the request.
- **FR-007**: When `"simple"` mode is used, the `validation` field in the response MUST indicate that no validation was performed (e.g. `"N/A"`).
- **FR-008**: The chat UI MUST display a mode selector (toggle or segmented control) that allows the user to choose between Simple and Agentic modes before or between messages.
- **FR-009**: The mode selector MUST default to Agentic mode on first load.
- **FR-010**: The chat UI MUST visually distinguish Simple-mode responses from Agentic-mode responses (e.g. different label or icon in the message footer).
- **FR-011**: Validation badge MUST NOT be shown for Simple-mode responses; it MUST still be shown for Agentic-mode responses.
- **FR-012**: The selected mode MUST persist across messages within the same browser session (no re-selection required per turn).
- **FR-013**: Token usage MUST be reported for both modes.

### Key Entities

- **Query**: A user question directed at the indexed documents, now carrying a `mode` attribute.
- **RAG Mode**: An enumerated setting (`simple` | `agentic`) that governs which retrieval-and-generation pipeline is invoked for a query.
- **Query Response**: The answer, sources, validation status, mode used, and token count returned by either pipeline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of existing agentic-mode tests continue to pass without modification.
- **SC-002**: Simple-mode queries complete without a validation badge — verifiable in both the UI and the API response (`validation: "N/A"`).
- **SC-003**: The mode selector is visible and operable on all viewport sizes supported by the existing UI.
- **SC-004**: All unit and integration tests for both modes pass before merge.
- **SC-005**: Guardrail enforcement is identical across both modes — no query that is blocked in Agentic mode passes in Simple mode.
- **SC-006**: Token count is reported for every query response regardless of mode.

## Assumptions

- The Simple mode performs a single retrieval pass (top-k similarity search, same `k` as the agentic retriever) followed by a single LLM generation call; no iterative refinement.
- The Agentic mode default is intentional — it is the "safe" choice that always validates answers.
- Mode selection is a per-request UI control, not a persistent account preference; it resets on page reload.
- Both modes use the same LLM model and embedding model configured in Settings.
- Guest users have access to both modes under the same constraints as admin users (guests can query already).
- The `validation` field value for Simple mode (`"N/A"`) is chosen to be clearly distinct from the Agentic values (`"VALID"`, `"NEEDS_REVISION"`).
