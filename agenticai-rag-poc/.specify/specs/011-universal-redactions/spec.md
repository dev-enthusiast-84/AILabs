# Feature Specification: Universal Redactions

**Feature Branch**: `011-universal-redactions`
**Created**: 2026-05-24
**Status**: Draft
**Input**: User description: "Universal redactions feature: (1) all text inputs trimmed for leading/trailing spaces at every API boundary, (2) all text and voice transcripts/recordings redact PII/PCI/secrets before LLM calls and in export artifacts, (3) all text/voice inputs run through the guardrail redaction layer before being sent to the LLM, (4) any sensitive data displayed back to the user uses appropriate frontend masking. Fields in scope: PII (email, SSN, phone), PCI (payment card numbers), secrets (API keys, bearer tokens, passwords, client secrets), government identifiers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Backend Redaction Before LLM Calls (Priority: P1)

A user sends a chat message or voice query that happens to contain sensitive data — an API key, a credit card number, or an email address. The application must ensure that sensitive data is scrubbed from every text representation that flows into the AI pipeline before any LLM call is made, and from every artifact stored or exported.

**Why this priority**: This is the primary privacy and compliance control. Without it, sensitive data can be leaked to third-party LLM providers, stored in vector indexes, or written into export files. All other redaction layers depend on this foundation being correct.

**Independent Test**: Submit queries containing known PII/PCI/secret fixtures through the chat API and verify via unit and integration tests that the text reaching the LLM call, the retrieval index, and any exported artifact contains only redaction labels, never the original values.

**Acceptance Scenarios**:

1. **Given** a typed chat message contains an email address, credit card number, API key, SSN, or phone number, **When** the message is processed by the backend, **Then** the value is replaced with the appropriate `[REDACTED_*]` label before being included in any LLM prompt, retrieval query, or stored context.
2. **Given** a voice transcript contains sensitive data, **When** the transcript is passed to the speech-to-text pipeline or stored, **Then** the redacted version — not the original — is used for all downstream processing.
3. **Given** a translated or multilingual query contains sensitive data in any language, **When** retrieval runs, **Then** sensitive data is removed from the retrieval query representation before the vector search executes.
4. **Given** an LLM generates an answer that contains sensitive data, **When** the answer is returned, **Then** the output is redacted before it leaves the server and before it is written to any log or audit event.

---

### User Story 2 - Export Artifact Redaction (Priority: P1)

A user requests a transcript or audio export of their conversation. The exported file must contain only redacted text — no raw emails, card numbers, API keys, SSNs, phones, passwords, or government identifiers — regardless of whether those values appeared in user messages or AI responses.

**Why this priority**: Export artifacts are the highest-risk data exfiltration surface. A transcript downloaded to disk or shared externally is outside the application's control. Redaction must be complete and verified by automated tests before export is allowed.

**Independent Test**: Generate exports of conversations containing known PII/PCI/secret fixture strings; assert that no fixture value appears in the exported transcript or audio synthesis input.

**Acceptance Scenarios**:

1. **Given** a transcript export is requested, **When** the backend builds the export artifact, **Then** the export passes through the authoritative backend redaction layer and every sensitive value is replaced by its label before serialization.
2. **Given** an audio export is requested, **When** the backend prepares the text for speech synthesis, **Then** the synthesis input is redacted and the synthesizer never receives raw PII, PCI, or secrets.
3. **Given** a conversation contained sensitive data only in the AI-generated answers, **When** either export type is produced, **Then** the AI-generated content is also redacted in the exported artifact.
4. **Given** redaction removes all meaningful content from a transcript, **When** the export is requested, **Then** the system returns a clear error explaining that the redacted transcript is empty and the export cannot be generated.

---

### User Story 3 - Universal Input Trimming (Priority: P2)

A developer or user submits text inputs with accidental leading or trailing whitespace — from copy-paste, voice recognition output, or form auto-fill. The application normalises all text at every API entry point so downstream processing (guardrails, redaction, LLM calls) operates on clean, consistently bounded strings.

**Why this priority**: Input trimming is a prerequisite for consistent redaction pattern matching. Regex patterns for secrets and PII may miss matches at string boundaries if leading/trailing whitespace is not removed first. It is also a basic data quality guarantee expected of production systems.

**Independent Test**: Submit requests with leading/trailing whitespace in all text fields (query text, voice transcript, export transcript); verify via unit tests that the processed value has no leading or trailing whitespace.

**Acceptance Scenarios**:

1. **Given** a chat query is submitted with leading or trailing spaces, **When** the backend receives the request, **Then** the query is trimmed before guardrail checking, redaction, or LLM routing begins.
2. **Given** a voice transcript is submitted with surrounding whitespace, **When** the backend processes the transcript, **Then** the trimmed value is used for all downstream operations.
3. **Given** an export transcript or text field is submitted with extra whitespace, **When** the backend processes it, **Then** the trimmed value is used for redaction and synthesis.
4. **Given** trimming reduces a non-empty input to an empty string, **When** the backend validates the request, **Then** the system returns a clear validation error rather than forwarding an empty payload to the LLM.

---

### User Story 4 - Frontend Display Masking (Priority: P2)

A user views chat messages in the browser. If a message contains values that look like sensitive data — API keys, emails, card numbers, SSNs, or phone numbers — the rendered text shows a masked label rather than the raw value. This is a defense-in-depth layer: it protects against cases where a backend-redacted response was inadvertently bypassed or where locally-composed text is shown before the server round-trip completes.

**Why this priority**: Backend redaction is the authoritative layer, but display masking provides an additional safeguard at the presentation layer. It also gives users immediate visual feedback that sensitive values in their own typed messages will not be displayed back in clear text.

**Independent Test**: Render chat message components with fixture content containing PII/PCI/secrets; assert that the rendered output contains mask labels and not the original values.

**Acceptance Scenarios**:

1. **Given** the frontend renders a chat message containing an email, phone, SSN, API key, or credit card number, **When** the message is displayed, **Then** the sensitive value is replaced by its mask label in the rendered text.
2. **Given** a user types a message containing a password or API key and submits it, **When** the message appears in the chat history, **Then** the displayed version shows the masked label, not the original text.
3. **Given** an AI assistant response contains sensitive data that passed backend redaction, **When** the frontend renders the message, **Then** the display masking provides an additional redaction pass before the user sees the text.
4. **Given** a message contains no sensitive values, **When** it is rendered, **Then** the display masking function makes no changes and the message appears exactly as received.

---

### Edge Cases

- A single message contains multiple instances of different sensitive data types (e.g., an email and a credit card in the same message); all must be redacted independently.
- A redaction pattern partially overlaps another (e.g., a phone number embedded in a longer number sequence); the most specific pattern wins.
- A voice transcript in a non-English language contains a sensitive value in that language's format (e.g., a European IBAN or national ID number) — current redaction scope is English-format patterns only; international formats are out of scope for v1.
- Redaction of a secret removes the only meaningful text from a retrieval query, resulting in an empty search; the system must handle this gracefully rather than forwarding an empty query to the vector store.
- A user intentionally pastes a redaction label (e.g., `[REDACTED_EMAIL]`) as their input; the system must not double-redact or treat it as a real sensitive value.
- An export job was queued before a guardrail rule change; the export artifact must use the redaction state at artifact generation time, not at queue time.
- Display masking is applied to streamed or incrementally-rendered messages; masking must be applied to the final rendered state, not intermediate streaming chunks.
- A message body exceeds the maximum allowed transcript size; size validation happens after trimming and before redaction so the limit applies to clean input.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All text inputs arriving at every API endpoint MUST be trimmed of leading and trailing whitespace before any further processing (guardrail checks, redaction, LLM routing, validation).
- **FR-002**: Trimming MUST occur before length/size validation so that limits apply to clean input without surrounding whitespace.
- **FR-003**: Inputs that become empty after trimming MUST be rejected with a specific validation error; empty payloads MUST NOT be forwarded to the LLM or vector store.
- **FR-004**: All text sent to LLM calls MUST pass through the authoritative backend redaction function before the call is made; this applies to typed queries, voice transcripts, multilingual inputs, and translated retrieval queries.
- **FR-005**: All generated LLM output MUST pass through the authoritative backend redaction function before being returned in an API response or written to any log or audit event.
- **FR-006**: Transcript export artifacts MUST be built from redacted content; the raw pre-redaction text MUST NOT appear in any serialised export payload.
- **FR-007**: Audio export synthesis inputs MUST be redacted before being submitted to the speech synthesis provider; the provider MUST NOT receive raw PII, PCI, or secret values.
- **FR-008**: Redaction MUST cover all of the following field types: email addresses, US Social Security Numbers (XXX-XX-XXXX), US phone numbers, payment card numbers (13–19 digits), API keys (sk-/sk-proj- prefixed), bearer tokens, passwords and secrets (key=value patterns), client secrets, private key blocks (PEM format), and long opaque tokens (≥32 characters).
- **FR-009**: Each redacted field type MUST produce a distinct, human-readable label (e.g., `[REDACTED_EMAIL]`, `[REDACTED_PAYMENT_CARD]`, `[REDACTED_API_KEY]`) so that users and operators can identify what was removed.
- **FR-010**: The frontend MUST apply display masking to rendered chat messages using the same field-type taxonomy as the backend redaction layer; masking labels MUST match the backend labels exactly.
- **FR-011**: Display masking MUST be applied to both user messages and AI assistant messages as they are rendered in the chat history.
- **FR-012**: Display masking MUST NOT alter messages that contain no sensitive values; unchanged messages MUST render byte-for-byte identically to their source.
- **FR-013**: Automated tests MUST verify that no known PII/PCI/secret fixture value appears in: LLM prompt payloads, transcript exports, audio synthesis inputs, audit log entries, or API error responses.
- **FR-014**: Automated tests MUST verify that frontend display masking correctly masks each supported field type and leaves non-sensitive content unchanged.
- **FR-015**: The redaction function MUST be deterministic: the same input MUST always produce the same redacted output.
- **FR-016**: Audit log entries for security-relevant events MUST be verified by tests to contain redacted content only; raw sensitive values MUST NOT appear in any structured log field.
- **FR-017**: Government identifiers (US SSN format) are in scope for v1; other national identifier formats are out of scope unless a follow-on spec extends coverage.

### Key Entities

- **RedactionPattern**: A named regex pattern with an associated label; together these define one sensitive field type (e.g., pattern = email regex, label = `[REDACTED_EMAIL]`).
- **RedactionResult**: The output of applying all patterns to an input — the redacted string plus a boolean flag indicating whether any substitution was made.
- **GuardrailCoverageMatrix**: A testable map of each text surface handled by the application to the redaction and guardrail checks applied before that surface reaches the LLM or an export artifact.
- **DisplayMask**: The frontend representation of a redaction — the same label as the backend (e.g., `[REDACTED_EMAIL]`) rendered in place of the original value in the chat UI.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated tests confirm that zero known PII/PCI/secret fixture strings appear in LLM prompt payloads, transcript exports, audio synthesis inputs, structured audit log entries, or API error response bodies.
- **SC-002**: All 8 text surfaces (typed input, voice transcript, multilingual input, translated retrieval query, generated answer, playback text, transcript export, audio synthesis input) have a corresponding passing test in the guardrail coverage matrix.
- **SC-003**: Frontend display masking tests confirm that every supported sensitive field type is correctly masked in rendered message output and that non-sensitive messages are unchanged.
- **SC-004**: Input trimming tests confirm that leading/trailing whitespace is removed from all text fields at every API endpoint, and that post-trim empty inputs return a validation error rather than proceeding.
- **SC-005**: Existing chat, voice, multilingual, export, settings, and document tests continue to pass without regression after the redaction layer is applied.
- **SC-006**: Redaction function tests confirm deterministic output: identical inputs always produce identical redacted outputs across repeated invocations.
- **SC-007**: The redaction label taxonomy is consistent between backend and frontend: every label used by the backend redaction function has a matching label in the frontend display masking library.

---

## Assumptions

- Backend redaction is the authoritative privacy control; frontend display masking is defense-in-depth only and does not substitute for backend enforcement.
- International PII formats (e.g., EU IBANs, UK NI numbers, non-US phone formats) are out of scope for v1; only the formats listed in FR-008 are required.
- Redaction pattern matching uses regex applied in a defined order; if two patterns could match the same span, the first matching pattern wins.
- The existing `redact_sensitive_text` function in the backend is the canonical redaction implementation to extend, not replace.
- Display masking is applied at render time in the frontend, not stored as a separate representation; the underlying message data is unchanged in the frontend store.
- Performance impact of redaction regex passes is acceptable for message sizes within the configured transcript limit (≤8 000 characters); no caching or optimisation is required for v1.
- The redaction label format `[REDACTED_TYPE]` is established and should not change, as it appears in existing exports and test fixtures.
- Trimming is applied to string-type fields only; binary fields (e.g., audio bytes) are not in scope for trimming.
