# Quickstart: Enterprise Production Hardening

**How to develop, verify, and test the hardening changes locally.**

---

## Prerequisites

- Backend venv active: `cd backend && source .venv/bin/activate`
- Frontend deps installed: `cd frontend && npm ci`
- `.env` with a valid `OPENAI_API_KEY`

---

## Local development flow

```bash
# 1. Start full stack
cd backend && uvicorn app.main:app --reload --port 8000 &
cd frontend && npm run dev   # :5173, proxies /api → :8000

# 2. Verify security headers
curl -I http://localhost:8000/api/health | grep -E "Permissions-Policy|Content-Security|X-Frame|X-Content"
# Expect: Permissions-Policy: geolocation=(), microphone=(self), camera=()

# 3. Check readiness endpoint
curl -s http://localhost:8000/api/readiness | jq .
# Expect status=ready (or degraded with named component if a dep is down)

# 4. Test redaction endpoint directly
curl -X POST http://localhost:8000/api/voice_export/redact \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"My API key is sk-proj-abc123xyz789"},{"role":"assistant","content":"I can help."}]}'
# Expect: content contains [REDACTED_API_KEY], not the original key

# 5. Test guardrail coverage (unit)
cd backend && pytest tests/unit/test_guardrail_coverage_matrix.py -v

# 6. Full backend suite
cd backend && pytest tests/unit/ tests/integration/ -v --cov=app --cov-report=term-missing
# Expect: ≥98% coverage, all tests pass

# 7. Frontend unit tests (includes redact.test.ts)
cd frontend && npm test
```

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `development` | `production` enables HSTS and suppresses startup banner |
| `OPENAI_API_KEY` | — | Required for LLM calls and readiness check |
| `VECTOR_STORE_TYPE` | `chroma` | `memory` for Vercel (ephemeral), `chroma`/`pinecone` for persistent |
| `FILE_STORE_TYPE` | `local` | `blob` for Vercel Blob storage |
| `MAX_EXPORT_TRANSCRIPT_CHARS` | `8000` | Hard limit on transcript size for export |

---

## Security header verification

```bash
# Backend API headers (should always be present on every /api/* route)
curl -si http://localhost:8000/api/health | grep -E \
  "X-Content-Type|X-Frame|Referrer|Permissions|Content-Security|X-Request-ID|Strict-Transport"

# Expected values:
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
# Referrer-Policy: strict-origin-when-cross-origin
# Permissions-Policy: geolocation=(), microphone=(self), camera=()
# Content-Security-Policy: default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'
# X-Request-ID: <uuid>
```

---

## Running the guardrail coverage matrix tests

```bash
cd backend
pytest tests/unit/test_guardrail_coverage_matrix.py -v --tb=short

# Output: 8 parametrized cases — one per text surface:
# PASSED test_guardrail_coverage_matrix[typed_input]
# PASSED test_guardrail_coverage_matrix[voice_transcript]
# PASSED test_guardrail_coverage_matrix[multilingual_input]
# PASSED test_guardrail_coverage_matrix[translated_query]
# PASSED test_guardrail_coverage_matrix[generated_answer]
# PASSED test_guardrail_coverage_matrix[playback_text]
# PASSED test_guardrail_coverage_matrix[transcript_export]
# PASSED test_guardrail_coverage_matrix[audio_synthesis_input]
```

---

## Verifying redaction (backend)

```bash
# Confirm PII is scrubbed from transcripts
cd backend && python -c "
from app.voice.redaction import redact_sensitive_text
samples = [
    'My email is test@example.com',
    'SSN: 123-45-6789',
    'Card: 4111 1111 1111 1111',
    'sk-proj-abcdef1234567890abcd',
    'password=s3cr3t!',
]
for s in samples:
    print(redact_sensitive_text(s))
"
```

---

## Verifying display masking (frontend)

```bash
cd frontend
# Run the redact unit tests
npm test -- --reporter=verbose redact

# Manual check: start the app and send a message containing an API key or email.
# The rendered message should show [REDACTED_API_KEY] or [REDACTED_EMAIL].
```

---

## Docker Compose (when Docker is available)

```bash
# Build and start full stack
docker compose up --build

# Verify headers from nginx-served frontend
curl -I http://localhost:3000 | grep -E "Content-Security|Permissions"
# Expect CSP and Permissions-Policy headers from nginx.conf

docker compose down
```

---

## Readiness degradation test

```bash
# Start backend without OPENAI_API_KEY to trigger degraded readiness
OPENAI_API_KEY="" uvicorn app.main:app --port 8001 &
curl -s http://localhost:8001/api/readiness | jq '{status, openai: .components.openai}'
# Expect: {"status": "degraded", "openai": {"status": "degraded"}}
# HTTP 503

# Liveness still passes (process is running)
curl -o /dev/null -w "%{http_code}" http://localhost:8001/api/health
# Expect: 200
```
