# Feature Specification: Voice-to-Voice Chat

**Feature Branch**: `003-voice-chat`  
**Created**: 2026-05-19  
**Status**: Draft  
**Input**: User description: "use spec kit to add the new feature for voice to voice capability; voice to voice only needed for chat window, no other functionality on the app"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a Chat Question by Voice (Priority: P1)

A user in the chat window wants to ask a document question without typing. They press a microphone control in the chat composer, grant microphone permission, speak a question, review the captured transcript in the existing chat input, and send it through the same chat query flow used for typed questions.

**Why this priority**: Voice input only creates value if it reliably feeds the existing chat workflow without bypassing document, role, guardrail, or settings rules.

**Independent Test**: Open the chat window with at least one indexed document, activate the microphone control, provide a spoken question, verify the transcript appears in the chat input, send it, and confirm the normal chat response flow is used.

**Acceptance Scenarios**:

1. **Given** the user is in the chat window with documents available, **When** they click the microphone control and speak, **Then** the recognized transcript appears in the chat input before submission.
2. **Given** a transcript is present in the chat input, **When** the user sends the message, **Then** the app submits the transcript using the same query endpoint and selected RAG mode as typed chat.
3. **Given** the user cancels recording before sending, **When** recording stops, **Then** no query is submitted automatically and the user can edit or clear the transcript.

---

### User Story 2 - Hear the Assistant Answer (Priority: P1)

A user who asked a chat question wants the answer read aloud. After the assistant response is displayed, the chat window offers playback for that answer and clearly shows when audio is playing or stopped.

**Why this priority**: Voice-to-voice requires an audible response, but playback must remain anchored to chat answers rather than becoming a global app feature.

**Independent Test**: Submit a chat question, wait for the assistant response, activate answer playback, verify audio begins, then stop playback and verify the UI returns to the idle state.

**Acceptance Scenarios**:

1. **Given** an assistant response is visible in the chat window, **When** the user clicks the listen/play control for that message, **Then** the response text is spoken aloud.
2. **Given** audio playback is active, **When** the user clicks stop or starts playback for another response, **Then** the previous playback stops cleanly.
3. **Given** the assistant response is an error or guardrail block message, **When** playback is requested, **Then** the app either reads that visible message aloud or disables playback with an inline explanation in the chat message area.

---

### User Story 3 - Handle Voice Permission and Browser Support Gracefully (Priority: P1)

A user may deny microphone access, use an unsupported browser, or experience speech recognition failure. The chat window must explain the issue without affecting typed chat.

**Why this priority**: Voice capabilities depend on browser/device support and permissions. Failure must be understandable and isolated to voice controls.

**Independent Test**: Simulate missing speech recognition support, denied microphone permission, and recognition failure; verify the chat window shows one appropriate inline error per case and typed chat still works.

**Acceptance Scenarios**:

1. **Given** the browser does not support voice capture, **When** the chat window loads, **Then** the microphone control is disabled or hidden with an accessible explanation and the typed chat input remains usable.
2. **Given** the user denies microphone permission, **When** voice capture is requested, **Then** the chat window shows one inline error near the voice control and does not show a duplicate toast.
3. **Given** voice recognition fails or returns no transcript, **When** recording ends, **Then** the chat window shows an inline message that no speech was captured and does not submit a query.

---

### User Story 4 - Keep Voice Strictly Scoped to Chat (Priority: P2)

A user navigating document upload, document preview, settings, guardrails, login, or deployment-related pages should not see or use voice controls there. Voice controls belong only to the chat window.

**Why this priority**: The requested feature is intentionally narrow; limiting scope reduces privacy risk, UI clutter, and implementation complexity.

**Independent Test**: Visit each non-chat surface and verify there are no microphone, speech, or audio playback controls outside the chat experience.

**Acceptance Scenarios**:

1. **Given** the user is on upload, document list, document preview, settings, guardrails, login, or header controls, **When** the page renders, **Then** no voice input or voice playback controls are displayed there.
2. **Given** the user opens a document viewer from an assistant source citation, **When** the modal appears, **Then** it does not add voice controls; playback remains available only on chat assistant messages.

---

### User Story 5 - Export Text, Voice, and Hybrid Chat (Priority: P2)

A user may complete a conversation by typing, speaking, or mixing both input modes. They expect the existing chat export control to export the readable conversation transcript regardless of how each message was created.

For voice-only conversations, the user also expects an audio export option so the spoken interaction can be reviewed outside the app. All exported transcript and audio content must redact sensitive and personally identifiable information before the file is created.

**Why this priority**: Export is part of the chat workflow. Adding voice must not make exported conversations incomplete or misleading, and voice-only users need an export that preserves the audio experience as well as the readable transcript.

**Independent Test**: Run three chat sessions: typed-only, voice-only, and hybrid typed/voice. Export each session and verify the exported transcript contains every visible user question and assistant answer in order with sensitive/PII values redacted. For the voice-only session, also export audio and verify the package contains playable redacted audio for the spoken conversation plus the redacted transcript.

**Acceptance Scenarios**:

1. **Given** a typed-only chat conversation, **When** the user exports the chat, **Then** the exported file contains the same readable transcript as before voice support was added with sensitive and PII values redacted.
2. **Given** a voice-only chat conversation where spoken questions became transcripts, **When** the user exports the chat, **Then** the exported file contains the submitted transcripts and assistant answers in chronological order with sensitive and PII values redacted.
3. **Given** a hybrid conversation containing typed and voice-transcribed questions, **When** the user exports the chat, **Then** the exported file includes all visible messages in order, does not omit voice-originated turns, and redacts sensitive and PII values.
4. **Given** a voice-only chat conversation, **When** the user chooses transcript export, **Then** the exported file contains all voice-transcribed user questions and assistant answer text with sensitive and PII values redacted.
5. **Given** a voice-only chat conversation, **When** the user chooses audio export, **Then** the export includes playable audio for the spoken conversation and includes the redacted transcript alongside it.
6. **Given** a typed-only or hybrid chat conversation, **When** the user exports the chat, **Then** transcript export remains available; audio export is available only for messages that have voice/audio data or can be safely synthesized from redacted visible assistant text.
7. **Given** any chat conversation containing sensitive values such as API keys, access tokens, email addresses, phone numbers, government identifiers, payment card numbers, or secrets, **When** transcript or audio export is requested, **Then** those values are replaced with redaction labels before export.

---

### Edge Cases

- Microphone permission is denied, revoked mid-session, or blocked by browser policy.
- Speech recognition returns an empty transcript, partial transcript, or incorrect transcript.
- The user exports a conversation containing typed questions, voice-transcribed questions, and spoken assistant responses.
- The user requests audio export for a voice-only conversation after some audio data is unavailable or cannot be synthesized.
- The conversation contains secrets, credentials, API keys, tokens, emails, phone numbers, payment numbers, government identifiers, or other PII that must be redacted before transcript or audio export.
- Redaction changes the text used for audio export; the audio must speak the redacted version rather than the original sensitive value.
- The user starts recording while a query is already loading.
- The user starts playback while another answer is already playing.
- The user navigates away from the chat window during recording or playback.
- The browser supports speech synthesis but not speech recognition, or vice versa.
- A guest session expires while using voice input; the existing auth/session error handling must apply.
- The chat has no indexed documents; voice input must not bypass the existing disabled query state.
- The user has reduced-motion or assistive-technology preferences; controls must remain keyboard and screen-reader accessible.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST add voice controls only to the chat window and chat message area.
- **FR-002**: The system MUST NOT add voice controls to document upload, document list, document viewer, settings, guardrails, authentication, header, deployment, or documentation screens.
- **FR-003**: The chat composer MUST provide a microphone control for capturing spoken input when the browser/device supports voice capture.
- **FR-004**: Voice capture MUST produce an editable transcript in the existing chat input before the query is sent.
- **FR-005**: Voice capture MUST NOT automatically submit a query unless the user explicitly sends the transcript.
- **FR-006**: Voice-submitted questions MUST use the same query API, selected RAG mode, role/session permissions, rate limits, settings prerequisites, and guardrails as typed questions.
- **FR-007**: The chat UI MUST disable or prevent recording while a query is already being submitted or when no documents are available.
- **FR-008**: Each assistant chat response MUST expose an optional playback control that reads the visible answer text aloud.
- **FR-009**: The system MUST provide a stop control or equivalent state toggle while audio playback is active.
- **FR-010**: Starting playback for one assistant response MUST stop any currently playing assistant response.
- **FR-011**: Recording and playback state MUST be visible to the user through chat-local UI states, such as active button state, status text, or inline message.
- **FR-012**: Voice permission errors, unsupported browser errors, recognition failures, and playback failures MUST be handled gracefully in the chat window using either inline messaging or toast messaging, but never both for the same event.
- **FR-013**: The system MUST NOT store raw microphone audio as part of this feature.
- **FR-014**: The system MUST NOT send raw microphone audio to document upload, indexing, settings, guardrails, or any non-chat workflow.
- **FR-015**: The system MUST stop recording and playback when the chat component unmounts or the user navigates away.
- **FR-016**: Voice controls MUST be keyboard accessible, have accessible names, and communicate recording/playback state to assistive technologies.
- **FR-017**: If voice recognition is unavailable but typed chat is available, the typed chat experience MUST continue to work unchanged.
- **FR-018**: If voice playback is unavailable but typed chat is available, the typed chat experience MUST continue to work unchanged.
- **FR-019**: The existing chat export control MUST support typed-only, voice-only, and hybrid typed/voice conversations.
- **FR-020**: Exported chat transcripts MUST include all visible user messages and assistant responses in chronological order, regardless of whether a user message originated from typing or voice transcription.
- **FR-021**: Exported chat transcripts MAY label message origin as typed or voice when that metadata is available, but MUST NOT depend on that label to include the message.
- **FR-022**: The chat export UI MUST offer transcript export for every conversation mode.
- **FR-023**: For voice-only conversations, the chat export UI MUST offer audio export in addition to transcript export.
- **FR-024**: Voice-only audio export MUST include the transcript plus playable audio for the spoken conversation.
- **FR-025**: Audio export MUST NOT include browser speech-recognition internals or transient recording/playback UI state.
- **FR-026**: Raw user microphone audio MUST NOT be persisted silently; if user-question audio is included in an audio export, it MUST be retained only for the current chat session and only for the explicit purpose of user-initiated export.
- **FR-027**: Assistant response audio MAY be generated on demand from visible assistant text during export when previously played audio is not retained.
- **FR-028**: If audio export cannot include part of a voice-only conversation, the chat UI MUST explain what is missing and still allow transcript export.
- **FR-029**: Transcript export MUST redact sensitive and personally identifiable information before generating the downloadable file.
- **FR-030**: Audio export MUST redact sensitive and personally identifiable information before generating or packaging playable audio.
- **FR-031**: Redaction MUST apply to user messages, assistant messages, voice transcripts, exported transcript sidecars, generated speech content, and any metadata included in the export.
- **FR-032**: Redaction MUST cover at minimum API keys, bearer/access tokens, passwords, private keys, email addresses, phone numbers, payment card numbers, government identifiers, and obvious secret-like values.
- **FR-033**: Redaction MUST replace sensitive values with stable readable labels such as `[REDACTED_API_KEY]`, `[REDACTED_EMAIL]`, or `[REDACTED_PHONE]` rather than deleting surrounding context.
- **FR-034**: If audio export includes user-question audio, the export MUST NOT include the original unredacted user audio when sensitive/PII content is detected; it MUST either synthesize redacted audio from the redacted transcript or explain that redacted audio export is unavailable while still allowing redacted transcript export.
- **FR-035**: Export redaction MUST happen before any export artifact is downloaded, stored, or handed to a browser download API.

### Key Entities

- **Voice Capture Session**: A temporary chat-local interaction that tracks whether recording is active, the current transcript, and any capture error. It is not persisted.
- **Voice Playback Session**: A temporary chat-local interaction that tracks which assistant message is being spoken and whether playback is active or stopped. It is not persisted.
- **Transcript**: Editable text produced from spoken input and placed into the existing chat question input before submission.
- **Assistant Audio Playback**: Spoken rendering of a visible assistant message. It is derived from the message text and does not create a new document, setting, or query entity.
- **Chat Export Transcript**: A downloadable text representation of visible chat messages. It includes typed questions, voice-transcribed questions, assistant answers, and existing message metadata that is already safe to export.
- **Chat Audio Export**: A user-initiated downloadable audio package for voice-only conversations. It includes playable audio for the spoken conversation and a transcript, while excluding browser internals and non-chat app data.
- **Redacted Export Artifact**: A transcript or audio export generated from redacted text, with sensitive/PII values replaced by readable redaction labels before download.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of voice controls appear only inside the chat window in UI tests.
- **SC-002**: A spoken question can be captured, edited, and submitted through the existing chat input without changing typed-chat behavior.
- **SC-003**: Assistant response playback can be started and stopped from the chat message UI.
- **SC-004**: Unsupported voice capture, denied microphone permission, empty transcript, and playback failure each produce one clear chat-local error state with no duplicate toast/inline pairing.
- **SC-005**: Existing chat tests for typed queries, RAG mode selection, guardrails, role/session isolation, and settings prerequisites continue to pass.
- **SC-006**: No raw audio is persisted in browser storage, backend storage, vector stores, blob storage, logs, or exported chat transcripts.
- **SC-007**: Export tests verify typed-only, voice-only, and hybrid conversations all produce complete ordered transcripts.
- **SC-008**: Voice-only export tests verify audio export produces a playable artifact plus transcript, or a clear chat-local explanation when audio export is unavailable.
- **SC-009**: Export tests verify sensitive and PII values are redacted from transcript exports and audio-export transcripts.
- **SC-010**: Audio export tests verify generated or packaged audio does not speak unredacted sensitive/PII values when redaction is required.

## Assumptions

- Voice-to-voice means spoken question input plus spoken assistant-answer playback inside the existing chat window.
- The first version uses explicit user actions: press to record, send transcript, press to play answer, press to stop.
- The feature does not implement always-on listening, wake words, global dictation, document narration, audio file upload, voice authentication, or app-wide voice navigation.
- Existing transcript export remains text-based; voice questions are exported as submitted transcripts and spoken assistant answers are exported as answer text.
- Voice-only audio export is an additional export option, not a replacement for transcript export.
- Export redaction is a best-effort privacy safeguard and does not change the visible in-app chat messages.
- Redacted audio export should prefer synthesized audio from redacted transcript text over retaining original unredacted microphone audio.
- Voice support may rely on browser/device capabilities; unsupported environments fall back to typed chat.
- Existing authentication, role/session isolation, settings prerequisites, query handling, guardrails, and rate limiting remain the source of truth.
