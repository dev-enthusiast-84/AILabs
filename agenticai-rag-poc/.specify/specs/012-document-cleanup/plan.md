# Implementation Plan: Document Cleanup

**Branch**: `012-document-cleanup` | **Date**: 2026-05-24 | **Spec**: `.specify/specs/012-document-cleanup/spec.md`

## Summary

Add an ownership-aware document cleanup system with four independently testable slices: (1) guest auto-cleanup on new session start, (2) admin manual cleanup with cadence presets, (3) upload-limit warning with force-mode bypass, and (4) zero-cost email and push notifications via SMTP and ntfy.sh.

Every cleanup operation removes documents from both the vector index (ChromaDB or Pinecone) and the file store (local disk or Vercel Blob). Isolation is structural — admin and guest sweep predicates filter by `owner_role` before any deletion, making cross-role deletion impossible.

---

## Technical Context

**Language/Version**: Python 3.11–3.13 (backend), TypeScript/React 18 (frontend)
**Primary Dependencies**: FastAPI 0.115.6, ChromaDB/Pinecone, Vercel Blob, React 18.3.1, Vite 6.0.7, Tailwind 3.4.17, httpx (already in requirements)
**Storage**: ChromaDB or Pinecone (vector chunks) + local disk or Vercel Blob (raw files + chunk manifests)
**Testing**: pytest (unit + integration), Vitest (frontend unit)
**Target Platform**: Local Docker Compose + Vercel serverless
**Project Type**: Full-stack web service (FastAPI backend + React SPA)
**Performance Goals**: Cleanup sweep ≤ 5 s for ≤ 500 documents; non-blocking for concurrent queries
**Constraints**: `BackgroundTasks` for non-blocking HTTP; Vercel stateless — no persistent scheduler; rate limit on cleanup endpoint
**Scale/Scope**: Per-deployment; single-process on local, ephemeral serverless on Vercel

---

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Tests BEFORE implementation | ✓ PASS | Test tasks numbered before impl in tasks.md (TDD order) |
| OWASP A01 Access Control | ✓ PASS | Cleanup endpoint requires `require_full_access`; guest sweep is session-scoped; admin/guest filters structurally disjoint |
| OWASP A03 Injection | ✓ PASS | All inputs via Pydantic models; cadence enum validated server-side; bleach on notification fields |
| OWASP A04 Rate Limiting | ✓ PASS | `@limiter.limit("2/minute")` on `POST /api/documents/cleanup` |
| OWASP A09 Logging | ✓ PASS | `audit_event` on every cleanup with count, trigger, cadence, force flag; no document content logged; SMTP password excluded from all logs |
| Performance — no blocking I/O | ✓ PASS | Cleanup runs in `BackgroundTasks`; notification dispatch via `asyncio.to_thread` |
| No hardcoded credentials | ✓ PASS | All config from env vars / runtime settings |
| No new top-level .md files | ✓ PASS | Docs in `.specify/specs/012-…/` and existing `docs/*.md` |
| Coverage ≥ 98% on new modules | ✓ TARGET | `app/rag/cleanup.py` and `app/core/notifications.py` must be fully unit-tested |

---

## Project Structure

### Documentation (this feature)

```text
.specify/specs/012-document-cleanup/
├── plan.md                       # This file
├── research.md                   # Phase 0
├── data-model.md                 # Phase 1
├── quickstart.md                 # Phase 1
├── contracts/
│   └── api-doc-cleanup.json      # Phase 1 (OpenAPI fragment)
└── tasks.md                      # Phase 2 (/speckit-tasks)
```

### Source Code (new / changed files)

```text
backend/
├── app/
│   ├── rag/
│   │   └── cleanup.py                    # NEW: CleanupService, isolation predicates, _select_documents_for_cleanup
│   ├── core/
│   │   └── notifications.py              # NEW: send_limit_warning, send_test_notification, SMTP + ntfy.sh
│   ├── api/
│   │   ├── documents.py                  # Add POST /cleanup + GET /cleanup/status; hook guest sweep
│   │   ├── settings.py                   # Add cadence fields + doc count/limit + notification fields
│   │   └── notifications.py              # NEW router: POST /api/notifications/test
│   ├── runtime/
│   │   └── settings_store.py             # Add cadence getters/setters, persist cadence globals
│   └── config.py                         # Add admin_cleanup_cadence, cadence custom fields,
│                                         # admin_max_indexed_documents, notification_* fields
└── tests/
    ├── unit/
    │   ├── test_cleanup.py               # NEW: CleanupService isolation + cadence + force mode
    │   ├── test_documents_cleanup.py     # NEW: endpoint unit tests (auth, rate limit, schema)
    │   └── test_notifications.py         # NEW: SMTP + ntfy.sh mocked, deduplication, test endpoint
    └── integration/
        └── test_documents_cleanup_integration.py  # NEW: full sweep via TestClient

frontend/
├── src/
│   ├── components/
│   │   ├── SettingsModal.tsx             # Document Retention section + Notifications section
│   │   └── DocumentList.tsx             # Amber near-limit banner + guest session-pruned message
│   ├── services/
│   │   └── api.ts                       # triggerCleanup(), getCleanupStatus(), sendTestNotification()
│   └── types/
│       └── index.ts                     # CleanupResult, CleanupStatusResponse, CleanupCadence; extended SettingsResponse
└── tests/
    └── unit/
        ├── SettingsModal.test.tsx        # Cadence selector, force mode flow, result card, notifications section
        └── DocumentList.test.tsx        # Near-limit amber banner, guest pruned message
```

---

## Phase 0 Research Summary

See `research.md` for full findings. Key decisions:

| Decision | Rationale |
|----------|-----------|
| `BackgroundTasks` for manual cleanup | Vercel serverless; HTTP response returns before sweep |
| Request-time guest cleanup on `GET /api/documents/` | Fits stateless serverless; no scheduler required |
| Ownership metadata filter | `owner_role` + `owner_session` + `uploaded_at` already in every chunk; no schema migration |
| Cadence as preset enum + custom | More intuitive in UI than a bare integer; resolves to `retention_hours` at runtime |
| `force` flag bypasses age threshold | Recovery path when near-limit warning is active |
| Dual-store cleanup (vector + file) | Follows existing `_cleanup_document_storage()` pattern |
| Zero-cost notifications (stdlib SMTP + ntfy.sh) | No paid service; `smtplib` ships with Python; `httpx` already in requirements |
| Module-level `_last_cleanup_result` cache | Simple; fits single-instance model; status endpoint returns "no result" after Vercel cold-start (documented assumption) |

---

## Phase 1 Design

See `data-model.md` for full entity definitions. See `contracts/api-doc-cleanup.json` for OpenAPI fragment.

### Cadence preset → retention hours mapping

| Preset | UI label | `retention_hours` |
|--------|----------|-----------------|
| `hourly` | Every hour | 1 |
| `daily` | Every day | 24 |
| `weekly` | Every week | 168 |
| `biweekly` | Every two weeks | 336 |
| `monthly` | Every month (default) | 720 |
| `custom` | Custom | `value × (1 if hours else 24)` |

### Isolation predicates

```python
# Admin sweep (normal) — never touches guest docs
def _admin_filter(meta: dict, cutoff_ts: int) -> bool:
    return meta.get("owner_role") == "admin" and int(meta.get("uploaded_at", 0)) < cutoff_ts

# Admin sweep (force) — age-independent, still never touches guest docs
def _admin_force_filter(meta: dict) -> bool:
    return meta.get("owner_role") == "admin"

# Guest sweep — never touches admin docs or current-session guest docs
def _guest_session_filter(meta: dict, current_session: str) -> bool:
    return meta.get("owner_role") == "guest" and meta.get("owner_session", "") != current_session
```

### API contract

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/documents/cleanup` | Admin JWT | Start sweep; `{"force": true}` bypasses age threshold |
| `GET` | `/api/documents/cleanup/status` | Admin JWT | Return last cleanup result |
| `POST` | `/api/notifications/test` | Admin JWT | Send test notification to all configured channels |

Guest cleanup is internal — triggered automatically during `GET /api/documents/` when a new session token is detected. No public endpoint.

### New environment variables

| Env var | Default | Purpose |
|---------|---------|---------|
| `ADMIN_CLEANUP_CADENCE` | `monthly` | Default cadence preset |
| `ADMIN_CLEANUP_CUSTOM_VALUE` | `30` | Custom cadence numeric value |
| `ADMIN_CLEANUP_CUSTOM_UNIT` | `days` | Custom cadence unit (`hours` or `days`) |
| `ADMIN_MAX_INDEXED_DOCUMENTS` | `100` | Near-limit threshold base |
| `NOTIFICATION_ENABLED` | `false` | Master notification switch |
| `NOTIFICATION_EMAIL` | `""` | Recipient email address |
| `NOTIFICATION_SMTP_HOST` | `""` | e.g. `smtp.gmail.com` |
| `NOTIFICATION_SMTP_PORT` | `587` | STARTTLS port |
| `NOTIFICATION_SMTP_USER` | `""` | SMTP login |
| `NOTIFICATION_SMTP_PASSWORD` | `""` | App password (never logged or returned) |
| `NOTIFICATION_NTFY_TOPIC` | `""` | ntfy.sh topic slug |

---

## OWASP Review

| ID | Control | Implementation |
|----|---------|----------------|
| A01 | Admin filter hard-codes `owner_role=="admin"` before deletion; guest filter hard-codes `owner_role=="guest"` | `_admin_filter`, `_guest_session_filter` in `cleanup.py` |
| A03 | Cadence value from Pydantic enum; custom value range 1–8760 validated; bleach on notification strings | `SettingsUpdateRequest` validators |
| A04 | `@limiter.limit("2/minute")` on cleanup endpoint | `documents.py` |
| A07 | Cleanup + notification endpoints require `require_full_access` | FastAPI dependency |
| A09 | `audit_event("document_cleanup", ...)` with count/trigger/scope; SMTP password excluded from all log calls | `cleanup.py`, `notifications.py` |

---

## Implementation Strategy

### MVP (Phases 1–4 — 18 tasks)

Delivers guest auto-cleanup + admin manual cleanup with full cadence configuration. US3 (force mode) and US4 (notifications) are independently testable increments that can follow in a subsequent session.

### Deferred (Post-MVP)

- Scheduled admin cleanup (requires persistent background process — not viable on Vercel)
- International notification channels (Slack, Teams) — out of scope
- Cleanup result persistence across Vercel instances (would require Vercel Blob or KV)
