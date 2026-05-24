# Tasks: Universal Redactions

**Feature**: 011-universal-redactions | **Date**: 2026-05-24 | **Status**: COMPLETE

---

## Phase 0 — Backend Core

- [X] **T-01** Add `RedactionResult` dataclass to `backend/app/voice/redaction.py`
  - Fields: `text: str`, `was_redacted: bool` (frozen dataclass)
- [X] **T-02** Add `redact_and_flag(text: str) -> RedactionResult` function
  - Applies all 11 `_PATTERNS` in order; sets `was_redacted = (redacted != text)`
- [X] **T-03** Update `redact_sensitive_text(text: str) -> str` to delegate to `redact_and_flag`
  - Backward-compatible wrapper: `return redact_and_flag(text).text`
- [X] **T-04** Add accepted-risk docstring note to `backend/app/agents/rag_agent.py`
  - Documents that retrieved chunks are not redacted (trusted operator corpus, v1 risk)

## Phase 1 — Backend Tests

- [X] **T-05** Create `backend/tests/unit/test_redaction.py`
  - `RedactionResult` dataclass invariants (frozen, fields)
  - `redact_and_flag()` return type, `was_redacted` flag, empty-string, parity with wrapper
  - All 11 patterns tested individually (pattern, label, non-match)
  - Ordering invariant: payment card before long-token catch-all
  - `build_redacted_transcript()` integration
  - Non-sensitive text passthrough (no false positives)
- [X] **T-06** Create `backend/tests/unit/test_guardrail_coverage_matrix.py`
  - Surface 1: `sanitize_query()` strips whitespace + 422 on empty
  - Surface 2: `ChatVoiceExportMessage._trim_content` and `ChatVoiceExportRequest` text/transcript trimming
  - Surface 3: `SettingsUpdateRequest` strips api_key and model fields
  - Surface 4: `build_redacted_transcript()` redacts PII fixtures
  - Surface 5: `redact_sensitive_text()` redacts audio synthesis input
  - Surfaces 6/7/8: `redact_and_flag()` on typed queries, history items, answer instructions
  - Surface 9: Backend label taxonomy contract (no `[REDACTED_GOV_ID]`)

## Phase 2 — Frontend Core

- [X] **T-07** Create `frontend/src/lib/redact.ts`
  - Export `maskSensitive(text: string): string` — all 11 patterns in backend-identical order
  - Export `REDACTION_LABELS: readonly string[]` — exhaustive list of canonical labels
  - Fix label mismatches: `[REDACTED_SSN]` (not `[REDACTED_GOV_ID]`), `[REDACTED_TOKEN]` (no "Bearer" prefix), split `[REDACTED_PASSWORD]` / `[REDACTED_TOKEN]` / `[REDACTED_SECRET]`
  - Reset `re.lastIndex` on every call (global regex safety)
- [X] **T-08** Update `frontend/src/hooks/useChatExport.ts`
  - Import `maskSensitive` from `@/lib/redact`
  - Replace inline `redactSensitiveText` body with `return maskSensitive(text)` wrapper
  - Keep export name `redactSensitiveText` for backward compatibility with `ChatInterface.tsx`
- [X] **T-09** Update `frontend/src/components/chat/ChatMessageList.tsx`
  - Import `maskSensitive` from `@/lib/redact`, add `useMemo` to imports
  - `MessageBubble`: `const maskedContent = useMemo(() => maskSensitive(message.content), [message.content])`; render `{maskedContent}` instead of `{message.content}`
  - Agent Trace panel: apply `maskSensitive()` to `refined_query`, `hypothetical_answer`, `query_variants.map(maskSensitive)`, `original_question`, `validation_reason`

## Phase 3 — Frontend Tests

- [X] **T-10** Create `frontend/tests/unit/redact.test.ts`
  - `REDACTION_LABELS` contains all canonical labels, does not contain `[REDACTED_GOV_ID]`
  - All 11 patterns tested individually (correct label, value absent from output)
  - Bearer token: result does NOT preserve "Bearer" prefix
  - SSN: uses `[REDACTED_SSN]` not `[REDACTED_GOV_ID]`
  - Payment card before long-token catch-all ordering invariant
  - Non-sensitive passthrough (no false positives)
  - Idempotency: `maskSensitive(maskSensitive(text)) === maskSensitive(text)`
  - Global regex `lastIndex` reset across repeated calls
- [X] **T-11** Update `frontend/tests/unit/ChatMessageList.test.tsx`
  - Add `ChatMessageList — display masking` describe block
  - Email, SSN, API key masked in user and assistant message content
  - SSN uses `[REDACTED_SSN]` not `[REDACTED_GOV_ID]`
  - Normal prose passes through unchanged
  - Email masked in Agent Trace `refined_query` field
  - SSN masked in Agent Trace `validation_reason` field

## Validation

- [X] Backend: 1005 unit tests pass, `app/voice/redaction.py` at 100% coverage
- [X] Frontend: 364 tests pass (22 test files), all new tests green
- [X] All 9 guardrail coverage matrix surfaces have automated test assertions
- [X] Label taxonomy parity: backend `[REDACTED_SSN]` / `[REDACTED_TOKEN]` / `[REDACTED_PASSWORD]` / `[REDACTED_SECRET]` — no `[REDACTED_GOV_ID]` in either codebase
