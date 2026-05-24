# Research: Universal Redactions

**Phase 0 output for plan.md** | Date: 2026-05-24

---

## 1. Redaction label taxonomy inconsistency (Gap 1 — US4, SC-007)

### Finding

Backend (`backend/app/voice/redaction.py`) and frontend (`frontend/src/hooks/useChatExport.ts`)
define independent redaction functions with three concrete label mismatches:

| Pattern | Backend label | Frontend label |
|---|---|---|
| US Social Security Number | `[REDACTED_SSN]` | `[REDACTED_GOV_ID]` |
| Bearer token | `[REDACTED_TOKEN]` (full match incl. "Bearer") | `Bearer [REDACTED_TOKEN]` (preserves the word "Bearer") |
| Password / secret key-value | Two distinct labels: `[REDACTED_PASSWORD]` and `[REDACTED_SECRET]` | Single combined replacement: `key: [REDACTED_SECRET]` for both |

Additionally, the frontend combines `api_key`, `access_token`, `secret`, `password`, and `pwd`
into one regex branch (line 18 of `useChatExport.ts`) while the backend uses four separate
`RedactionPattern` entries, each with its own label.

### Decision

- **Decision:** Standardise on backend labels as the canonical taxonomy. Frontend must match exactly.
- **Rationale:** Backend labels are already in production for transcript exports; changing them
  would invalidate stored transcripts. The frontend is display-only and has no persistent output,
  so it is the lower-risk side to change.
- **Alternatives considered:** A shared JSON config file with label definitions (rejected —
  adds build-time coupling between Python and TypeScript; labels are stable constants).

### Implementation

- Create `frontend/src/lib/redact.ts` — exports `maskSensitive(text: string): string` with all
  patterns aligned to backend labels:
  - `[REDACTED_SSN]` (replacing `[REDACTED_GOV_ID]`)
  - `[REDACTED_TOKEN]` with the bearer prefix consumed inside the regex, not preserved
  - `[REDACTED_PASSWORD]` for `password|passwd|pwd` key-value matches
  - `[REDACTED_TOKEN]` for `access_token|refresh_token|id_token|api_token` key-value matches
  - `[REDACTED_SECRET]` for `secret|client_secret|api_secret` key-value matches
  - Keep: `[REDACTED_PRIVATE_KEY]`, `[REDACTED_API_KEY]`, `[REDACTED_EMAIL]`,
    `[REDACTED_PHONE]`, `[REDACTED_PAYMENT_CARD]`
- Update `frontend/src/hooks/useChatExport.ts` — replace the inline `redactSensitiveText`
  function body with a re-export that delegates to `maskSensitive` from `redact.ts`.

---

## 2. Input trimming gaps (Gap 2 — US3, FR-001)

### Finding

Three endpoints already trim all user-supplied text fields:

- `backend/app/api/query.py:204` — `sanitize_query()` applies `bleach.clean()` then `.strip()`
  on `body.question`.
- `backend/app/api/voice_export.py:68-96` — Pydantic `@field_validator` with `_trim_content()`
  and `_trim_optional_text()` call `.strip()` on all string fields before validation.
- `backend/app/api/settings.py:179-193` — `SettingsUpdateRequest._sanitize_string` is a
  `@field_validator(mode="before")` that calls `bleach.clean(...).strip()` on all 18 string
  fields: `api_key`, `model`, `embedding_model`, `planner_model`, `generator_model`,
  `validator_model`, `langchain_api_key`, `langchain_project`, `pinecone_api_key`,
  `pinecone_index_name`, `pinecone_namespace`, `pinecone_cloud`, `pinecone_region`,
  `blob_read_write_token`, `reranker_type`, `reranker_judge_model`, `chunker_type`.

No additional trimming gaps exist across the three primary text-accepting endpoints.

### Decision

- **Decision:** No new trimming code required in settings.py or voice_export.py. The settings
  endpoint strips all string inputs including key-like fields (API keys, connection strings)
  via `bleach.clean(...).strip()`. This is acceptable because API keys and connection string
  components (index names, namespace values, cloud/region identifiers) should never have
  intentional leading/trailing whitespace; stripping is safe.
- **Rationale:** Consistent application via a single `mode="before"` validator is the correct
  pattern. Selective stripping of only "human-typed" fields would require per-field decisions
  that introduce future maintenance drift.
- **Alternatives considered:** Skipping strip on key/token fields to preserve exact user
  intent for copy-paste errors (rejected — if a user pastes with trailing whitespace the key
  will be invalid regardless; stripping improves UX).

### Implementation

- No code changes needed. Document coverage in spec as confirmed-complete.
- Add a test assertion in `backend/tests/unit/test_api_settings.py` confirming that
  `SettingsUpdateRequest(api_key="  sk-abc  ")` returns `api_key="sk-abc"` after validation.

---

## 3. Frontend display masking absent from ChatMessageList (Gap 3 — US4, FR-010)

### Finding

`frontend/src/components/chat/ChatMessageList.tsx:311` renders message content as:

```tsx
<p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
```

`message.content` is rendered verbatim — no redaction applied. The `redactSensitiveText`
function in `useChatExport.ts` is used only for:
1. Browser TTS playback synthesis input (`ChatInterface.tsx:275`).
2. Local transcript export (`buildLocalExportTranscript`).

The chat display surface (the message bubbles in the browser) is entirely unmasked.

The Agent Trace panel also renders unmasked values for `refined_query`,
`hypothetical_answer`, `query_variants`, and `validation_reason` (lines 234-278 of
`ChatMessageList.tsx`) — all of which contain or are derived from the original user query
and could carry PII that was typed into the chat input.

### Decision

- **Decision:** Apply `maskSensitive()` from the new `frontend/src/lib/redact.ts` to
  `message.content` at render time in `MessageBubble` (line 311). Also apply to Agent Trace
  fields: `refined_query`, `hypothetical_answer`, `query_variants`, and `validation_reason`.
- **Rationale:** Defense-in-depth. Backend redacts before LLM calls and before export;
  frontend display masking is a last-resort client-side layer for cases where a user
  accidentally includes secrets in a chat message. It is never the primary redaction gate.
- **Alternatives considered:**
  - Masking only assistant messages (rejected — user messages may contain secrets typed
    directly into the chat input).
  - Masking in the Zustand store at ingestion time (rejected — would mutate the canonical
    message state, making the original text unrecoverable for debugging; render-time masking
    preserves source-of-truth without storing secrets in display form).

### Implementation

- `frontend/src/lib/redact.ts` — new file, exports `maskSensitive(text: string): string`.
- `frontend/src/components/chat/ChatMessageList.tsx` — import `maskSensitive` and replace
  `{message.content}` with `{maskSensitive(message.content)}` in `MessageBubble` (line 311).
  Apply the same call to the four Agent Trace fields rendered in `TraceRow` elements.
- `frontend/src/hooks/useChatExport.ts` — remove the local `redactSensitiveText` body;
  delegate to `maskSensitive` from `redact.ts` (the export name `redactSensitiveText` can
  be kept as a re-export alias for backward compatibility with any tests).

---

## 4. LLM call redaction completeness (Gap 4 — US1, FR-004)

### Finding

The query pipeline redacts in this order (`backend/app/api/query.py:204-218`):
1. `sanitize_query(body.question)` — bleach + strip (line 204).
2. `_check_input_guardrail(clean_question, surface="original")` — guardrail engine applies
   PII redaction and returns `modified_text` (line 211).
3. `_contextual_retrieval_question(clean_question, body.history)` — builds retrieval query
   from already-redacted `clean_question` (line 213).
4. History messages: each `message.content` in `body.history` is independently sanitized
   and checked (lines 214-216).
5. `answer_instruction` (language directive): also checked through `_check_input_guardrail`
   (line 218) — confirmed covered.

Retrieved document chunks flow from `retriever_node` → `grader_node` → `reranker_node` →
`generator_node` as `state["retrieved_context"]` (the output of `format_context(docs)`). Chunks
are sourced from indexed documents. They pass through chunking/embedding at index time
(`app/rag/pipeline.py`) but are NOT passed through `redact_sensitive_text` before being
injected into the LLM generator prompt at `rag_agent.py:726`.

### Decision

- **Decision:** Document chunks are operator-uploaded (admin or guest) content and are treated
  as trusted corpus material for v1. Redacting retrieved chunks before LLM injection is out
  of scope for this spec. The redaction layer targets user-typed query text and LLM-generated
  output only.
- **Rationale:** Redacting corpus chunks would corrupt the knowledge base semantics — a
  document legitimately containing an email address for contact purposes would be redacted
  before the LLM could answer "what is the contact email?" questions correctly. Document-level
  redaction is a separate operator-facing concern (pre-upload sanitisation) not a runtime
  concern.
- **Alternatives considered:** Redacting chunks only in reranker/judge prompts (rejected —
  inconsistent; the judge scores on truncated chunk text already at 400 chars, further
  redaction would change scores arbitrarily).
- **Accepted risk:** Document corpus may contain PII. Documented in `backend/app/agents/rag_agent.py`
  module docstring as an accepted v1 risk. Tracked for a future "document corpus redaction"
  spec.

### Implementation

- Add one-line accepted-risk note to the `rag_agent.py` module docstring.
- No functional code change required.

---

## 5. Government identifier label and scope (Gap 5 — FR-008, FR-017)

### Finding

- Backend (`backend/app/voice/redaction.py:58-60`): pattern `\b\d{3}-\d{2}-\d{4}\b` →
  label `[REDACTED_SSN]`. US SSN format only. No other national identifier patterns present.
- Frontend (`frontend/src/hooks/useChatExport.ts:25`): same numeric pattern →
  label `[REDACTED_GOV_ID]`.

The FR-017 scope note (US SSN only for v1) is already satisfied by both implementations.
The only issue is the label mismatch, which is resolved by Gap 1 (frontend adopts
`[REDACTED_SSN]`).

### Decision

- **Decision:** Retain `[REDACTED_SSN]` as the canonical label. No pattern changes needed.
  Non-US national identifier formats (NI number, SIN, TFN, etc.) are explicitly out of scope
  for v1 per FR-017.
- **Rationale:** `[REDACTED_SSN]` is specific and unambiguous; `[REDACTED_GOV_ID]` was an
  over-generalisation applied to what is effectively a US-only pattern. Using a specific label
  avoids confusion if non-US patterns are added later under distinct labels.
- **Alternatives considered:** Renaming backend label to `[REDACTED_GOV_ID]` for generality
  (rejected — breaks existing stored transcripts with no user benefit).

### Implementation

- Frontend change only: in `frontend/src/lib/redact.ts`, use `[REDACTED_SSN]` for the
  `\b\d{3}-\d{2}-\d{4}\b` pattern.
- No backend change required.

---

## Summary of files to create or modify

| File | Action | Spec refs |
|---|---|---|
| `frontend/src/lib/redact.ts` | Create — canonical `maskSensitive()` with aligned taxonomy | US4, FR-010, SC-007 |
| `frontend/src/hooks/useChatExport.ts` | Modify — delegate `redactSensitiveText` to `maskSensitive` | US2, SC-007 |
| `frontend/src/components/chat/ChatMessageList.tsx` | Modify — apply `maskSensitive` to `message.content` and Agent Trace fields at render | US4, FR-010 |
| `backend/app/agents/rag_agent.py` | Modify — add accepted-risk note to module docstring | US1, FR-004 |
| `backend/tests/unit/test_api_settings.py` | Modify — add trim-coverage assertion | US3, FR-001 |
| `frontend/tests/unit/ChatMessageList.test.tsx` | Modify — add display masking assertions | US4, FR-010 |
| `frontend/tests/unit/` | Add `redact.test.ts` — unit tests for `maskSensitive` label taxonomy | SC-007 |
