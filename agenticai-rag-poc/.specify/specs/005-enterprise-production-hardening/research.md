# Research: Enterprise Production Hardening

**Phase 0 output for plan.md** | Date: 2026-05-24

---

## 1. Permissions-Policy microphone bug (US2 / Gap 1)

### Finding

`backend/app/main.py`, line 153, inside `_apply_common_headers()`:

```python
response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
```

`microphone=()` is the deny-all form of the directive. The W3C Permissions Policy
specification states that an empty allow-list (`()`) blocks the feature for ALL
origins, including the page's own origin. This breaks the voice-chat microphone
input that the app supports.

The two production Vercel configs already use the correct value:
- `vercel.json` line 33: `"geolocation=(), microphone=(self), camera=()"`
- `frontend/vercel.json` line 24: `"geolocation=(), microphone=(self), camera=()"`

The integration test `test_security_headers.py::test_backend_security_headers_are_minimal_for_api`
(line 34) currently asserts `"geolocation=(), microphone=(), camera=()"` — it matches the
broken backend value and will need to be updated alongside the fix.

A second test at line 65 already asserts `microphone=(self)` for both vercel.json
files and will continue to pass.

### Decision

- Decision: Change `microphone=()` to `microphone=(self)` in `_apply_common_headers()`
  in `backend/app/main.py` line 153 only.
- Rationale: The backend serves API responses, not browser pages, so the Permissions-Policy
  on `/api/*` responses is advisory. However, keeping it consistent with the frontend policy
  prevents split-brain confusion and aligns with the principle that all surfaces should share
  the same security intent. `(self)` restricts microphone to the app's own origin.
- Alternatives considered: Remove the Permissions-Policy header from backend API responses
  entirely (it only applies to browser contexts). Rejected because the header is harmless
  on API responses and provides defence-in-depth for browsers that apply it transitively.

### Implementation

File: `backend/app/main.py`, line 153.
Change: `"geolocation=(), microphone=(), camera=()"` → `"geolocation=(), microphone=(self), camera=()"`.

File: `backend/tests/integration/test_security_headers.py`, line 34.
Update the assertion `assert resp.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"` to `"geolocation=(), microphone=(self), camera=()"`.

---

## 2. CSP architecture split — API vs. frontend (US2 / Gap 2)

### Finding

The project has three distinct serving tiers, each with its own CSP:

**Backend (`backend/app/main.py` lines 154-156):**
```
default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'
```
This is a strict deny-all CSP appropriate for a JSON API server. The backend does not
serve HTML, JS, or any browser-rendered content. This is correct as-is.

**Vite dev server (`frontend/vite.config.ts`):**
No CSP headers are set. Vite's dev server has no built-in CSP support. This is acceptable
because the dev server is not a production surface.

**Docker Compose production (`frontend/nginx.conf` lines 7-11):**
```
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
```
No CSP header is set. nginx.conf is missing the Content-Security-Policy header entirely.
It also has `microphone=()` (the broken deny-all form).

**Vercel production (both `vercel.json` and `frontend/vercel.json`):**
Both files already define a complete, production-grade CSP:
```
default-src 'self'; base-uri 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:;
object-src 'none'; frame-ancestors 'none'; form-action 'self'; manifest-src 'self';
media-src 'self' blob:; worker-src 'self' blob:; upgrade-insecure-requests
```
Permissions-Policy is already correct: `geolocation=(), microphone=(self), camera=()`.

### Decision

- Decision (nginx.conf): Add a `Content-Security-Policy` header matching the Vercel CSP to
  `frontend/nginx.conf`. Also fix `Permissions-Policy` to use `microphone=(self)`.
- Rationale: Docker Compose production deployments currently serve the frontend with no CSP
  protection. Adding the same policy used in Vercel closes the gap without introducing drift.
- Alternatives considered: Generate nginx.conf from a shared template. Rejected as premature
  complexity; a direct sync is sufficient for the current deployment footprint.

### Implementation

File: `frontend/nginx.conf`.
Add after existing `add_header` lines:
```
add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; form-action 'self'; manifest-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; upgrade-insecure-requests" always;
```
Fix existing line: `microphone=()` → `microphone=(self)`.

Test: Extend `test_security_headers.py::test_vercel_production_headers_cover_browser_features`
or add a new nginx-focused unit test that reads `frontend/nginx.conf` and asserts both
headers are present and correct.

---

## 3. Guardrail coverage matrix testing (US1 / Gap 3)

### Finding

The guardrail engine (`backend/app/guardrails/engine.py`) is a pure function: it takes
text and a target (`"input"` or `"output"`) and returns a `GuardrailResult`. It is already
exercised by `tests/unit/test_guardrails.py` and `tests/unit/test_guardrails_safety.py`.

The call sites where guardrails are actually invoked in the pipeline are:

| Surface | Location | Covered? |
|---------|----------|----------|
| Typed query (original) | `api/query.py:211` `_check_input_guardrail(clean_question)` | Yes — unit + integration |
| Chat history messages | `api/query.py:216` `_check_input_guardrail(message.content)` | Untested |
| Language instruction | `api/query.py:218` `_check_input_guardrail(answer_instruction)` | Untested |
| Generated answer (output) | `api/query.py:257` `_guardrail_engine.check(result["answer"], "output")` | Integration only |
| Voice transcript (export) | `api/voice_export.py:210-211` via `_export_text()` → `build_redacted_transcript()` | Untested at surface level |
| Audio synthesis input | `api/voice_export.py:466` after redaction | Untested |
| Transcript redaction endpoint | `api/voice_export.py:574-576` | Untested at surface level |
| Audit metadata fields | `core/audit.py:19-21` `_safe_value()` → `redact_sensitive_text()` | `test_audit.py` partial |

There is no single test file that verifies every surface in one parametrized sweep.
`test_guardrails.py` and `test_guardrails_safety.py` test the engine and `sanitize_query`
respectively, but not the integration of the engine with voice export or the language
instruction surface.

### Decision

- Decision: Add `backend/tests/unit/test_guardrail_coverage_matrix.py` — a parametrized
  pytest test with one row per surface. Each row mocks the engine and asserts the surface
  calls it with the expected text and target. The voice export surfaces use
  `redact_sensitive_text` / `build_redacted_transcript` directly (not the engine), so those
  rows verify redaction is applied rather than engine invocation.
- Rationale: A single parametrized test file is easier to audit than scattered assertions
  across many files. Mocking the engine keeps the test fast and deterministic.
- Alternatives considered: Integration test that sends HTTP requests per surface. Rejected
  because it requires the full agent stack including LLM mocks; unit parametrization is
  faster and equally conclusive for coverage proof.

### Implementation

New file: `backend/tests/unit/test_guardrail_coverage_matrix.py`.

Parametrize over:
1. `query_input_original` — mock `GuardrailEngine.check`, call `_check_input_guardrail`.
2. `query_input_history` — call `_check_input_guardrail` with a history message body.
3. `query_language_instruction` — call `_check_input_guardrail` with a non-en instruction.
4. `query_output` — mock `GuardrailEngine.check` for target `"output"`.
5. `voice_export_transcript` — call `redact_sensitive_text` with a PII-containing string, assert `[REDACTED_EMAIL]` in result.
6. `voice_export_messages` — call `build_redacted_transcript` with a PII message, assert redacted.
7. `audit_metadata` — call `audit_event` with a raw secret in metadata, assert it does not appear in the log output.

---

## 4. Export size limits and thresholds (US4 / Gap 4)

### Finding

All export limits are currently defined as module-level constants in
`backend/app/api/voice_export.py` lines 29-39:

```python
_MAX_MESSAGE_CHARS = 6000
_MAX_MESSAGES = 100
_MAX_TRANSCRIPT_CHARS = 12000
_MAX_AUDIO_INPUT_CHARS = 4000
_MAX_AUDIO_BYTES = 10 * 1024 * 1024   # 10 MB
_OPENAI_REQUEST_TIMEOUT_SECONDS = 30.0
_ASYNC_EXPORT_JOB_TTL_SECONDS = 15 * 60    # 15 min
_ASYNC_EXPORT_ARTIFACT_TTL_SECONDS = 10 * 60   # 10 min
```

These are not surfaced in `backend/app/config.py` and cannot be changed via environment
variables or the Settings UI. `_MAX_TRANSCRIPT_CHARS = 12000` exceeds the safe Vercel
serverless response body limit for audio. At 128 kbps MP3, 12,000 chars ≈ ~6-8 minutes
of speech ≈ ~6-8 MB, which is within the 10 MB `_MAX_AUDIO_BYTES` guard but can exceed
Vercel's 4.5 MB serverless response body limit for synchronous responses.

The async (deferred) path (`_should_defer_export`) already activates automatically in
production (`app_env == "production"`) and when `len(transcript) > _MAX_AUDIO_INPUT_CHARS`,
which provides a practical safety valve. The `_MAX_AUDIO_BYTES = 10 MB` guard at the
artifact level is the last hard stop.

`config.py` has no export-related fields today. The VoiceExportJobStore TTL is set
from module-level constants at import time, not from config.

### Decision

- Decision: Document the existing limits in `config.py` as read-only informational
  properties rather than migrating all constants to config. The async-first production
  path is the correct architectural answer to Vercel limits.
- Rationale: Moving module-level constants to config would require threading `get_settings()`
  into the VoiceExportJobStore constructor and the Pydantic validators, which is a larger
  refactor than the spec requires. The existing `_should_defer_export` guard already
  activates the async path in production, which sidesteps the response body limit.
- Alternatives considered: Full migration of all export constants to `config.py`. Deferred
  to a future spec; not required for this hardening pass.
- Document accepted risk: A synchronous export with `_MAX_TRANSCRIPT_CHARS = 12000` chars
  could in theory exceed Vercel's 4.5 MB response body limit if TTS compresses poorly.
  Mitigated by `_MAX_AUDIO_BYTES = 10 MB` guard and automatic async deferral in production.

### Implementation

File: `backend/app/api/voice_export.py`.
Add a module-level docstring section documenting the relationship between the constants
and Vercel serverless limits. No code change required.

Add to `backend/tests/unit/test_guardrail_coverage_matrix.py` (or a dedicated
`test_voice_export_limits.py`): verify that `_enforce_transcript_limit` raises
`HTTP 413` for a transcript exceeding `_MAX_TRANSCRIPT_CHARS`, and that
`_enforce_audio_input_limit` raises for input exceeding `_MAX_AUDIO_INPUT_CHARS`.

---

## 5. Readiness liveness distinction (US6 / Gap 5)

### Finding

The implementation in `backend/app/main.py` already provides the correct
liveness/readiness split:

- `GET /api/health` (line 255-261): Liveness probe. Always returns `{"status": "ok"}`
  with HTTP 200 when the process is running. Adds `{"env": ...}` only in development.
  Does not call any external dependency.

- `GET /api/readiness` (line 359-363): Readiness probe. Calls `_readiness_status()` which
  checks `app_config`, `openai`, `vector_store`, `file_store`, and `export` components.
  Returns HTTP 503 when any component is `"degraded"`.

The test file `backend/tests/integration/test_api_readiness.py` covers the critical
scenarios:
- `test_health_is_liveness_not_dependency_readiness` (line 26): patches `get_effective_api_key`
  to raise, confirms health returns 200 while readiness returns 503.
- `test_readiness_dependency_failure_surface_is_sanitized` (line 40): confirms exception
  messages do not leak into the readiness response.

Both `/api/health` and `/readiness` (Vercel-stripped prefix) are tested.

The Vercel deployment in `vercel.json` sets `maxDuration: 60` for the backend service.
No additional readiness probe configuration is needed.

### Decision

- Decision: No code change required for the liveness/readiness split. The implementation
  is correct and tested.
- Rationale: The existing `_readiness_status()` function returns 503 for any degraded
  component as required by FR-026. The test suite proves the 503 path.
- Alternatives considered: Adding a `/api/startup` probe. Not needed; `readiness` covers
  the same purpose for Kubernetes/Vercel health checks.

### Implementation

No production code changes. Verify test coverage by confirming
`test_health_is_liveness_not_dependency_readiness` exercises the 503 path
for each component type. If any component failure path is untested, add a parametrized
case to `test_api_readiness.py`.

---

## 6. Exception handler audit — bare `except` clauses (US7 / Gap 6)

### Finding

A systematic grep of all routers for bare `except Exception` clauses:

**`backend/app/api/documents.py`** — All `except Exception` blocks either:
- Call `safe_app_error_from_exception(exc, ...)` and re-raise (upload, list, delete, file read), or
- Log with `error_type=type(exc).__name__` and continue (availability checks, chunk reads).
No raw exception messages reach the HTTP response. Compliant.

**`backend/app/api/query.py`** — Lines 240-254: `except Exception as exc` calls
`safe_app_error_from_exception(exc, default="internal_error")`. Compliant.

**`backend/app/api/voice_export.py`** — Lines 498-511: `except Exception as exc` checks
`isinstance(exc, HTTPException)` before re-raising, then calls `_raise_safe_error(...)` with
a static message. The raw exception type is logged via `error_type=type(exc).__name__` but
the message is never forwarded to the client. Compliant.

**`backend/app/api/settings.py`** — `_run_ragas_eval_background` (line 934):
`except Exception as exc: _log.error("ragas_trigger.failed", error_type=type(exc).__name__)`.
This is a background task with no HTTP response; the pattern is correct.

**`backend/app/api/guardrails.py`** — Not yet read; inspect for bare `except` clauses.

**`backend/app/auth/router.py`** — Not yet read; inspect for bare `except` clauses.

**`backend/app/main.py`** — Global exception handler (line 216): returns safe 500 with
`{"detail": "An internal error occurred.", "request_id": ...}`. Compliant. The middleware
`except` block (line 175) does the same. Compliant.

The only pattern that needed review was `voice_export.py` lines 498-511, which uses
`_raise_safe_error` (a private helper that raises `HTTPException` with a static code/message)
rather than `SafeAppError`. This is functionally equivalent but diverges stylistically from
the `SafeAppError` pattern used elsewhere. It is acceptable for this module because
`VoiceExportJobStore` and the TTS pipeline have their own error taxonomy.

### Decision

- Decision: Audit `guardrails.py` and `auth/router.py` for bare `except` clauses.
  If found, replace with `safe_app_error_from_exception()` or a static `_raise_safe_error`
  pattern. No changes needed to `documents.py`, `query.py`, `voice_export.py`, or `main.py`.
- Rationale: The major routers are already compliant. The remaining routers are smaller and
  likely clean, but must be verified before closing US7.
- Alternatives considered: Static analysis via `ast.parse` to find all `except` clauses.
  Useful for CI but out of scope for this hardening pass.

### Implementation

Read `backend/app/api/guardrails.py` and `backend/app/auth/router.py`.
For any `except Exception as e: raise HTTPException(status_code=500, detail=str(e))` pattern,
replace with:
```python
except Exception as exc:
    safe_error = safe_app_error_from_exception(exc, default="internal_error")
    raise safe_error from exc
```
Add test cases in the relevant unit/integration test files to verify that a simulated
dependency failure returns a safe error response (no raw exception message in body).

---

## 7. Guardrails API router exception handling (US7 — guardrails.py audit)

### Finding

`backend/app/api/guardrails.py` manages CRUD for guardrail rules. The store operations
(`store.add_rule`, `store.update_rule`, `store.delete_rule`, `store.get_rule`) can raise
`ValueError` (for validation errors) or other exceptions (store access failures). Current
state must be verified by reading the file.

Expected pattern from similar routers: `ValueError` → HTTP 422 with a safe message;
all other exceptions → `safe_app_error_from_exception` or the global handler.

### Decision

- Decision: Read `guardrails.py` at implementation time and apply the `safe_app_error_from_exception`
  pattern to any `except Exception` blocks that currently forward raw exception messages.
- Rationale: Guardrail rule operations are admin-only and low-risk (no external I/O), but
  consistency with the rest of the codebase reduces the surface area for accidental information
  disclosure.

### Implementation

File: `backend/app/api/guardrails.py`.
Pattern: Wrap store operation calls in `try/except`; `ValueError` → HTTP 422 static message;
`Exception` → `safe_app_error_from_exception(exc, default="internal_error")`.

---

## Summary of Decisions

| Gap | Decision | Files Changed |
|-----|----------|---------------|
| 1 — Permissions-Policy microphone | `microphone=()` → `microphone=(self)` in `main.py` | `backend/app/main.py`, `tests/integration/test_security_headers.py` |
| 2 — CSP in nginx.conf | Add full CSP + fix microphone in `nginx.conf` | `frontend/nginx.conf` |
| 3 — Guardrail coverage matrix | New parametrized unit test covering all 7 text surfaces | `backend/tests/unit/test_guardrail_coverage_matrix.py` |
| 4 — Export limits | Document existing limits; no config migration; add limit boundary tests | `backend/app/api/voice_export.py` (docstring), tests |
| 5 — Liveness/readiness split | Already implemented and tested; no code change | — |
| 6 — Exception handler audit | `documents.py`, `query.py`, `voice_export.py`, `main.py` compliant; audit `guardrails.py`, `auth/router.py` | TBD after file inspection |
| 7 — guardrails.py audit | Apply `safe_app_error_from_exception` to any raw `except` blocks | `backend/app/api/guardrails.py` |
