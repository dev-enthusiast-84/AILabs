# Feature Specification: Authentication & Authorization

**Feature Branch**: `brownfield/auth`
**Created**: 2026-05-04
**Status**: Brownfield (describes current production behaviour)
**Input**: Existing implementation in `backend/app/auth/`

---

> **Brownfield notice**: This spec documents what the system **currently does**. It is
> derived directly from `backend/app/auth/router.py`, `backend/app/auth/utils.py`, and
> `backend/app/auth/models.py`. No new functionality is described here.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin Login (Priority: P1)

An administrator supplies a username and password to receive a signed JWT that grants
full write and admin access to all protected endpoints.

**Why this priority**: Login is the entry point for all privileged operations. Without it,
no document management or settings changes can take place.

**Independent Test**: Send `POST /api/auth/login` with valid admin credentials; verify the
response contains a bearer token and that the token can subsequently reach a
`require_full_access` endpoint without a 403.

**Acceptance Scenarios**:

1. **Given** the server has `ADMIN_PASSWORD` set and the admin user exists in the in-memory
   store, **When** a client sends `POST /api/auth/login` with the correct `username` and
   `password`, **Then** the server returns HTTP 200 with a JSON body containing
   `access_token` (non-empty string) and `token_type: "bearer"`.

2. **Given** a valid login has just succeeded, **When** the returned token is decoded,
   **Then** the JWT payload contains `sub` (admin username), `role: "admin"`, `exp`, `iat`,
   and a unique `jti` claim.

3. **Given** a correct username but wrong password, **When** a client calls
   `POST /api/auth/login`, **Then** the server returns HTTP 401 with
   `detail: "Invalid credentials"` — the message does not distinguish between a bad username
   and a bad password (uniform error, OWASP A07).

4. **Given** a client sends 10 login requests from the same IP within 60 seconds,
   **When** the 11th request arrives, **Then** the server returns HTTP 429 (Too Many
   Requests) and enforces the rate limit until the window resets.

5. **Given** a login request with `username` shorter than 3 characters or containing
   characters outside `[a-zA-Z0-9_]`, **When** the request is received, **Then** the server
   returns HTTP 422 Unprocessable Entity before any credential check is performed.

6. **Given** a login request with `password` shorter than 8 characters or longer than 128
   characters, **When** the request is received, **Then** the server returns HTTP 422
   Unprocessable Entity.

7. **Given** `ADMIN_PASSWORD` is not set in the environment, **When** the server starts,
   **Then** `_build_users()` raises `RuntimeError` and the server fails to initialise
   (startup banner describes the fix).

---

### User Story 2 - Guest Access (Priority: P1)

A visitor with no account obtains a short-lived read-only JWT without providing any
credentials, allowing them to use the chat interface and list documents.

**Why this priority**: Guest access is the primary discovery path. It must work independently
of the admin credential flow.

**Independent Test**: Send `POST /api/auth/guest` with no body; verify the response token
decodes to `sub: "guest"` and `role: "guest"`, and that the token is accepted by a
read-only endpoint but rejected by `require_full_access`.

**Acceptance Scenarios**:

1. **Given** any client (authenticated or not), **When** it sends `POST /api/auth/guest`
   with an empty body, **Then** the server returns HTTP 200 with a JSON body containing
   `access_token` (non-empty string) and `token_type: "bearer"`.

2. **Given** a guest token is issued, **When** it is decoded, **Then** the JWT payload
   contains `sub: "guest"`, `role: "guest"`, a valid `exp` set to
   `now + GUEST_TOKEN_EXPIRE_MINUTES` (default 15 minutes), `iat`, and a unique `jti`.

3. **Given** a guest token, **When** it is presented to a write/admin endpoint protected by
   `require_full_access` (e.g. document upload, delete, settings update), **Then** the server
   returns HTTP 403 with
   `detail: "This action requires a full account. Please sign in."`.

4. **Given** a client sends more than 10 guest token requests from the same IP within 60
   seconds, **When** the next request arrives, **Then** the server returns HTTP 429.

5. **Given** a guest token whose `exp` has passed, **When** it is presented to any
   protected endpoint, **Then** the server returns HTTP 401 with
   `detail: "Could not validate credentials"`.

---

### User Story 3 - Current User Info (Priority: P2)

Any authenticated user (admin or guest) can retrieve their own identity information to
confirm which role they hold and what username the server recognises them by.

**Why this priority**: The `GET /api/auth/me` endpoint allows the frontend to display the
user's role and gate UI elements without decoding the JWT client-side.

**Independent Test**: Obtain a token (admin or guest), then call `GET /api/auth/me` with it;
verify the response body matches the `username` and `role` embedded in the token.

**Acceptance Scenarios**:

1. **Given** a valid admin token, **When** a client sends `GET /api/auth/me` with it as a
   Bearer credential, **Then** the server returns HTTP 200 with
   `{"username": "<admin_username>", "role": "admin"}`.

2. **Given** a valid guest token, **When** a client sends `GET /api/auth/me`, **Then** the
   server returns HTTP 200 with `{"username": "guest", "role": "guest"}`.

3. **Given** no `Authorization` header, **When** a client calls `GET /api/auth/me`, **Then**
   the server returns HTTP 403 (FastAPI HTTPBearer rejects missing credentials).

4. **Given** a malformed or tampered JWT, **When** it is presented to `GET /api/auth/me`,
   **Then** the server returns HTTP 401 with
   `detail: "Could not validate credentials"`.

---

### User Story 4 - Role Enforcement on Write Endpoints (Priority: P1)

Guests are automatically blocked from any endpoint that mutates state. The
`require_full_access` FastAPI dependency is the single enforcement point.

**Why this priority**: Without role enforcement the guest token offers no security
boundary, defeating the purpose of the two-tier access model.

**Independent Test**: Obtain a guest token, then attempt `POST /api/documents/upload`,
`DELETE /api/documents/{filename}`, and `POST /api/settings/`; all must return HTTP 403
with the standard detail message.

**Acceptance Scenarios**:

1. **Given** a guest token, **When** any endpoint decorated with `require_full_access` is
   called, **Then** the server returns HTTP 403 before any business logic executes.

2. **Given** an admin token, **When** the same `require_full_access`-protected endpoint is
   called, **Then** the request proceeds normally (no 403).

3. **Given** the `_GUEST_USER` sentinel object (which has `role: "guest"`), **When**
   `authenticate_user()` is called with username `"guest"` and any password, **Then** the
   function returns `None` — the guest role cannot be promoted to a full session via the
   login endpoint.

---

### Edge Cases

- What happens when the JWT `sub` claim is missing? `decode_token()` raises a `ValueError`
  internally, which is caught and re-raised as HTTP 401 with
  `detail: "Could not validate credentials"`.
- What happens when a valid token belongs to a user who has been removed from `_USERS`?
  `get_current_user()` raises HTTP 401 with `detail: "User not found or disabled"`.
- What happens when a user's `disabled` flag is `True`? Both `authenticate_user()` and
  `get_current_user()` treat disabled users as non-existent (HTTP 401).
- What happens if `ADMIN_PASSWORD` is an empty string at startup? `_build_users()` treats
  it as unset and raises `RuntimeError`.
- What happens when the same IP makes exactly 10 requests per minute to `/login`? The 10th
  request succeeds; the 11th is rejected with HTTP 429.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose `POST /api/auth/login` and return a signed JWT on
  successful credential validation.
- **FR-002**: The login endpoint MUST be rate-limited to 10 requests per minute per source
  IP using `slowapi`.
- **FR-003**: The system MUST validate admin passwords using bcrypt (`passlib` with
  `bcrypt` backend). The plaintext password MUST never be stored or logged.
- **FR-004**: The JWT payload MUST include `sub` (username), `role`, `exp`, `iat`, and
  a unique `jti` (UUID4). The signing algorithm MUST be HS256.
- **FR-005**: Admin tokens MUST expire after `access_token_expire_minutes` (default
  45 minutes). Guest tokens MUST expire after `guest_token_expire_minutes` (default 15
  minutes). Both values MUST be configurable via environment variables.
- **FR-006**: The system MUST expose `POST /api/auth/guest` which issues a read-only JWT
  without requiring any credentials. This endpoint MUST also be rate-limited to 10/minute
  per IP.
- **FR-007**: The system MUST expose `GET /api/auth/me` which returns the `username` and
  `role` of the bearer token holder. This endpoint requires a valid token (admin or guest).
- **FR-008**: The `require_full_access` dependency MUST reject tokens with `role: "guest"`
  with HTTP 403 and the message
  `"This action requires a full account. Please sign in."`.
- **FR-009**: Failed login attempts MUST return a uniform HTTP 401 error message
  (`"Invalid credentials"`) regardless of whether the username or password was incorrect
  (OWASP A07 — prevents username enumeration).
- **FR-010**: The `LoginRequest` model MUST enforce: `username` 3–64 characters matching
  `^[a-zA-Z0-9_]+$`; `password` 8–128 characters. Violations return HTTP 422.
- **FR-011**: The in-memory user store MUST be built at server startup from `ADMIN_PASSWORD`.
  If the variable is absent or empty, the server MUST fail to start with a descriptive
  `RuntimeError`.
- **FR-012**: The `_GUEST_USER` sentinel MUST be present in `_USERS` at all times, but
  `authenticate_user()` MUST reject attempts to authenticate as guest via the login endpoint
  (role check guards this path).

### Key Entities

- **UserInDB**: Represents a user record in the in-memory store. Fields: `username` (str),
  `hashed_password` (str, empty for guest), `disabled` (bool, default `False`),
  `role` (str: `"admin"` | `"guest"`).
- **LoginRequest**: Input model for `POST /api/auth/login`. Fields: `username` (str,
  3–64 chars, alphanumeric + underscore), `password` (str, 8–128 chars).
- **TokenResponse**: Output model for all auth endpoints that issue a JWT. Fields:
  `access_token` (str), `token_type` (str, always `"bearer"`).
- **TokenData**: Internal model produced by `decode_token()`. Fields: `username`
  (str | None).
- **JWT payload**: Contains `sub`, `role`, `exp` (UTC epoch), `iat` (UTC epoch), `jti`
  (UUID4 string). Signed with HS256 using `SECRET_KEY`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `POST /api/auth/login` with correct credentials returns HTTP 200 and a
  non-empty `access_token` in under 500 ms (including bcrypt verification).
- **SC-002**: The 11th login request from the same IP within 60 seconds receives HTTP 429.
- **SC-003**: A guest token used on any `require_full_access` endpoint returns HTTP 403
  in 100% of attempts with the prescribed detail message.
- **SC-004**: A token whose `exp` has elapsed is rejected with HTTP 401 on every request.
- **SC-005**: The uniform error message `"Invalid credentials"` is returned for all failed
  login attempts (wrong username, wrong password, or disabled user) — no variance.
- **SC-006**: Starting the server without `ADMIN_PASSWORD` set fails with a `RuntimeError`
  before accepting any requests.
- **SC-007**: 100% of the unit and integration test cases in `backend/tests/unit/` and
  `backend/tests/integration/` related to auth pass with no mocks bypassed.

---

## Assumptions

- The in-memory user store (`_USERS`) holds exactly one admin account per server process.
  Multi-user or database-backed user management is out of scope for the current
  implementation.
- JWT revocation (token blacklisting) is not implemented; tokens remain valid until their
  `exp` is reached. Logout is handled purely client-side by discarding the token.
- The `SECRET_KEY` used to sign JWTs is read from the `SECRET_KEY` environment variable.
  The insecure default value (`"change-me-..."`) is intentional for local development only
  and MUST be rotated before production deployment.
- Rate limiting state is in-process (not shared across replicas). In a multi-replica
  deployment, each replica enforces its own counter independently.
- The `GUEST_TOKEN_EXPIRE_MINUTES` default is 15 minutes as set in `config.py`. The comment
  in `router.py` referencing "480 min / 8 h" reflects an earlier draft; the authoritative
  value is the `Settings` class field.
- bcrypt cost factor is determined by the `bcrypt.gensalt()` default (currently 12 rounds).
  This is applied at startup when hashing `ADMIN_PASSWORD` into `_USERS`.
- The `WWW-Authenticate: Bearer` response header is included on all HTTP 401 responses
  from auth endpoints, per RFC 6750.
- The frontend stores the JWT in `localStorage` and attaches it via an axios interceptor;
  this is the only supported token transport mechanism.
