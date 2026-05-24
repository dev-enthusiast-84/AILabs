# Feature Specification: Runtime Settings

**Feature Branch**: `brownfield/settings`
**Created**: 2026-05-04
**Status**: Brownfield (describes existing behaviour)
**Input**: Brownfield reverse-spec of `backend/app/api/settings.py` and
`backend/app/settings_store.py`

---

> **Brownfield note**: This spec describes what the system CURRENTLY does. No new
> development is implied. All behaviour is sourced directly from the production code.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin Reads Current Settings (Priority: P1)

An administrator opens the settings panel and sees the currently active OpenAI model,
a masked representation of the API key, its origin (runtime override vs. environment
file vs. not configured), and the list of models they may switch to.

**Why this priority**: The GET endpoint is the baseline — callers need to know the
current effective state before deciding whether to update it.

**Independent Test**: Send `GET /api/settings/` with a valid admin JWT; assert HTTP 200
with a `SettingsResponse` containing `model`, `api_key_masked`, `api_key_source`, and
`allowed_models`. Verify the real API key does NOT appear in the response.

**Acceptance Scenarios**:

1. **Given** a runtime API key has been set via `apply_runtime_settings()`,
   **When** `GET /api/settings/` is called,
   **Then** `api_key_masked` is in the format `"sk-****...<last-4-chars>"` and
   `api_key_source` is `"runtime"`.

2. **Given** no runtime key is set but `OPENAI_API_KEY` is present in the environment,
   **When** `GET /api/settings/` is called,
   **Then** `api_key_masked` is in the format `"sk-****...<last-4-chars> (from environment)"`
   and `api_key_source` is `"environment"`.

3. **Given** neither a runtime key nor an environment key is configured,
   **When** `GET /api/settings/` is called,
   **Then** `api_key_masked` is an empty string and `api_key_source` is `"not_configured"`.

4. **Given** any state of key configuration,
   **When** `GET /api/settings/` is called,
   **Then** `allowed_models` is a sorted list containing exactly the models from the
   `ALLOWED_MODELS` frozenset: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4`,
   `gpt-3.5-turbo`, `o1-preview`, `o1-mini`.

---

### User Story 2 - Admin Updates the API Key and/or Model (Priority: P1)

An administrator enters a new OpenAI API key or selects a different model from the
dropdown. The server validates both, applies them to the runtime store, and resets the
agent singleton so the next query uses the new configuration.

**Why this priority**: Enables zero-downtime key rotation and model switching without
restarting the server.

**Independent Test**: POST `{"api_key": "sk-proj-abc...xyz", "model": "gpt-4o-mini"}`
with an admin JWT; assert HTTP 200, `api_key_masked` ends with the last 4 chars of the
new key, and `model` equals `"gpt-4o-mini"`.

**Acceptance Scenarios**:

1. **Given** a valid admin JWT and a body with both `api_key` and `model`,
   **When** `POST /api/settings/` is called,
   **Then** both values pass validation, are applied via `apply_runtime_settings()`,
   and the response reflects the new masked key and model.

2. **Given** only `api_key` is provided (no `model`),
   **When** `POST /api/settings/` is called,
   **Then** the API key is updated; the model remains unchanged; the response shows
   the previous effective model.

3. **Given** only `model` is provided (no `api_key`),
   **When** `POST /api/settings/` is called,
   **Then** the model is updated; the API key remains unchanged.

4. **Given** valid settings are applied,
   **When** `apply_runtime_settings()` is called internally,
   **Then** `app.agents.rag_agent._AGENT` is set to `None`, forcing the LangGraph
   agent to be rebuilt with the new key/model on the next query. The vector store
   cache is NOT cleared.

5. **Given** an HTML-injected api_key string (e.g., `<script>sk-abc</script>`),
   **When** the request body is validated,
   **Then** `bleach.clean()` strips the HTML tags before the key is validated, so the
   stored key contains only the sanitised string.

---

### User Story 3 - API Key Format Is Rejected If Invalid (Priority: P1)

A user submits an API key that does not match the expected OpenAI format. The server
must reject it with a clear validation error before attempting to use it.

**Why this priority**: Prevents obviously wrong keys from being applied and causing
cryptic LLM errors on subsequent queries.

**Independent Test**: POST `{"api_key": "not-a-real-key"}` and assert HTTP 422 with
`errors.api_key` containing the format error message.

**Acceptance Scenarios**:

1. **Given** an `api_key` value that does not match `^sk(-proj)?-[A-Za-z0-9_\-]{20,}$`,
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 422 with `{"detail": {"api_key": "API key format is invalid..."}}`.

2. **Given** an `api_key` that is an empty string after sanitization,
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 422 with `{"detail": {"api_key": "API key must not be empty."}}`.

3. **Given** an `api_key` longer than 200 characters,
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 422 with
   `{"detail": {"api_key": "API key exceeds maximum allowed length."}}`.

4. **Given** `model` is set to a string not in `ALLOWED_MODELS` (e.g., `"gpt-5"`),
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 422 with `{"detail": {"model": "Model 'gpt-5' is not in
   the allowed list. Supported models: ..."}}`.

5. **Given** both `api_key` and `model` fail validation simultaneously,
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 422 with both error keys present in `detail`.

---

### User Story 4 - Guest Uses the Settings Endpoint Exactly Once (Priority: P2)

A guest user (read-only JWT) may configure a custom API key and model once per session.
On a second attempt within the same JWT lifetime, the server refuses with HTTP 409.

**Why this priority**: Prevents guests from re-configuring settings arbitrarily while
still allowing the one-time self-service key setup envisioned for the guest tier.

**Independent Test**: Obtain a guest JWT with a unique `jti` claim; POST valid settings;
assert HTTP 200. POST again with the same JWT; assert HTTP 409 with the session-locked
error message.

**Acceptance Scenarios**:

1. **Given** a guest JWT whose `jti` has NOT yet been used for settings,
   **When** `POST /api/settings/` is called with valid `api_key` and/or `model`,
   **Then** the response is HTTP 200 and the settings are applied.

2. **Given** the same guest JWT is used again for a second settings POST,
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 409 with
   `"Guest settings can only be configured once per session. Start a new guest session to change your API key or model."`.

3. **Given** a guest JWT with a missing or empty `jti` claim,
   **When** `POST /api/settings/` is called,
   **Then** the endpoint treats this as "already used" and returns HTTP 409
   (empty `jti` is functionally indistinguishable from a blank already-seen key).

4. **Given** a guest settings POST fails validation (e.g., bad api_key format),
   **When** the HTTP 422 is returned,
   **Then** the guest JTI is NOT added to `_guest_settings_used`, preserving the
   one remaining attempt.

---

### User Story 5 - Neither Field Provided Returns a Validation Error (Priority: P3)

A client sends a POST body with both `api_key` and `model` omitted (or both null).
The server must reject this as a no-op rather than silently doing nothing.

**Why this priority**: Prevents ambiguous empty-update calls that would give callers
a false impression that settings were changed.

**Independent Test**: POST `{}` or `{"api_key": null, "model": null}`; assert HTTP 422
with `"Provide at least one of: api_key, model."`.

**Acceptance Scenarios**:

1. **Given** a POST body where both `api_key` and `model` are `null` or absent,
   **When** `POST /api/settings/` is called,
   **Then** the response is HTTP 422 with
   `{"detail": "Provide at least one of: api_key, model."}`.

2. **Given** the no-op check triggers,
   **When** the 422 is returned,
   **Then** `apply_runtime_settings()` is NOT called and no state is changed.

---

### User Story 6 - Rate Limiting on Settings Updates (Priority: P3)

A client that fires too many settings updates within a short window is throttled.

**Why this priority**: OWASP A04 — prevents brute-force API key probing via the
settings endpoint.

**Independent Test**: Fire 21 POST requests from the same IP within one minute; assert
the 21st returns HTTP 429.

**Acceptance Scenarios**:

1. **Given** a single IP has already sent 20 settings POST requests within one minute,
   **When** a 21st request arrives,
   **Then** the response is HTTP 429 Too Many Requests.

---

### Edge Cases

- **Unauthenticated request**: Both GET and POST require a valid JWT via
  `get_current_user`. Requests without a token return HTTP 401.

- **JWT decode error during guest check**: If the JWT cannot be decoded inside the
  POST handler (malformed token), the `jti` is set to `""`, which is treated as
  already-used, and HTTP 409 is returned.

- **Runtime settings are in-memory only**: `_runtime_api_key` and `_runtime_model`
  are module-level variables; they reset to `""` on process restart. The `.env`
  values become effective again after a restart.

- **Masked key format for environment key vs. runtime key differs**: Runtime key:
  `"sk-****...<last4>"`. Environment key: `"sk-****...<last4> (from environment)"`.
  These formats are display conventions, not functional differences.

- **`api_key_source` precedence**: `"runtime"` takes priority if a runtime key is
  set, regardless of whether an environment key also exists.

- **Agent singleton reset is not vector-store reset**: `apply_runtime_settings()` sets
  `_AGENT = None` in `rag_agent` but does NOT call `lru_cache` clear on
  `get_vector_store`. Already-indexed documents remain queryable after a key change.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `GET /api/settings/` MUST return `model`, `api_key_masked`,
  `api_key_source`, and `allowed_models`. It MUST be accessible to any authenticated
  user (guest or admin).

- **FR-002**: The `api_key_masked` field MUST always be the masked representation —
  never the raw key. The real key MUST NOT appear in any response body or log entry
  (OWASP A02).

- **FR-003**: `api_key_source` MUST be exactly one of `"runtime"`, `"environment"`,
  or `"not_configured"`, determined by: runtime key set → `"runtime"`;
  else env key present → `"environment"`; else → `"not_configured"`.

- **FR-004**: `allowed_models` MUST be returned as a sorted list from the `ALLOWED_MODELS`
  frozenset (currently 7 models).

- **FR-005**: `POST /api/settings/` MUST sanitize `api_key` and `model` fields with
  `bleach.clean(tags=[], strip=True)` before any validation (OWASP A03).

- **FR-006**: `api_key` MUST be validated against the regex `^sk(-proj)?-[A-Za-z0-9_\-]{20,}$`.
  Validation MUST also reject empty strings and strings longer than 200 characters.

- **FR-007**: `model` MUST be validated against the `ALLOWED_MODELS` frozenset. Any
  model name not in the set MUST be rejected with a descriptive error listing
  the supported values.

- **FR-008**: If either or both of `api_key` / `model` fail validation, the response
  MUST be HTTP 422 with a `detail` object mapping each failing field name to its
  error message. `apply_runtime_settings()` MUST NOT be called.

- **FR-009**: If both `api_key` and `model` are null/absent, the response MUST be
  HTTP 422 (returned as a `JSONResponse` with `422` status) before validation.

- **FR-010**: `apply_runtime_settings()` MUST update the module-level `_runtime_api_key`
  and/or `_runtime_model` under a threading lock, then reset `app.agents.rag_agent._AGENT`
  to `None`. It MUST log the event with key redacted as `"***"` (OWASP A09).

- **FR-011**: Guest users MUST be limited to exactly one successful settings POST per
  JWT session, tracked by the JWT `jti` claim in the in-memory `_guest_settings_used` set.

- **FR-012**: A guest's JTI MUST be added to `_guest_settings_used` ONLY after a
  successful `apply_runtime_settings()` call (i.e., not on validation error).

- **FR-013**: `POST /api/settings/` MUST be rate-limited to 20 requests per minute
  per client IP address.

- **FR-014**: `get_effective_api_key()` and `get_effective_model()` MUST fall back to
  the `.env`-sourced `Settings` values when the corresponding runtime override is empty.

### Key Entities

- **SettingsResponse**: API response model.
  Fields: `model` (str), `api_key_masked` (str), `api_key_source` (str —
  `"runtime"` | `"environment"` | `"not_configured"`), `allowed_models` (list[str]).

- **SettingsUpdateRequest**: API request model.
  Fields: `api_key` (str | None), `model` (str | None). Both sanitized by
  `bleach.clean()` via Pydantic `field_validator`.

- **Runtime state** (module-level in `settings_store.py`):
  - `_runtime_api_key: str` — empty string means "use environment".
  - `_runtime_model: str` — empty string means "use environment default".
  - `_lock: threading.Lock` — guards all reads and writes.

- **ALLOWED_MODELS**: Immutable `frozenset` of 7 model name strings:
  `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`,
  `o1-preview`, `o1-mini`.

- **_guest_settings_used**: In-memory `set[str]` in `api/settings.py`.
  Stores JWT `jti` values of guests who have already consumed their one settings update.
  Resets on process restart.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full OpenAI API key NEVER appears in a `GET /api/settings/` response
  body or any structlog entry — only the masked form is ever serialised (OWASP A02).

- **SC-002**: An API key failing the regex validation (`^sk(-proj)?-[A-Za-z0-9_\-]{20,}$`)
  is rejected with HTTP 422 in 100% of tested cases.

- **SC-003**: A model name not in `ALLOWED_MODELS` is rejected with HTTP 422 in 100%
  of tested cases; the error message lists all supported values.

- **SC-004**: After a successful `POST /api/settings/`, the next `run_agent()` call
  uses the new key/model (because `_AGENT` is `None` and is rebuilt by `get_agent()`),
  and previously indexed vector store documents remain accessible.

- **SC-005**: A guest JWT cannot produce more than one successful settings mutation;
  any second attempt returns HTTP 409 regardless of the fields supplied.

- **SC-006**: A 20/minute per-IP rate cap is enforced; the 21st POST from the same
  IP within one minute returns HTTP 429.

---

## Assumptions

- The `_guest_settings_used` set is in-memory and per-process. In a multi-worker
  deployment, different workers may not share this set, so the one-time gate is
  per-worker, not per-cluster.

- JWT `jti` claims are expected to be unique per guest token. The `POST /api/auth/guest`
  endpoint is assumed to generate a `jti` (UUID) for every token it issues; if it does
  not, guests with no `jti` are always treated as having exhausted their one setting.

- The `bleach.clean()` sanitization in `SettingsUpdateRequest` validators runs before
  regex validation, so HTML-injected keys will be stripped to their tag-free content
  before format validation occurs.

- Runtime settings are not persisted to disk. After a server restart, `_runtime_api_key`
  and `_runtime_model` revert to `""`, and the effective values revert to whatever is
  in `backend/.env`.

- `get_effective_api_key()` and `get_effective_model()` acquire `_lock` on every call.
  This is designed for a single-process uvicorn server; if the process count is scaled
  beyond one, runtime settings changes in one process will not propagate to others.

- The `ALLOWED_MODELS` frozenset is defined at module load time and is not configurable
  via environment variables; adding a new model requires a code change.
