# Production Hardening Controls

> [← Security Reference](security/SECURITY.md) · [← Home](README.md)

Runtime hardening applied on top of the OWASP baseline: typed error isolation,
PII-safe audit logging, dependency health checks, and voice export guardrails.

---

## SafeAppError — Typed Exception Pattern (`app/core/errors.py`)

All module-level catches in API routers translate raw exceptions into `SafeAppError`
before the response is sent, preventing internal messages from reaching the client.

**`ErrorCategory` literal type** — one of:

| Value | Meaning |
|-------|---------|
| `openai_provider_error` | Upstream OpenAI / LLM call failed |
| `vector_store_error` | ChromaDB / Pinecone operation failed |
| `blob_storage_error` | Vercel Blob or file-store write/read failed |
| `storage_error` | Generic persistence layer failure |
| `retrieval_error` | RAG retrieval pipeline error |
| `internal_error` | Catch-all for unexpected exceptions |

**`SafeAppError` dataclass fields:**

| Field | Type | Purpose |
|-------|------|---------|
| `category` | `ErrorCategory` | Stable category string safe to expose to callers |
| `status_code` | `int` | HTTP status to return (4xx / 5xx) |
| `public_message` | `str` | Human-readable message safe for client consumption |
| `cause_type` | `str` | `type(exc).__name__` — class name only, never the message |
| `metadata` | `dict` | Additional structured context (no raw messages) |

**`categorize_exception(exc)`** inspects only `type(exc).__name__` and
`type(exc).__module__` — never `str(exc)` or `exc.args` — so secrets, prompts,
and PII in exception messages can never leak into structured logs or API responses.

---

## `audit_event()` PII Redaction (`app/core/audit.py`)

Every call to `audit_event()` applies the following pipeline before any I/O:

1. All `str` values in the `metadata` dict are passed through `redact_sensitive_text()`.
2. Each value is truncated to **160 characters** after redaction.
3. The final entry is emitted as a structured `structlog` record at INFO level.

**Log schema** (all fields present on every event):

| Field | Example |
|-------|---------|
| `event` | `"audit_event"` |
| `event_type` | `"query"` / `"upload"` / `"voice_export"` / `"settings_change"` |
| `status` | `"ok"` / `"rejected"` / `"error"` |
| `user_id` | anonymised subject from JWT |
| `user_role` | `"admin"` / `"guest"` |
| `endpoint` | `"/api/query"` |
| `error_category` | `ErrorCategory` value or omitted when status is `"ok"` |

Raw content, credentials, and prompts are **never** written to audit logs.

---

## GET /api/readiness — Health Endpoint (`app/main.py`)

Public endpoint — no authentication required. Used by load-balancers and uptime
monitors to detect degraded components.

**Behaviour:**

- Checks each registered component (vector store, LLM provider, file store) in parallel.
- Returns **HTTP 200** when all components are healthy.
- Returns **HTTP 503** when one or more components are degraded.
- Each component entry in the response body contains `ok: bool` and `reason: str`.
- Component failures are logged with `error_type` (class name) only — the exception
  message and stack trace are never included in the log entry or the response body,
  preventing internal topology details from leaking through the health endpoint.

---

## Voice Export Guardrail Coverage (`app/api/voice_export.py`)

Both `POST /api/voice/export` and `POST /api/voice/redact` apply the guardrail
engine to exported transcript text **before** any audio synthesis or PII redaction.

**Request flow:**

```
Transcript text
   ▼
GuardrailEngine.check(text, "input")
   ├── Blocked  → HTTP 400 {"code": "export_content_blocked"}
   │              audit_event("voice_export", status="rejected",
   │                          error_category="guardrail_blocked")
   ├── Flagged  → log.warning(rule_ids=[...])   # non-blocking; continues
   └── Allowed  → audio synthesis / PII redaction proceeds
   ▼
(redact endpoint only) redact_sensitive_text()  from app/voice/redaction.py
   ▼
Response returned to client
```

**Covered injection vectors:**

- SQL injection patterns detected by the `sql-injection` built-in rule.
- Prompt injection patterns detected by the `prompt-injection` built-in rule.
- Any custom `block` rules with target `input` or `both`.

This catches attempts to smuggle malicious content via the export API even when
the same content bypassed the query pipeline guardrail earlier in the session.
