# Implementation Plan: Enterprise Production Hardening

**Branch**: `005-enterprise-production-hardening` | **Date**: 2026-05-24 | **Spec**: `.specify/specs/005-enterprise-production-hardening/spec.md`

## Summary

Harden the Agentic RAG application across seven enterprise-readiness dimensions: consistent security controls and audit coverage on all chat/voice/export surfaces (US1); correct browser security headers including a Permissions-Policy microphone fix (US2); maintainable chat architecture already refactored into sub-components (US3); reliable async audio/transcript export with defined size limits (US4); clean multilingual retrieval query separation (US5); operational health and readiness observability (US6); and typed safe exception handling replacing broad catch-all handlers (US7).

Most infrastructure is already in place. The remaining work is: one Permissions-Policy line fix, nginx.conf CSP + microphone headers, a parametrized guardrail coverage matrix test, exception handler audits in two remaining routers, and comprehensive test coverage for all hardening surfaces.

---

## Technical Context

**Language/Version**: Python 3.11–3.13 (backend), TypeScript/React 18 (frontend)
**Primary Dependencies**: FastAPI 0.115.6, LangGraph 1.2.0, LangChain 1.3.1, ChromaDB 0.6.3, React 18.3.1, Vite 6.0.7, Tailwind 3.4.17
**Storage**: ChromaDB (local/Docker), Pinecone (optional), Vercel Blob (file store), in-memory fallback
**Testing**: pytest (unit + integration), Vitest (frontend unit), Playwright (E2E)
**Target Platform**: Linux server (Docker Compose) + Vercel serverless (production)
**Project Type**: Full-stack web service (FastAPI API + React SPA)
**Performance Goals**: <500ms p95 for chat queries; export non-blocking UI; transcript exports ≤8 000 chars; audio exports ≤240 s of content
**Constraints**: Vercel 4.5 MB response body limit; no persistent runtime between requests (serverless); `VECTOR_STORE_TYPE=memory` on Vercel
**Scale/Scope**: Single-tenant admin + guest-session model; up to 100 indexed documents

---

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Tests written before implementation | ✓ PASS | TDD ordering enforced in tasks.md |
| OWASP Top 10 reviewed | ✓ PASS | See Phase 0 research summary and OWASP table below |
| No new top-level `.md` files | ✓ PASS | All docs go into existing `docs/*.md` |
| No broad exception handlers swallowing defects | ⚠ PARTIAL | 2 routers still require audit: `guardrails.py`, `auth/router.py` |
| Coverage ≥ 98% | ✓ ENFORCED | Run `pytest --cov=app` before merge |
| No hardcoded credentials | ✓ PASS | All secrets via env / settings_store |
| Parallel subagents for independent subtasks | ✓ PASS | Enforced in tasks.md [P] labels |

**Post-design re-check**: Permissions-Policy fix and nginx.conf change are low-risk one-liners. Re-run test_security_headers.py after applying.

---

## Project Structure

### Documentation (this feature)

```text
.specify/specs/005-enterprise-production-hardening/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── api-hardening.json        # Security header + readiness contract (Phase 1)
│   └── requirements-target.txt  # (existing — LangGraph upgrade phase)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code

```text
backend/
├── app/
│   ├── main.py                          # Fix Permissions-Policy microphone=(self); security middleware
│   ├── config.py                        # ExportLimits group documentation
│   ├── core/
│   │   ├── audit.py                     # audit_event (complete — no changes)
│   │   ├── errors.py                    # SafeAppError, categorize_exception (complete — no changes)
│   │   └── chat_languages.py            # Shared language contract (complete — no changes)
│   ├── guardrails/
│   │   └── engine.py                    # Guardrail engine (complete — no changes)
│   ├── voice/
│   │   ├── redaction.py                 # redact_sensitive_text (complete — no changes)
│   │   └── export_jobs.py               # VoiceExportJobStore (complete — no changes)
│   └── api/
│       ├── query.py                     # retrieval/answer split complete
│       ├── voice_export.py              # Async export + redaction (complete)
│       ├── guardrails.py                # Exception handler audit — replace bare except if found
│       └── settings.py                  # Exception handler audit — replace bare except if found
│
├── tests/
│   ├── unit/
│   │   ├── test_guardrail_coverage_matrix.py  # NEW — 8 parametrized surface tests
│   │   ├── test_redaction.py                  # Extend: PII/PCI/secrets pattern assertions
│   │   ├── test_security_headers.py           # Fix: microphone=(self) assertion
│   │   └── test_errors.py                     # Exception categorization coverage
│   └── integration/
│       ├── test_api_readiness.py              # 503 degraded-dep tests (extend existing)
│       └── test_api_query.py                  # Verify input trimming end-to-end

frontend/
├── src/
│   └── lib/
│       └── chatLanguages.ts             # Frontend language contract (synced from backend)

└── tests/
    └── unit/
        └── ChatInterface.test.tsx       # Guardrail coverage assertions

nginx/
└── nginx.conf                           # Add Content-Security-Policy header; fix microphone=(self)
```

---

## Complexity Tracking

> No constitution violations requiring justification.

---

## Phase 0 Research Summary

See `research.md` for full findings. Key decisions:

### 1. Permissions-Policy microphone fix (US2 — confirmed bug)
- **Finding**: `backend/app/main.py:153` has `microphone=()` which denies the app's own origin, breaking voice chat. Both `vercel.json` files already use the correct `microphone=(self)`.
- **Decision**: One-line fix in `main.py`. Update the matching assertion in `test_security_headers.py`.
- **Also**: `frontend/nginx.conf` has the same bug and is missing CSP. Fix both in same commit.

### 2. CSP scope (US2 — resolved, partial gap in nginx)
- **Decision**: Backend API CSP (`default-src 'none'`) is correct for a JSON-only API server. Frontend CSP is on Vercel config (already correct) and nginx.conf (fix needed). No Vite dev-server CSP required (dev mode only).
- **Rationale**: Split deployment — API serves only JSON; HTML/JS/CSS served by nginx or Vercel.

### 3. Guardrail coverage matrix (US1, FR-003)
- **Decision**: New `backend/tests/unit/test_guardrail_coverage_matrix.py` with 8 parametrized cases — one per text surface.
- **Surfaces**: typed_input, voice_transcript, multilingual_input, translated_query, generated_answer, playback_text, transcript_export, audio_synthesis_input.
- **Rationale**: Machine-checkable proof of coverage without duplicating implementation logic.

### 4. Export limits (US4, FR-028)
- **Decision**: Module-level constants in `voice_export.py` are authoritative. Document them; add boundary tests. No config migration.
- **Limits**: max_transcript=8 000 chars, max_audio=240 s, artifact_ttl=300 s, job_ttl=600 s.
- **Rationale**: `_should_defer_export()` guard already activates async mode for Vercel deployments.

### 5. Liveness/readiness (US6, FR-026 — complete)
- **Decision**: No code changes needed. `/api/health` = liveness (always 200), `/api/readiness` = readiness (503 when degraded).
- **Rationale**: Implementation already matches spec requirements.

### 6. Exception handler audit (US7, FR-023)
- **Decision**: Audit `guardrails.py` and `auth/router.py` at implementation time. Replace raw `except Exception` patterns with `safe_app_error_from_exception()`.
- **Rationale**: `documents.py`, `query.py`, `voice_export.py`, and `main.py` are already compliant.

---

## Phase 1 Design

See `data-model.md` for full entity definitions. See `contracts/api-hardening.json` for API contract.

### Guardrail coverage matrix (8 surfaces)

| Surface | Backend function | Redaction | Audit |
|---------|-----------------|-----------|-------|
| typed_input | `sanitize_query` + `guardrail_engine.check_input` | ✓ | ✓ |
| voice_transcript | `redact_sensitive_text` (voice_export.py) | ✓ | ✓ |
| multilingual_input | `sanitize_query` + `guardrail_engine.check_input` | ✓ | ✓ |
| translated_query | `guardrail_engine.check_input` (on retrieval_question) | ✓ | ✓ |
| generated_answer | `guardrail_engine.check_output` | ✓ | ✓ |
| playback_text | `redact_sensitive_text` (before browser TTS) | ✓ | — |
| transcript_export | `build_redacted_transcript` | ✓ | ✓ |
| audio_synthesis_input | `redact_sensitive_text` (before OpenAI TTS) | ✓ | ✓ |

### Security header policy (corrected)

| Header | Value | OWASP |
|--------|-------|-------|
| `X-Content-Type-Options` | `nosniff` | A05 |
| `X-Frame-Options` | `DENY` | A05 |
| `X-XSS-Protection` | `1; mode=block` | A05 |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | A05 |
| `Permissions-Policy` | `geolocation=(), microphone=(self), camera=()` | A05 |
| `Content-Security-Policy` | `default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'` | A05 |
| `X-Request-ID` | echo or new UUID | A09 |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (production only) | A02 |

---

## OWASP Review

| ID | Control | Status |
|----|---------|--------|
| A01 | Role/session isolation for all surfaces | Existing tests; guardrail matrix adds coverage |
| A02 | bcrypt+JWT unchanged; HSTS production-only | ✓ |
| A03 | `sanitize_query` + injection regexes cover typed and voice input | ✓ |
| A05 | CSP + Permissions-Policy — microphone bug confirmed and fixed | Pending nginx + main.py fix |
| A07 | Auth router exception audit — must not leak "user not found" vs "wrong password" | Pending audit |
| A09 | `audit_event` with safe metadata; no raw prompts/content logged | Guardrail matrix tests verify |

---

## Implementation Strategy

### MVP (minimum required before merge)

1. Fix `Permissions-Policy` in `main.py` + `nginx.conf` CSP (US2)
2. Add `test_guardrail_coverage_matrix.py` (US1, FR-003)
3. Audit + fix `guardrails.py` and `auth/router.py` exception handlers (US7)
4. Full test suite — all pass, coverage ≥ 98%

### Deferred (Post-MVP — tracked in PENDING_TASKS.md)

- Docker Compose integration test (blocked on Docker CLI availability)
- Live E2E walkthrough with OPENAI_API_KEY gated (T019 from upgrade tasks)
- Export performance regression benchmarks (US4 FR-028)
- Multilingual retrieval regression fixture corpus (US5 FR-029)
