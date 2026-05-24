# Data Model: Universal Redactions

**Phase 1 output for plan.md** | Date: 2026-05-24

---

## Overview

This document defines the data entities for spec 011 — the universal PII/PCI/secrets
redaction layer. The backend authoritative implementation lives in
`backend/app/voice/redaction.py`. The frontend display-masking mirror lives in the new
`frontend/src/lib/redact.ts` module. All entities share the same canonical label
taxonomy so that backend substitutions and frontend renderings are byte-for-byte
identical.

---

## 1. RedactionPattern

**Source**: `backend/app/voice/redaction.py` (exists)

Immutable value object. One instance per supported sensitive field type. The ordered
tuple `_PATTERNS` is the authoritative list; pattern order determines which label wins
when two regexes could match the same span.

| Field | Type | Notes |
|-------|------|-------|
| `label` | `str` | Human-readable replacement token, e.g. `[REDACTED_EMAIL]`. Constant per instance. |
| `pattern` | `re.Pattern[str]` | Pre-compiled regular expression. Flags baked in at compile time (IGNORECASE, DOTALL where applicable). |

**Invariants**:
- Both fields are mandatory; the dataclass is `frozen=True` — instances are immutable and hashable.
- `label` MUST follow the `[REDACTED_<TYPE>]` format established by existing exports and test fixtures.
- `pattern` MUST be pre-compiled (not a raw string) so that regex compilation cost is paid once at import time, not per call.

### The 11 Patterns in Evaluation Order

Pattern ordering is load-bearing. Pattern 10 (`[REDACTED_PAYMENT_CARD]`) MUST fire
before pattern 11 (`[REDACTED_SECRET]` long-token catch-all); otherwise a 16-digit card
number is swallowed by the catch-all first and receives the wrong label.

| # | Label | What It Matches | Key Flags |
|---|-------|-----------------|-----------|
| 1 | `[REDACTED_PRIVATE_KEY]` | PEM private key blocks: `-----BEGIN ... PRIVATE KEY----- ... -----END ... PRIVATE KEY-----` | `IGNORECASE \| DOTALL` (multi-line blocks) |
| 2 | `[REDACTED_API_KEY]` | `sk-` or `sk-proj-` prefixed keys followed by ≥20 alphanumeric/dash/underscore characters | — |
| 3 | `[REDACTED_TOKEN]` | `Bearer <token>` header values where token is ≥16 chars | `IGNORECASE` |
| 4 | `[REDACTED_PASSWORD]` | `password`, `passwd`, or `pwd` followed by `:` or `=` and a non-whitespace value | `IGNORECASE` |
| 5 | `[REDACTED_TOKEN]` | `access_token`, `refresh_token`, `id_token`, or `api_token` key=value pairs (value ≥12 chars) | `IGNORECASE` |
| 6 | `[REDACTED_SECRET]` | `secret`, `client_secret`, or `api_secret` key=value pairs (value ≥12 chars) | `IGNORECASE` |
| 7 | `[REDACTED_EMAIL]` | RFC-style email addresses (`local@domain.tld`) | `IGNORECASE` |
| 8 | `[REDACTED_SSN]` | US Social Security Numbers in `XXX-XX-XXXX` format | — |
| 9 | `[REDACTED_PHONE]` | US phone numbers with optional `+1` prefix; separators may be space, dot, or dash | — |
| 10 | `[REDACTED_PAYMENT_CARD]` | 13–19 consecutive digits with optional single space or dash between digit groups | — |
| 11 | `[REDACTED_SECRET]` | Any token of ≥32 consecutive alphanumeric/dash/underscore characters (catch-all) | — |

**Note on shared labels**: Patterns 3 and 5 both emit `[REDACTED_TOKEN]`; patterns 6 and 11
both emit `[REDACTED_SECRET]`. This is intentional — the label reflects the semantic
class, not the specific regex variant.

---

## 2. RedactionResult

**Source**: `backend/app/voice/redaction.py` (NEW — to be added)

Return type of the new `redact_and_flag(text: str) -> RedactionResult` function.
The existing `redact_sensitive_text(text: str) -> str` is kept unchanged for backward
compatibility; it delegates internally to `redact_and_flag` and returns `.text`.

```python
@dataclass(frozen=True)
class RedactionResult:
    text: str           # redacted output string
    was_redacted: bool  # True if at least one pattern matched and substituted
```

| Field | Type | Notes |
|-------|------|-------|
| `text` | `str` | The full input string with every matching span replaced by its label. Equal to the original if no pattern matched. |
| `was_redacted` | `bool` | `True` when `text != original_input`. Callers use this to decide whether to emit an audit/log event or return an `HTTP 422` for post-trim-empty inputs. |

**Invariants**:
- `was_redacted` is `False` iff `text` is byte-for-byte identical to the original input.
- The function is pure and deterministic: same input always produces the same `RedactionResult`.
- `text` is never `None`; if the input is an empty string the output is also an empty string with `was_redacted=False`.

---

## 3. CanonicalLabelMap

**Documentation entity** — defines the taxonomy shared by backend patterns and the
frontend `DisplayMask` module. Neither backend nor frontend may introduce a label not
in this table.

| Field Type | Canonical Label | Scope |
|------------|-----------------|-------|
| PEM private key | `[REDACTED_PRIVATE_KEY]` | backend + frontend |
| API key (`sk-` / `sk-proj-`) | `[REDACTED_API_KEY]` | backend + frontend |
| Bearer token | `[REDACTED_TOKEN]` | backend + frontend |
| `password=` / `passwd=` / `pwd=` value | `[REDACTED_PASSWORD]` | backend + frontend |
| `access_token=` / `refresh_token=` / `id_token=` / `api_token=` value | `[REDACTED_TOKEN]` | backend + frontend |
| `secret=` / `client_secret=` / `api_secret=` value | `[REDACTED_SECRET]` | backend + frontend |
| Email address | `[REDACTED_EMAIL]` | backend + frontend |
| US SSN | `[REDACTED_SSN]` | backend + frontend |
| US phone number | `[REDACTED_PHONE]` | backend + frontend |
| Payment card number (13–19 digits) | `[REDACTED_PAYMENT_CARD]` | backend + frontend |
| Long opaque token (≥32 alphanumeric chars, catch-all) | `[REDACTED_SECRET]` | backend + frontend |

### Frontend Label Corrections Required

The current `frontend/src/lib/redact.ts` (once created) and any existing frontend
redaction code MUST be updated to match this table exactly:

| Current frontend label | Correct canonical label | Change |
|------------------------|-------------------------|--------|
| `[REDACTED_GOV_ID]` | `[REDACTED_SSN]` | Rename to match backend |
| `Bearer [REDACTED_TOKEN]` (preserves literal "Bearer") | `[REDACTED_TOKEN]` | Strip the "Bearer" prefix from the replacement so the whole `Bearer <value>` span becomes just `[REDACTED_TOKEN]` |

---

## 4. DisplayMask

**Source**: `frontend/src/lib/redact.ts` (NEW file)

TypeScript module that applies client-side display masking at render time. This is a
defense-in-depth layer only; the backend redaction function is the authoritative privacy
control.

| Export | Type signature | Notes |
|--------|----------------|-------|
| `maskSensitive` | `(text: string) => string` | Applies all canonical patterns in the same order as the backend `_PATTERNS` tuple. Pure function; returns the input unchanged if no pattern matches. |
| `REDACTION_LABELS` | `readonly string[]` | Exhaustive list of all possible replacement labels (11 values, one per row in the CanonicalLabelMap). Used in test assertions to verify a rendered message contains a label and not the original value. |

**Invariants**:
- `maskSensitive` is pure and deterministic.
- `maskSensitive(text)` returns `text` unmodified when no pattern matches (FR-012).
- Every label in `REDACTION_LABELS` appears in the CanonicalLabelMap and has a matching backend label; no additional labels may be introduced.
- Pattern evaluation order mirrors the backend: payment card (pattern 10) before long-token catch-all (pattern 11).

**Consumers**:

| Consumer | Usage | File |
|----------|-------|------|
| `ChatMessageList.tsx` | Wraps `message.content` before rendering | `frontend/src/components/chat/ChatMessageList.tsx` |
| `useChatExport.ts` | Replaces the local `redactSensitiveText` helper (import from lib instead) | `frontend/src/hooks/useChatExport.ts` |
| Browser TTS playback | Replaces the local `redactSensitiveText` call in `ChatInterface.tsx` | `frontend/src/components/ChatInterface.tsx` |

---

## 5. GuardrailCoverageMatrix

**Test artifact** — maps every text surface that the application processes to the
redaction/trimming function applied before that surface reaches the LLM or an export
artifact. Every row must have a corresponding passing test.

| Surface | Redaction/Trimming function | File | US in scope |
|---------|-----------------------------|------|-------------|
| typed_input (chat query) | `_check_input_guardrail` → guardrail engine PII redaction | `backend/app/api/query.py` | US1 |
| voice_transcript (export) | `build_redacted_transcript` → `redact_sensitive_text` | `backend/app/voice/voice_export.py` | US2 |
| audio_synthesis_input | `redact_sensitive_text` (called before TTS provider) | `backend/app/voice/voice_export.py` | US2 |
| chat_message_rendering | `maskSensitive` (NEW) | `frontend/src/components/chat/ChatMessageList.tsx` | US4 |
| browser_tts_playback | `redactSensitiveText` → `maskSensitive` (after refactor) | `frontend/src/components/ChatInterface.tsx` | US4 |
| local_transcript_export | `buildLocalExportTranscript` → `maskSensitive` (after refactor) | `frontend/src/hooks/useChatExport.ts` | US4 |
| query_api_input_boundary | `.strip()` via `sanitize_query()` | `backend/app/api/query.py` | US3 |
| voice_export_api_input_boundary | `.strip()` via Pydantic `_trim_content` validators | `backend/app/voice/voice_export.py` | US3 |
| settings_api_string_inputs | `.strip()` via Pydantic field validators (ADD if missing) | `backend/app/api/settings.py` | US3 |

**Coverage rule**: a surface is "covered" only when both conditions hold:
1. An automated test submits a known fixture value (email, SSN, card number, API key, etc.) through that surface.
2. The test asserts that the fixture value does not appear in the output — only the corresponding `[REDACTED_*]` label does.

---

## Relationships

```
RedactionPattern (×11, ordered tuple _PATTERNS)
    │  used by
    ▼
redact_sensitive_text(text) → str          ← backward-compat wrapper
redact_and_flag(text)       → RedactionResult
    │
    ├── RedactionResult.text         (redacted string)
    └── RedactionResult.was_redacted (bool flag for audit/validation)

CanonicalLabelMap
    │  defines labels for
    ├── backend _PATTERNS (labels column)
    └── frontend DisplayMask (maskSensitive + REDACTION_LABELS)

GuardrailCoverageMatrix
    │  references
    └── all surfaces → redaction functions above
```

---

## Out of Scope (v1)

- International PII formats: EU IBANs, UK NI numbers, non-US phone formats, passports.
- Binary/audio fields: trimming and redaction apply to string-type fields only.
- Streaming-chunk-level masking: display masking is applied to the final rendered message state, not to intermediate streaming chunks.
- Storing redacted representations separately from original messages in the frontend store; masking is render-time only.
