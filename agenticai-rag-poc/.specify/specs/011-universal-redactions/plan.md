# Implementation Plan: Universal Redactions

**Branch**: `011-universal-redactions` | **Date**: 2026-05-24 | **Spec**: `.specify/specs/011-universal-redactions/spec.md`

## Summary

Extend the existing PII/PCI/secrets redaction infrastructure to cover every text surface in the application, enforce input trimming at all API boundaries, and add defense-in-depth display masking to the frontend chat renderer.

Most of the heavy lifting is already done: `redact_sensitive_text()` covers 11 field types, `query.py` and `voice_export.py` already trim inputs, and the guardrail engine redacts user queries before LLM calls. The remaining work is: (1) fix three label mismatches between the backend and frontend taxonomies, (2) centralise frontend redaction into a shared `lib/redact.ts` module and apply it to the chat message renderer, (3) add a `RedactionResult` return type for observability, and (4) write the guardrail coverage matrix tests that prove each surface is covered.

---

## Technical Context

**Language/Version**: Python 3.11–3.13 (backend), TypeScript/React 18 (frontend)
**Primary Dependencies**: FastAPI 0.115.6, React 18.3.1, Vite 6.0.7, Tailwind 3.4.17, Vitest, pytest
**Storage**: N/A — redaction is a pure-function transformation layer with no storage changes
**Testing**: pytest (backend unit), Vitest (frontend unit)
**Target Platform**: Linux server (Docker Compose) + Vercel serverless
**Project Type**: Full-stack web service — pure function / middleware layer change
**Performance Goals**: Redaction regex pass adds <5ms per message at max transcript length (8 000 chars); imperceptible to users
**Constraints**: Regex evaluation is O(n × patterns); 11 backend patterns × 8 000 chars is well within budget
**Scale/Scope**: Per-message function; no state, no storage, no network calls

---

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Tests written before implementation | ✓ PASS | TDD ordering in tasks.md — test files listed before impl files |
| OWASP A03 — Injection | ✓ PASS | Redaction operates on already-sanitized text; does not introduce new injection surface |
| OWASP A09 — Logging | ✓ PASS | `audit_event` already logs only redacted content; no raw text in logs |
| No new top-level `.md` files | ✓ PASS | All docs go to existing `docs/*.md` |
| No hardcoded credentials | ✓ PASS | Patterns match secrets but never store them |
| Coverage ≥ 98% | ✓ ENFORCED | New functions must be 100% unit-tested before merge |
| Backward compatibility | ✓ PASS | `redact_sensitive_text()` kept as wrapper; `RedactionResult` is additive |

---

## Project Structure

### Documentation (this feature)

```text
.specify/specs/011-universal-redactions/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── redaction-contract.json   # Canonical label taxonomy + coverage matrix
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code

```text
backend/
├── app/
│   └── voice/
│       └── redaction.py          # Add RedactionResult dataclass + redact_and_flag()
│                                 # redact_sensitive_text() stays as backward-compat wrapper
│
└── tests/
    └── unit/
        ├── test_redaction.py     # NEW — RedactionResult, all 11 patterns, ordering invariants
        └── test_guardrail_coverage_matrix.py  # NEW — 9-surface matrix (trimming + redaction)

frontend/
├── src/
│   └── lib/
│       └── redact.ts             # NEW — maskSensitive(), REDACTION_LABELS[]
│                                 # Replaces local helpers in useChatExport.ts and ChatInterface.tsx
│
├── src/components/
│   └── chat/
│       └── ChatMessageList.tsx   # Apply maskSensitive() to message.content at render time
│                                 # Apply to Agent Trace panel fields (refined_query, etc.)
│
└── tests/unit/
    └── redact.test.ts            # NEW — maskSensitive() all field types + non-sensitive passthrough
```

---

## Complexity Tracking

> No constitution violations requiring justification.

---

## Phase 0 Research Summary

See `research.md` for full findings. Key decisions:

### 1. Label taxonomy — backend is canonical (US4, SC-007)
- **Finding**: Three mismatches between backend (`voice/redaction.py`) and frontend (`hooks/useChatExport.ts`):
  1. `[REDACTED_GOV_ID]` (frontend) → must be `[REDACTED_SSN]` (backend)
  2. `Bearer [REDACTED_TOKEN]` (frontend, preserves "Bearer") → must be `[REDACTED_TOKEN]`
  3. Combined `password/secret` catch-all (frontend) → must be split into `[REDACTED_PASSWORD]` and `[REDACTED_SECRET]` to match backend
- **Decision**: Backend labels are canonical. `frontend/src/lib/redact.ts` implements the corrected taxonomy. `useChatExport.ts` imports `maskSensitive` from the lib (removes its local `redactSensitiveText`).

### 2. Input trimming — already complete (US3, FR-001)
- **Finding**: All three API text boundaries already trim:
  - `query.py:204` → `sanitize_query()` calls `bleach.clean(...).strip()`
  - `voice_export.py:68-96` → Pydantic `@field_validator` with `_trim_content()` on all string fields
  - `settings.py:179-193` → `@field_validator(mode="before")` calls `bleach.clean(...).strip()` on all 18 string fields
- **Decision**: No new trimming code needed. Add a test assertion per endpoint to lock in coverage and prevent regression.

### 3. Frontend display masking — absent, must be added (US4, FR-010)
- **Finding**: `ChatMessageList.tsx:311` renders `{message.content}` verbatim. The Agent Trace panel fields (`refined_query`, `hypothetical_answer`, `query_variants`, `validation_reason`) also render unmasked.
- **Decision**: Create `frontend/src/lib/redact.ts` with `maskSensitive(text: string): string`. Apply it in `MessageBubble` (message content) and the four Agent Trace fields. Use `useMemo` for repeated renders.

### 4. LLM call redaction — already complete for user input (US1, FR-004)
- **Finding**: `query.py:204-218` confirms all user text goes through `sanitize_query()` + `_check_input_guardrail()` (which includes PII/PCI redaction) before any LLM call. `answer_instruction` is checked at line 218.
- **Accepted v1 risk**: Retrieved document chunks injected into the generator prompt are NOT passed through `redact_sensitive_text`. Corpus content is operator-uploaded (trusted source). Document corpus redaction is out of scope for v1; add a docstring note to `rag_agent.py`'s generator node.

### 5. Government identifier label — frontend-only fix (FR-008, FR-017)
- **Finding**: Backend uses `[REDACTED_SSN]` (correct, US-only). Frontend uses `[REDACTED_GOV_ID]` on the same SSN regex pattern.
- **Decision**: Fix is fully contained in Gap 1 (frontend `lib/redact.ts` creation). No backend change needed.

---

## Phase 1 Design

See `data-model.md` for full entity definitions. See `contracts/redaction-contract.json` for the canonical label taxonomy.

### Canonical label taxonomy

| Field type | Label | Backend | Frontend (after fix) |
|------------|-------|---------|----------------------|
| PEM private key | `[REDACTED_PRIVATE_KEY]` | ✓ | ✓ (fix) |
| API key (sk-) | `[REDACTED_API_KEY]` | ✓ | ✓ |
| Bearer token | `[REDACTED_TOKEN]` | ✓ | ✓ (fix: remove "Bearer" prefix) |
| password= value | `[REDACTED_PASSWORD]` | ✓ | ✓ (fix: split from combined pattern) |
| access/refresh/id/api token key=value | `[REDACTED_TOKEN]` | ✓ | ✓ (fix: split from combined pattern) |
| client_secret= / api_secret= value | `[REDACTED_SECRET]` | ✓ | ✓ (fix: split from combined pattern) |
| Email address | `[REDACTED_EMAIL]` | ✓ | ✓ |
| US SSN (XXX-XX-XXXX) | `[REDACTED_SSN]` | ✓ | ✓ (fix: was GOV_ID) |
| US phone number | `[REDACTED_PHONE]` | ✓ | ✓ |
| Payment card (13–19 digits) | `[REDACTED_PAYMENT_CARD]` | ✓ | ✓ |
| Long opaque token (≥32 chars) | `[REDACTED_SECRET]` | ✓ | ✓ |

### Guardrail coverage matrix (9 surfaces)

| Surface | Function applied | File | US |
|---------|-----------------|------|----|
| typed query input | `sanitize_query()` + `_check_input_guardrail()` | query.py | US1 |
| query history items | `sanitize_query()` + `_check_input_guardrail()` | query.py | US1 |
| answer_instruction | `_check_input_guardrail()` | query.py | US1 |
| voice transcript (export) | `build_redacted_transcript()` | voice_export.py | US2 |
| audio synthesis input | `redact_sensitive_text()` | voice_export.py | US2 |
| query API boundary trim | `sanitize_query()` → `.strip()` | query.py | US3 |
| voice_export API boundary trim | Pydantic `_trim_content` validators | voice_export.py | US3 |
| settings API boundary trim | Pydantic `@field_validator(mode="before")` | settings.py | US3 |
| chat message render | `maskSensitive()` (NEW) | ChatMessageList.tsx | US4 |

### `RedactionResult` dataclass (new, additive)

```python
@dataclass(frozen=True)
class RedactionResult:
    text: str            # redacted output string
    was_redacted: bool   # True if any pattern matched and substituted
```

New function: `redact_and_flag(text: str) -> RedactionResult`
Existing function: `redact_sensitive_text(text: str) -> str` — stays as `return redact_and_flag(text).text`

### `frontend/src/lib/redact.ts` interface

```typescript
export function maskSensitive(text: string): string
export const REDACTION_LABELS: readonly string[]
```

`REDACTION_LABELS` is the exhaustive list of all possible `[REDACTED_*]` strings — used in tests to assert no label appears in test fixture inputs and every fixture is masked in outputs.

---

## OWASP Review

| ID | Control | Status |
|----|---------|--------|
| A01 | Redaction is display-only; no access control changes | ✓ |
| A03 | Patterns operate on already-sanitized strings; no new injection surface | ✓ |
| A09 | Audit events already use `_safe_value()` which calls `redact_sensitive_text`; no raw text reaches logs | ✓ |

---

## Implementation Strategy

### MVP (minimum required before merge)

1. Add `RedactionResult` + `redact_and_flag()` to `voice/redaction.py`; update `redact_sensitive_text` to delegate
2. Write `backend/tests/unit/test_redaction.py` — all 11 patterns, `RedactionResult`, ordering invariants
3. Write `backend/tests/unit/test_guardrail_coverage_matrix.py` — 9-surface parametrized test
4. Create `frontend/src/lib/redact.ts` with `maskSensitive()` + corrected labels
5. Write `frontend/tests/unit/redact.test.ts` — all field types + non-sensitive passthrough
6. Apply `maskSensitive()` in `ChatMessageList.tsx` (MessageBubble + Agent Trace fields)
7. Update `useChatExport.ts` and `ChatInterface.tsx` to import `maskSensitive` from lib (remove local helpers)
8. Full test suite — all pass, coverage ≥ 98%

### Deferred (post-MVP)

- International PII formats (EU IBAN, UK NI numbers, non-US phone) — out of scope v1 per FR-017
- Document corpus redaction (retrieved chunks before generator prompt) — accepted v1 risk, docstring note in `rag_agent.py`
- Streaming message masking (incremental render) — apply masking to final render state only for v1
