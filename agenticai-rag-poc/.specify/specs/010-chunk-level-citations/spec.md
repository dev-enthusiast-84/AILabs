# Feature Specification: Chunk-Level Citations

**Feature Branch**: `010-chunk-level-citations`  
**Created**: 2026-05-21  
**Status**: Implemented  
**Input**: User description: "Implement industry-standard citation/source experience: relevant chunks first, full document access second, replacing duplicate filename-only source UI."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verify an Answer From Exact Evidence (Priority: P1)

A user reads an answer and sees the specific retrieved chunk, page, sheet, or section that grounded it.

**Why this priority**: Trust depends on checking the passage that actually supported the answer, not only the parent file.

**Independent Test**: Mock a query response with citations and confirm the answer renders citation cards with filename, location, and excerpt.

**Acceptance Scenarios**:

1. **Given** a retrieved PDF chunk has page metadata in its text, **When** the answer renders, **Then** the citation shows the filename, page, chunk number, and excerpt.
2. **Given** a retrieved spreadsheet chunk has a sheet marker, **When** the answer renders, **Then** the citation shows the sheet and chunk number.
3. **Given** citation metadata exists, **When** the answer renders, **Then** the older filename-only source pill list is not duplicated above it.

---

### User Story 2 - Open the Full Document Separately (Priority: P1)

A user can open the full source document from a citation without the query response embedding the full document.

**Why this priority**: Chunk citations keep answers verifiable while existing document endpoints provide full context on demand.

**Independent Test**: Click a citation card and confirm it opens the existing document viewer for that citation's normalized source.

**Acceptance Scenarios**:

1. **Given** a citation card is clicked, **When** the document viewer opens, **Then** it uses the same source name shown in the citation.
2. **Given** a response only has legacy `sources`, **When** it renders, **Then** the source buttons still open the document viewer for backward compatibility.
3. **Given** richer source details require an additional backend call, **When** the user expands or opens those details, **Then** the call is authenticated, scoped to the current role/session, bounded, and fails safely without exposing internal metadata.

---

### User Story 3 - Preserve Role and Session Boundaries (Priority: P1)

Guest and Vercel admin sessions see only normalized citations for documents they are allowed to query.

**Why this priority**: Citation metadata must not leak guest/admin session prefixes or cross-session documents.

**Independent Test**: Mock internal session-prefixed sources and assert the API returns normalized citation names only for the current user scope.

**Acceptance Scenarios**:

1. **Given** Vercel admin storage prefixes a source with the current session, **When** query returns citations, **Then** the client sees only the display filename.
2. **Given** a citation belongs to another guest/admin session, **When** response filtering runs, **Then** that citation is removed.

### Edge Cases

- Responses without citations keep the legacy `sources` array and source-button fallback.
- Citation excerpts are bounded and never include whole documents.
- Agent trace shows retrieval counts but does not duplicate citation/source lists.
- Citation display must remain keyboard accessible and AA-friendly.
- Agentic retrieval uses a bounded Retriever Team fan-out (`primary`, deduped
  `variant_n`, optional `hyde`) and must preserve deterministic citation/source order
  even when searches complete out of order.
- Additional backend/provider work is allowed when it materially improves provenance quality or user trust, but it must be bounded by count, byte size, token budget, and timeout.
- Any new intermittent, performance, maintainability, security, data-exposure, or OWASP issue found during implementation or verification must be fixed before the task is complete.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `POST /api/query/` MUST return `citations` alongside the existing `sources` array.
- **FR-002**: Each citation MUST include normalized `source`, `filename`, `chunk_index`, optional `page_number`, optional `section`, and bounded `excerpt`.
- **FR-003**: Simple and agentic RAG modes MUST use the same citation helper.
- **FR-004**: Citation source names MUST be filtered and normalized through the same role/session rules as `sources`.
- **FR-005**: The frontend MUST render citation cards when `citations` are present and use legacy source buttons only as fallback.
- **FR-006**: Clicking a citation MUST reuse the existing document viewer; query responses MUST NOT include full document text.
- **FR-007**: Agent trace MUST avoid a second filename list when citations are already visible.
- **FR-008**: The frontend SHOULD provide an industry-standard source experience: inline markers or clear citation affordances, a source panel/list with filename and location context, bounded excerpts, accessible loading/error states, and authenticated full-document preview actions.
- **FR-009**: New backend calls or endpoints MAY be added for richer citation details, page/section resolution, or preview anchoring when they improve UX. They MUST validate filenames, resolve internal source keys server-side, enforce role/session scope, bound payloads, and return safe errors.
- **FR-010**: Query-time citation enrichment MAY use additional bounded work only when measured and justified. If enrichment times out, fails, or exceeds budget, the response MUST fall back to basic citations or legacy `sources` without failing the answer.
- **FR-011**: Citation payloads and logs MUST NOT expose guest/admin source prefixes, owner/session metadata, vector IDs, filesystem/blob paths, credentials, raw prompts, guardrail violation contents, full raw documents, or unredacted sensitive values.
- **FR-012**: Retriever Team fan-out MUST keep query variants and HyDE retrieval scoped to the same role/session filter as the original query, and RRF/dedup ordering MUST remain deterministic.

### Non-Functional / Safety Requirements

- **NFR-001**: Citation behavior MUST preserve existing authentication, authorization, retrieval metadata filters, guardrail order, rate limits, token budget controls, document storage safety, upload limits, and cleanup semantics.
- **NFR-002**: Citation ordering and deduplication MUST be deterministic to avoid intermittent UI and test behavior.
- **NFR-003**: Any added backend/provider work MUST have explicit count, byte, token, and timeout budgets, plus tests or assertions covering graceful fallback.
- **NFR-004**: Implementation verification MUST include a risk pass for OWASP A01, A03, A04, and A09, plus data exposure, performance, intermittent behavior, and maintainability. Issues found in that pass MUST be fixed before completion.

### Key Entities

- **SourceCitation**: Chunk-level evidence object with source, display filename, location metadata, and excerpt.
- **Legacy Sources**: String source array retained for compatibility and fallback rendering.
- **Document Viewer**: Existing full-document access path opened from citation/source controls.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Query API responses include `citations` without breaking existing `sources`.
- **SC-002**: Citation cards show exact chunk provenance and open full-document view on demand.
- **SC-003**: Guest/admin session prefixes never appear in citation payloads or UI.
- **SC-004**: No duplicated citation/source surfaces appear in the answer bubble.
- **SC-005**: Rich citation details either load within configured budgets or degrade to basic citations/source buttons without breaking the query.
- **SC-006**: Verification finds no new security, data exposure, intermittent, material performance, maintainability, or OWASP regressions; any discovered issue is fixed before completion.
- **SC-007**: Retriever Team tests cover duplicate query suppression, preserved retrieval text, and deterministic RRF ordering under parallel fan-out.

## Assumptions

- Chunk metadata already includes `source`, `chunk_index`, and `raw_chunk`.
- Page and sheet locations can be inferred from existing extracted text markers when available.
- Full citation-to-answer-span mapping may be implemented now or later if it can be done within the same security and performance budgets; retrieved-evidence provenance remains the minimum acceptable fallback.
