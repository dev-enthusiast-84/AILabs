# Feature Specification: Multilingual Text and Voice Chat Modalities

**Feature Branch**: `004-multilingual-chat-modalities`  
**Created**: 2026-05-19  
**Status**: Draft  
**Input**: User description: "Add a spec feature to enable multi language support for text/voice modality and ensure guardrails cover the scope of data being handled"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask and Receive Chat Answers in a Selected Language (Priority: P1)

A user wants to ask document questions in a supported language and receive the answer in that same language, using the existing chat workflow for typed questions.

**Why this priority**: Multilingual support must first preserve the core chat loop: user question, retrieval, grounded answer, sources, and guardrail enforcement.

**Independent Test**: Select a supported non-English language, type a question in that language, submit it through chat, and verify the answer is returned in the selected language with normal sources and RAG mode metadata.

**Acceptance Scenarios**:

1. **Given** a user selects Spanish and types a Spanish question, **When** they submit it, **Then** the answer is displayed in Spanish and uses the same document retrieval flow as typed English chat.
2. **Given** a user selects French and types a French question, **When** the answer is generated, **Then** sources, validation state, and token/latency metadata remain visible as they are for English chat.
3. **Given** the selected language changes mid-conversation, **When** the next question is submitted, **Then** only subsequent answers use the new selected language.

---

### User Story 2 - Use Voice Input and Voice Playback in a Selected Language (Priority: P1)

A user wants voice-to-voice chat in a supported language. They select a language, speak a question, review the transcript in that language, submit it, and hear the assistant answer spoken in that language.

**Why this priority**: The existing voice feature must work beyond English without bypassing transcript review, explicit send, redaction, or chat-only scope.

**Independent Test**: Select a supported language, use microphone input, verify the transcript uses the selected language, submit it, and play the assistant answer with the matching language/voice settings.

**Acceptance Scenarios**:

1. **Given** the user selects Spanish, **When** they start voice input, **Then** speech recognition is configured for Spanish and the transcript appears in the chat input before submission.
2. **Given** a Spanish assistant answer is visible, **When** the user plays the answer, **Then** speech playback uses Spanish-compatible speech settings when available.
3. **Given** the browser does not support speech recognition or playback for the selected language, **When** the user attempts voice input or playback, **Then** the chat window shows one chat-local explanation and typed chat remains available.

---

### User Story 3 - Guardrails Cover Every Multilingual Data Surface (Priority: P1)

A user may submit or receive content in any supported language, through text, voice transcript, translated intermediate text, assistant answer, playback text, transcript export, or audio export. The system must run guardrails on the data it handles, not only on English typed text.

**Why this priority**: Multilingual features can create guardrail blind spots if policy checks only inspect one language or one representation of the content.

**Independent Test**: Submit unsafe or sensitive content in a supported non-English language through typed input and voice transcript, then verify it is blocked, flagged, or redacted consistently across chat display, playback, transcript export, and audio export.

**Acceptance Scenarios**:

1. **Given** a non-English typed question violates an input guardrail, **When** it is submitted, **Then** the request is blocked or handled with the same policy outcome as an equivalent English request.
2. **Given** a voice transcript contains unsafe content in a supported language, **When** the user submits it, **Then** the input guardrail evaluates the transcript before query execution.
3. **Given** generated answer text contains sensitive or policy-relevant content in any supported language, **When** it is displayed, played, or exported, **Then** output guardrails and export redaction apply before the content leaves the chat workflow.
4. **Given** translation is used internally, **When** content is transformed between languages, **Then** guardrails evaluate the original user text, any translated query used for retrieval/generation, generated answer text, and exported text/audio content.

---

### User Story 4 - Export Multilingual Text, Voice, and Hybrid Chats (Priority: P2)

A user wants exports from multilingual conversations to preserve readable language context while still redacting sensitive and PII content.

**Why this priority**: Export must remain complete and safe when conversations mix languages, typed input, voice transcripts, and spoken answers.

**Independent Test**: Run a multilingual typed-only, voice-only, and hybrid chat. Export transcripts and, where available, audio. Verify messages remain ordered, language labels are included when available, and sensitive/PII values are redacted.

**Acceptance Scenarios**:

1. **Given** a multilingual typed chat, **When** transcript export is requested, **Then** the export includes the visible messages in order with language metadata when available.
2. **Given** a multilingual voice-only chat, **When** audio export is requested, **Then** the export includes redacted playable audio plus a redacted transcript.
3. **Given** exported text or generated audio would include sensitive/PII content, **When** export is created, **Then** the sensitive values are redacted before download or audio generation.

---

### User Story 5 - Language Selection Is Chat-Scoped (Priority: P3)

A user should configure language for chat text and voice only. Language controls should not appear in document upload, document list, settings, guardrails, login, deployment, or other non-chat workflows.

**Why this priority**: The feature is scoped to chat modalities and should not create app-wide complexity or misleading controls.

**Independent Test**: Visit non-chat surfaces and verify no multilingual chat controls appear there.

**Acceptance Scenarios**:

1. **Given** the user opens upload, document viewer, settings, guardrails, login, or header-only UI, **When** the surface renders, **Then** no chat language selector or voice-language control is displayed there.
2. **Given** the user opens the chat window, **When** documents are available, **Then** the language selector is available near the chat composer or chat toolbar.

---

### Edge Cases

- The selected language is unsupported by browser speech recognition, browser speech synthesis, or server-side audio export.
- The user mixes languages in a single question or conversation.
- The document corpus is in a different language than the user’s selected chat language.
- Guardrails detect a violation only after translation or only in the original source text.
- Translation changes or obscures PII, secrets, or policy-sensitive content.
- A voice transcript is incorrect because of accent, dialect, or language auto-detection failure.
- Audio export cannot synthesize a selected language voice.
- A guest session expires during multilingual voice capture, playback, or export.
- The selected language changes while a query, playback, or audio export is in progress.
- The user exports a multilingual conversation containing sensitive/PII values in multiple languages or scripts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The chat window MUST provide a language selector for supported text and voice chat languages.
- **FR-002**: Language controls MUST be scoped to the chat window and MUST NOT be added to upload, document list, document viewer, settings, guardrails, authentication, header, deployment, or documentation surfaces.
- **FR-003**: Typed chat questions MUST support supported non-English languages without bypassing the existing query API, selected RAG mode, role/session permissions, rate limits, settings prerequisites, or source display.
- **FR-004**: Voice capture MUST configure speech recognition using the selected language when browser support is available.
- **FR-005**: Voice playback MUST use the selected language or a compatible language voice when available.
- **FR-006**: If voice capture, playback, or audio export is unavailable for the selected language, the chat UI MUST show one chat-local explanation and preserve typed chat functionality.
- **FR-007**: The system MUST preserve explicit transcript review before sending voice-captured questions in any language.
- **FR-008**: The system MUST track the language used for each user message when known.
- **FR-009**: The system MUST request assistant answers in the selected chat language while keeping source citations and response metadata visible.
- **FR-010**: If internal translation is used for retrieval or generation, the system MUST keep language metadata sufficient to audit which text representations were evaluated by guardrails.
- **FR-011**: Input guardrails MUST evaluate typed questions and voice transcripts in their original language before query execution.
- **FR-012**: If translation is used, input guardrails MUST also evaluate translated query text before query execution.
- **FR-013**: Output guardrails MUST evaluate generated assistant answers before display, playback, transcript export, or audio export.
- **FR-014**: Export redaction MUST evaluate multilingual transcript text before creating downloadable transcript files.
- **FR-015**: Audio export MUST generate or package audio only from redacted export text.
- **FR-016**: Guardrails MUST cover at minimum user typed input, voice transcripts, translated query text, retrieved context snippets included in prompts when exposed, assistant answer text, playback text, transcript exports, audio export transcripts, and audio-export synthesis input.
- **FR-017**: Guardrail results MUST be applied consistently across text and voice modalities for equivalent content.
- **FR-018**: Multilingual export MUST include all visible chat messages in chronological order and include language labels when known.
- **FR-019**: Multilingual transcript and audio exports MUST redact sensitive/PII values before download or audio generation.
- **FR-020**: Redaction MUST support sensitive/PII patterns across supported languages and scripts where pattern detection is feasible, including emails, phone numbers, API keys, tokens, passwords, private keys, payment card numbers, and government identifiers.
- **FR-021**: Existing English typed and voice chat behavior MUST remain unchanged when the selected language is English.
- **FR-022**: The selected language MUST apply only to chat modalities and MUST NOT change document indexing, document preview, admin settings, guardrail configuration, or authentication behavior.

### Key Entities

- **Chat Language Preference**: Chat-local selection that controls typed answer language, speech recognition language, speech playback language, and export language metadata.
- **Message Language Metadata**: Per-message language information, including selected language and detected language when available.
- **Multilingual Transcript**: Chat transcript containing one or more languages and message-level language metadata when known.
- **Translated Query Representation**: Optional internal text generated from the original user message to improve retrieval or generation. It must be guardrail-covered if used.
- **Guardrail Coverage Scope**: The set of data surfaces evaluated by guardrails: original input, voice transcript, translation, generated answer, playback text, export transcript, and audio synthesis input.
- **Redacted Multilingual Export**: Transcript or audio export with sensitive/PII values replaced before download or audio generation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete typed chat in at least three configured languages, including English, without breaking source citations or RAG mode metadata.
- **SC-002**: Voice capture and answer playback work for supported languages in browsers that provide the needed speech APIs.
- **SC-003**: Unsupported language/modality combinations show one clear chat-local explanation and typed chat remains usable.
- **SC-004**: Guardrail tests cover original non-English typed input, non-English voice transcripts, translated query text when used, generated answers, transcript exports, and audio export synthesis input.
- **SC-005**: Equivalent policy-violating content is blocked, flagged, or redacted consistently across typed and voice modalities.
- **SC-006**: Multilingual transcript exports preserve message order and redact sensitive/PII values.
- **SC-007**: Multilingual audio exports never synthesize unredacted sensitive/PII values.
- **SC-008**: Existing English chat, voice, export, guardrail, and role/session tests continue to pass.

## Assumptions

- The first version supports a defined list of languages chosen by the product team; unsupported languages fall back to typed chat with clear messaging.
- Language selection is chat-local and does not change document upload, indexing, settings, guardrail administration, authentication, or deployment workflows.
- Existing role/session isolation, query prerequisites, guardrails, rate limits, redaction, and export privacy rules remain the source of truth.
- Translation, if implemented, is an internal aid for retrieval/generation and does not replace the original user message in the visible chat transcript.
- Guardrail coverage is required for every text representation the system handles, including translated representations used internally.
- Audio export should synthesize from redacted text rather than preserving unredacted raw microphone audio.
