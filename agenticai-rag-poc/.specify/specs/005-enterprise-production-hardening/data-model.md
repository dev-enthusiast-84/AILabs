# Data Model: Enterprise Production Hardening

**Phase 1 output for plan.md** | Date: 2026-05-24

---

## Overview

This document covers every entity, config group, and conceptual model introduced or formalised by spec 005 (US1–US7). Runtime Pydantic models are marked **runtime**; test/documentation-only constructs are marked **test artifact** or **doc entity**.

---

## 1. SafeAppError (runtime)

**Source:** `backend/app/core/errors.py`

Structured application error raised throughout the backend. Serialised to JSON in the global exception handler; the `public_message` is the only field surfaced to API callers.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `category` | `ErrorCategory` | required | Machine-readable error category (see below) |
| `status_code` | `int` | required | HTTP status code returned to the client |
| `public_message` | `str \| None` | `None` | Human-readable message safe to expose; `None` → generic fallback |
| `cause_type` | `str \| None` | `None` | Python exception class name (for internal logging only) |
| `metadata` | `dict` | `{}` | Extra structured context (never contains PII or secrets) |

**ErrorCategory literals:**

| Value | Meaning |
|-------|---------|
| `"openai_provider_error"` | OpenAI API failure (rate-limit, 5xx, timeout) |
| `"vector_store_error"` | ChromaDB / Pinecone read/write failure |
| `"blob_storage_error"` | Vercel Blob or local file-store failure |
| `"storage_error"` | Generic persistence failure |
| `"retrieval_error"` | RAG retrieval pipeline failure |
| `"internal_error"` | Unclassified server error |
| `"timeout"` | Operation exceeded configured deadline |

**OWASP note:** `public_message` must never include stack traces, file paths, or internal identifiers. `metadata` is emitted only to structured logs (A09).

---

## 2. AuditEvent (structured log — not a DB model)

**Source:** `backend/app/core/audit.py`

Emitted via Python's standard `logging` framework as a structured JSON line. There is no database table; events are consumed by log aggregators (e.g. Datadog, CloudWatch).

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | `str` | Semantic name, e.g. `"guardrail_block"`, `"auth_failure"`, `"export_complete"` |
| `status` | `str` | `"ok"` \| `"blocked"` \| `"error"` |
| `request_id` | `str \| None` | Propagated from `X-Request-ID` header; `None` for background jobs |
| `user_role` | `str` | `"admin"` \| `"guest"` \| `"anonymous"` |
| `session_scope` | `"present" \| "none"` | Whether a valid session cookie was attached |
| `error_category` | `str \| None` | Mirrors `SafeAppError.category` when an error is being logged |
| `**kwargs` | sanitised `dict` | Additional safe metadata (filenames, query hashes, etc.) — PII must not appear here |

**Invariant:** Emitters must call `sanitize_for_audit()` on any user-supplied string before including it in kwargs. The audit logger never calls `repr()` on raw request bodies.

---

## 3. VoiceExportJob (runtime)

**Source:** `backend/app/voice/export_jobs.py`

In-process job record for an asynchronous TTS export request. Persisted in memory (bounded LRU); not written to any database.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `job_id` | `str` | uuid4 | Stable identifier returned to the client |
| `owner_key` | `str` | required | Opaque key scoping the job to one session/role |
| `status` | `VoiceExportJobStatus` | `"queued"` | See state machine below |
| `created_at` | `datetime` | `now()` | UTC timestamp when the job was enqueued |
| `updated_at` | `datetime` | `now()` | UTC timestamp of last status change |
| `expires_at` | `datetime` | `now() + job_ttl` | After this point the job record is dropped from the cache |
| `artifact_expires_at` | `datetime \| None` | `None` | Set when status reaches `"succeeded"`; after this the audio bytes are discarded |
| `retry_count` | `int` | `0` | Number of worker retries attempted |
| `error_code` | `str \| None` | `None` | Short machine-readable failure code set on `"failed"` |
| `error_message` | `str \| None` | `None` | Safe human-readable failure description (no stack traces) |
| `artifact` | `VoiceExportArtifact \| None` | `None` | Populated when status = `"succeeded"` |
| `metadata` | `dict` | `{}` | Caller-supplied tags (e.g. `{"language": "es"}`) |

**VoiceExportJobStatus literals:** `"queued"` | `"running"` | `"succeeded"` | `"failed"` | `"canceled"` | `"expired"`

### 3a. Job Lifecycle State Machine

```
                   ┌──────────┐
         enqueue   │          │
        ──────────►│  queued  │
                   │          │
                   └────┬─────┘
                        │ worker picks up
                        ▼
                   ┌──────────┐
                   │          │◄─── retry (retry_count++)
                   │ running  │
                   │          │
                   └──┬───┬───┘
          success ────┘   └──── transient error (retry_count < max)
              │                 permanent error │
              ▼                                 ▼
        ┌──────────┐                     ┌──────────┐
        │succeeded │                     │  failed  │
        │(artifact │                     │(error_   │
        │ present) │                     │ code set)│
        └──────────┘                     └──────────┘
              │
              │ artifact_expires_at reached
              ▼
        (artifact bytes discarded; job record
         remains until expires_at)

  Any state ──► canceled   (client calls DELETE /api/voice/export/{job_id})
  Any state ──► expired    (expires_at reached and job not yet terminal)
```

**Transitions:**
- `queued → running`: background worker acquires the job.
- `running → succeeded`: TTS completes; `artifact` and `artifact_expires_at` populated.
- `running → running`: transient OpenAI error within retry budget; `retry_count` incremented, `updated_at` refreshed.
- `running → failed`: non-retryable error or retry budget exhausted; `error_code` and `error_message` set.
- `* → canceled`: explicit client cancellation before terminal state.
- `* → expired`: TTL expiry by the cache-reaper background task.

---

## 4. VoiceExportArtifact (runtime)

**Source:** `backend/app/voice/export_jobs.py`

Embedded in `VoiceExportJob.artifact` once TTS synthesis succeeds.

| Field | Type | Description |
|-------|------|-------------|
| `audio` | `bytes` | Raw encoded audio data |
| `mime_type` | `str` | MIME type, e.g. `"audio/mpeg"` |
| `audio_format` | `"mp3"` | Encoding format (currently always `mp3`) |
| `expires_at` | `datetime` | UTC deadline after which the bytes are zeroed and the field set to `None` |

**Security note:** Audio bytes are held in process memory only. They must never be written to disk or returned in logs. The `expires_at` TTL defaults to `export_artifact_ttl_seconds` (see ExportLimits).

---

## 5. ChatLanguage (runtime)

**Source:** `backend/app/core/chat_languages.py`

Describes a supported UI + TTS language. The static constant `CHAT_LANGUAGES` is the authoritative list; no database persistence.

| Field | Type | Description |
|-------|------|-------------|
| `code` | `ChatLanguageCode` | BCP-47 short code used internally (`"en"` \| `"es"` \| `"fr"`) |
| `label` | `str` | Display name shown in the language picker |
| `speech` | `str` | BCP-47 locale tag passed to the TTS API (e.g. `"en-US"`) |

**ChatLanguageCode literals:** `"en"` | `"es"` | `"fr"`

**CHAT_LANGUAGES constant:**

| `code` | `label` | `speech` |
|--------|---------|---------|
| `"en"` | English | `"en-US"` |
| `"es"` | Spanish | `"es-ES"` |
| `"fr"` | French | `"fr-FR"` |

---

## 6. RetrievalQueryRepresentation (conceptual — query.py)

**Source:** `backend/app/api/query.py` lines 205–235

Not a Pydantic model; represents the three logical strings derived from a single user question before the retrieval pipeline executes. Documented here to formalise the invariant separating retrieval from generation.

| Field | Derived value | Purpose |
|-------|--------------|---------|
| `retrieval_question` | Stripped of language/style instructions | Sent to vector-store search; must be semantically neutral |
| `answer_instruction` | Language/style directive only | Appended to LLM generation prompt; never sent to the vector store |
| `question` | Verbatim user input | Echoed in the response for attribution |

**Invariant:** `retrieval_question` must not contain phrases like "answer in Spanish" or "respond formally". Such directives belong exclusively in `answer_instruction`. Any change to the splitting logic in `query.py` must preserve this contract and add a corresponding unit test in `backend/tests/unit/test_query_splitting.py`.

---

## 7. ReadinessStatus (runtime)

**Source:** `backend/app/main.py` — `_readiness_status()`

Returned by `GET /api/readiness`. The endpoint returns HTTP 200 when `status = "ready"` and HTTP 503 when `status = "degraded"`. `GET /api/health` (liveness) always returns 200 regardless.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"ready" \| "degraded"` | Aggregate health; `"degraded"` if any component is degraded |
| `components` | `dict[str, ComponentHealth]` | Keyed by component name (see below) |

**ComponentHealth shape:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"ready" \| "degraded"` | Component-level health |
| `detail` | `str` | Human-readable explanation (safe for external exposure) |

**Components checked:**

| Key | Check performed |
|-----|----------------|
| `auth` | `SECRET_KEY` is non-empty and meets minimum entropy |
| `openai` | `OPENAI_API_KEY` is non-empty |
| `vector_store` | Store type detected + connectivity probe (list call) |
| `file_store` | Store type detected + token/credential present |
| `speech` | `OPENAI_API_KEY` present (reused for TTS) |

### 7a. Readiness State Machine

```
Server starts
     │
     ▼
 _readiness_status() called
     │
     ├─ All components "ready"  ──► { status: "ready" }   HTTP 200
     │
     └─ Any component "degraded" ─► { status: "degraded" } HTTP 503
                                         │
                                         └─ Kubernetes/load-balancer
                                            removes pod from rotation
                                            until probe returns 200
```

**Note:** Readiness is re-evaluated on every probe call (no caching). This is intentional so that late-binding config (e.g. a secret injected via Vercel env after deploy) is reflected within one probe interval.

---

## 8. ExportLimits (config)

**Source:** `backend/app/config.py`

Configuration fields that govern voice export behaviour. All are already present as attributes; this table documents them together for clarity.

| Config attribute | Env var | Type | Default | Description |
|-----------------|---------|------|---------|-------------|
| `max_export_transcript_chars` | `MAX_EXPORT_TRANSCRIPT_CHARS` | `int` | `8000` | Hard cap on transcript length accepted by the export endpoint |
| `max_audio_duration_seconds` | `MAX_AUDIO_DURATION_SECONDS` | `int` | `240` | Maximum TTS output duration before the job is aborted |
| `export_artifact_ttl_seconds` | `EXPORT_ARTIFACT_TTL_SECONDS` | `int` | `300` | Seconds after job completion before audio bytes are discarded |
| `export_job_ttl_seconds` | `EXPORT_JOB_TTL_SECONDS` | `int` | `600` | Seconds after job creation before the entire job record is evicted |

**Relationship:** `export_artifact_ttl_seconds` ≤ `export_job_ttl_seconds` must always hold. The artifact expires before the job record so clients can still retrieve error details after audio is gone.

---

## 9. SecurityHeaderPolicy (doc entity)

**Source:** `backend/app/main.py` security-headers middleware

Documentation-only entity describing every HTTP security header emitted on API responses. No Pydantic model exists.

| Header | Value | Notes |
|--------|-------|-------|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-sniffing (OWASP A05) |
| `X-Frame-Options` | `DENY` | Blocks all framing |
| `X-XSS-Protection` | `1; mode=block` | Legacy XSS filter for older browsers |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer leakage |
| `Permissions-Policy` | `geolocation=(), microphone=(self), camera=()` | Allows microphone only for same-origin (voice chat). **CORRECTED** from `microphone=()` which broke voice chat |
| `Content-Security-Policy` | `default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'` | Strict deny-by-default for API responses |
| `X-Request-ID` | `<uuid>` | Correlation ID propagated from client or generated per-request |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | **Production only** — not set in development |

**OWASP mapping:** A01 (frame-ancestors), A02 (HSTS), A03 (CSP), A05 (MIME, XSS-Protection), A09 (X-Request-ID for log correlation).

---

## 10. GuardrailCoverageMatrix (test artifact)

**Source:** `backend/tests/unit/test_guardrail_coverage.py` (parametrised)

Not a runtime model. A parametrisation map ensuring every text surface that flows through the pipeline is covered by at least one guardrail check, a redaction assertion, and an audit-log assertion.

| Field | Type | Description |
|-------|------|-------------|
| `surface_name` | `str` | Unique name of the text surface |
| `guardrail_fn` | `str` | Fully-qualified name of the guardrail function under test |
| `test_file` | `str` | Relative path of the test file containing the coverage case |
| `test_name` | `str` | `pytest` node ID of the parametrised test case |
| `redaction_applied` | `bool` | True if the guardrail redacts the surface before downstream use |
| `audit_logged` | `bool` | True if a block/flag event is emitted to the audit log |

**Covered surfaces:**

| `surface_name` | `guardrail_fn` | `redaction_applied` | `audit_logged` |
|---------------|---------------|--------------------|--------------------|
| `typed_input` | `guardrails.engine.check_input` | `True` | `True` |
| `voice_transcript` | `guardrails.engine.check_input` | `True` | `True` |
| `multilingual_input` | `guardrails.engine.check_input` | `True` | `True` |
| `translated_query` | `guardrails.engine.check_input` | `True` | `True` |
| `generated_answer` | `guardrails.engine.check_output` | `True` | `True` |
| `playback_text` | `guardrails.engine.check_output` | `True` | `True` |
| `transcript_export` | `guardrails.engine.check_output` | `True` | `True` |
| `audio_synthesis_input` | `guardrails.engine.check_output` | `True` | `True` |

**Invariant:** Every row must have `audit_logged = True`. A surface where `redaction_applied = False` requires an explicit justification comment in the test parametrisation.

---

## Cross-Entity Relationships

```
VoiceExportJob
  └─ artifact: VoiceExportArtifact       (1:0..1, embedded)
  └─ owner_key ──► session/role scope    (no FK, opaque string)
  └─ ExportLimits ──► TTL fields         (config drives expires_at calculation)

SafeAppError
  └─ category ──► AuditEvent.error_category  (mirrored on error log emission)

AuditEvent
  └─ request_id ◄──► X-Request-ID header    (SecurityHeaderPolicy)

RetrievalQueryRepresentation
  └─ retrieval_question ──► vector_store search
  └─ answer_instruction ──► LLM generation prompt
  └─ question ──► response attribution

ChatLanguage
  └─ speech ──► VoiceExportArtifact.mime_type  (TTS locale drives codec choice)

ReadinessStatus
  └─ components["openai"] ──► ExportLimits (speech TTL only meaningful if key present)
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-05-24 | Initial data model for spec 005 (US1–US7) |
