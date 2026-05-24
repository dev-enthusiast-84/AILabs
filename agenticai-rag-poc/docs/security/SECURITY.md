# Security Reference

> [← Home](README.md)

OWASP Top 10 controls, authentication, input validation, upload safety, and secrets management.

## Security Documentation

- **[Content Guardrails](security/GUARDRAILS.md)** — Rule types (block/redact/flag), built-in rules, creating and managing custom rules
- **[Guardrails API](security/GUARDRAILS-API.md)** — curl examples and complete rule schema for REST API management
- **[Production Hardening](security/SECURITY-HARDENING.md)** — Runtime hardening beyond the OWASP baseline: typed error isolation, timing mitigations

---

## OWASP Top 10 Coverage

| Risk | Control | Location |
|------|---------|---------|
| **A01 Broken Access Control** | `require_full_access` dependency blocks guests on write/admin endpoints (HTTP 403). Guest JWT carries `role: "guest"`. | `auth/utils.py`, `api/documents.py`, `api/settings.py`, `api/guardrails.py` |
| **A02 Cryptographic Failures** | Passwords hashed with bcrypt. JWT HS256 signed with `SECRET_KEY`; raises `RuntimeError` at startup if left as default in non-development. | `auth/utils.py`, `main.py` |
| **A03 Injection** | bleach strips XSS. Regex patterns detect prompt/SQL injection before any LLM or DB operation. Filename sanitisation blocks path traversal. Guardrail regex validated with `re.compile` at creation. | `guardrails/safety.py`, `guardrails/engine.py` |
| **A04 Insecure Design** | Token budget hard cap (`MAX_COMPLETION_TOKENS`). Per-IP rate limits on auth (10/min), queries (10/min), guest uploads (5/min). Guest uploads capped at 2 MB; admin at 20 MB (4 MB on Vercel). Indexed-document caps bound file/vector storage growth. | `config.py`, `api/query.py`, `api/documents.py` |
| **A05 Security Misconfiguration** | HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, strict CSP via Vercel headers. `Server` header stripped. Swagger UI disabled when `APP_ENV=production`. | `main.py`, `vercel.json` |
| **A06 Vulnerable Components** | Dependencies pinned in `requirements.txt`. ClamAV daemon (optional) scans uploads against current malware signatures. | `requirements.txt`, `rag/scanner.py` |
| **A07 Auth Failures** | Login rate-limited to 10 req/min per IP. Uniform error on auth failure (no username enumeration). Guest tokens expire after 15 min. JWT JTI enforces one-time guest settings gate. | `auth/router.py`, `auth/utils.py` |
| **A08 Data Integrity** | File extension allowlist. Magic-byte validation rejects mismatched content. ZIP-bomb detection (100 MB limit). Stored prompt-injection scan before indexing. | `rag/scanner.py`, `api/documents.py` |
| **A09 Logging Failures** | `structlog` structured logging. Startup banner suppressed in production. Guardrail violations logged server-side; no rule detail leaked to client. | `main.py`, `guardrails/engine.py` |
| **A10 SSRF** | No server-initiated HTTP to user-controlled URLs. OpenAI calls use only the configured key; no user-supplied endpoints are followed. | `rag_agent.py`, `vector_store.py` |

---

## Authentication and Session Management

**JWT structure:**

| Field | Value |
|-------|-------|
| Algorithm | HS256 |
| Signing key | `SECRET_KEY` env var — minimum 32 random bytes |
| Admin expiry | 45 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| Guest expiry | 15 minutes (`GUEST_TOKEN_EXPIRE_MINUTES`) |
| JTI | UUID4 in every token — enforces guest one-time settings gate |

**Password storage:** bcrypt; plaintext never stored. **Guest enforcement:** `require_full_access` returns HTTP 403 with a uniform message regardless of token state (missing, expired, or guest-scoped) — prevents role enumeration.

---

## Input Validation and Injection Prevention

All user-supplied text passes through `sanitize_query()` in `guardrails/safety.py`:

1. **bleach strip** — removes HTML tags and dangerous attributes (XSS)
2. **Injection regex** — blocks prompt-injection (`ignore previous`, `you are now`, `system:`) and SQL injection patterns (`DROP TABLE`, `SELECT *`, `OR 1=1`)
3. **Length cap** — queries over `MAX_QUERY_LENGTH` (default 1000 chars) → HTTP 422

Filename inputs pass through `validate_filename()`: rejects `..`, `/`, `\`, null bytes, absolute paths, and names over 255 characters.

---

## Upload Safety

| Check | What it catches |
|-------|----------------|
| **Early peek check** | First bytes read *before* any vector-store I/O: empty files → 422; Windows PE (`MZ`) / ELF / shell-script executable headers → 422. Fires even when the vector store is degraded (503), so validation errors are never masked by infrastructure failures. |
| **Extension allowlist** | Only `pdf`, `txt`, `csv`, `xlsx`, `xls` accepted |
| **Magic-byte validation** | File content checked against declared MIME type |
| **ZIP-bomb detection** | Decompressed size capped at 100 MB |
| **ClamAV scan** *(optional)* | File streamed to ClamAV if `CLAMAV_HOST` set; detected malware → HTTP 400 |
| **Stored prompt-injection** | Document text scanned for LLM override patterns before embedding |

### Stored Prompt-Injection Protection

All uploaded files are scanned with regex patterns in `rag/scanner.py` before indexing. Content matching known injection patterns (e.g., `ignore previous instructions`, `[INST]`, `###instruction`) is rejected with HTTP 422 before it reaches the vector store.

### ClamAV Integration

If `CLAMAV_HOST` is set, uploaded files are streamed to the ClamAV daemon for malware scanning before indexing. If the daemon is unreachable, scanning is skipped with a logged warning (fail-open). ClamAV is only available in Docker and self-hosted deployments; it cannot run on Vercel serverless functions.

---

## Security Headers

Set in `vercel.json` (Vercel) and `main.py` middleware (local/Docker):

| Header | Value |
|--------|-------|
| `Strict-Transport-Security` | Vercel: `max-age=63072000; includeSubDomains; preload`; backend production: `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Content-Security-Policy` | Vercel: self-only scripts, same-origin API/analytics connections, blob frames/workers/media for previews/downloads, `object-src 'none'`, `frame-ancestors 'none'`; backend API: `default-src 'none'` |
| `Permissions-Policy` | Vercel UI allows `microphone=(self)` for voice and denies camera/geolocation; backend API denies microphone/camera/geolocation |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Server` | Stripped (not sent) |

---

## Secrets Management

| Secret | Storage | Production action |
|--------|---------|------------------|
| `OPENAI_API_KEY` | Settings UI in production; `backend/.env` only for local development | Rotate in the provider dashboard, then re-enter in Settings UI |
| `SECRET_KEY` | `backend/.env` | Generate: `openssl rand -hex 32`; rotate: `redeploy-vercel.sh --secret-key` |
| `ADMIN_PASSWORD` | `backend/.env` (auto-generated) | Rotate: `redeploy-vercel.sh --admin-password gen` |

- `SECRET_KEY` default or `ADMIN_PASSWORD` unset both raise `RuntimeError` at startup (non-development). Neither is ever written to logs or API responses.

---

## Security Logging (structlog)

| Event | Log level | Detail leaked to client |
|-------|-----------|------------------------|
| Auth failure (wrong password) | WARNING | Uniform `"Incorrect username or password"` — no detail |
| Guest access to restricted endpoint | WARNING | Fixed `"This action requires a full account."` |
| Guardrail block | INFO | `"Query blocked by content policy."` — no rule detail |
| Guardrail flag | INFO | Server-side only — client receives unmodified response |
| Guardrail redact | INFO | Client receives redacted text; no rule detail leaked |
| Upload rejected (type/size/AV) | WARNING | Generic rejection message |
| Startup banner | INFO | Shown only in `development` — suppressed in `production` and `test` |
