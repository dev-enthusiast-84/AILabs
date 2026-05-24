# Research: Document Cleanup

**Phase 0 output for plan.md** | Date: 2026-05-24

---

## 1. Existing Cleanup Infrastructure

### Finding
The codebase already has partial cleanup wiring:
- `backend/app/api/documents.py` — `_cleanup_document_storage(filename)` deletes a single document from vector store + file store + chunk manifest; `_delete_stale_document()` calls it for stale index entries.
- `backend/app/api/documents.py` — `_list_visible_document_names()` already calls `_delete_stale_document()` for stale guest docs during a list operation.
- `backend/app/config.py` — `guest_doc_retention_seconds: int = 3600` and `admin_doc_retention_days: int = 30` exist.
- `backend/app/runtime/settings_store.py` — `get_effective_admin_doc_retention_days()` and `_runtime_admin_doc_retention_days` exist; `apply_runtime_settings()` already accepts `admin_doc_retention_days`.
- `backend/app/api/settings.py` — `SettingsUpdateRequest` already has `admin_doc_retention_days: int | None`.

### Decision
Extend the existing patterns rather than building a new scheduler:
1. Guest cleanup → extend `GET /api/documents/` (already does stale removal; extend for full previous-session sweep).
2. Admin manual cleanup → new `POST /api/documents/cleanup` endpoint using `BackgroundTasks`.

**Rationale**: Vercel serverless has no persistent runtime between requests. Request-time cleanup fits the architecture.

---

## 2. Ownership Metadata

### Finding
Every uploaded document chunk has metadata:
```python
{
  "source": source_key,
  "filename": filename,
  "owner_role": "guest" | "admin",
  "owner_username": str,
  "owner_session": str,       # "" for admin
  "uploaded_at": str,         # Unix timestamp as string
}
```
Written in `_document_metadata()` at upload time, indexed in both ChromaDB and Pinecone.

### Decision
Use `owner_role`, `owner_session`, and `uploaded_at` as the sole filter keys. No schema changes needed.

---

## 3. Isolation Strategy

### Decision
Admin filter: `owner_role == "admin"` AND `int(uploaded_at) < cutoff_ts`
Guest filter: `owner_role == "guest"` AND `owner_session != current_session`

These are disjoint by `owner_role` — structurally impossible to cross-delete. Implemented in a single `_select_documents_for_cleanup(filter_fn)` function that calls `get_all_documents()` once and de-dupes by `source`.

---

## 4. Cadence Design

### Decision
Replace `admin_doc_retention_days` (scalar integer) with a named cadence preset:

| Preset | Retention |
|--------|-----------|
| `hourly` | 1 h |
| `daily` | 24 h |
| `weekly` | 168 h |
| `biweekly` | 336 h |
| `monthly` (default) | 720 h |
| `custom` | `value × (1 if hours else 24)` |

`get_effective_cleanup_retention_hours()` in `settings_store.py` resolves at runtime. **Force mode** sets `cutoff_ts = now()` regardless of cadence.

**Rationale**: Preset names are more intuitive in a UI dropdown than a bare integer.

---

## 5. Force Mode

### Decision
`POST /api/documents/cleanup` accepts `{"force": true}`. When force=true, `cutoff_ts = now()` so all admin docs are eligible regardless of age. Result includes `force_mode=True` and `retention_hours=None` so the UI can show a distinct badge.

**Trigger**: When `admin_docs_near_limit` is true, the frontend sends `force=true` automatically.

---

## 6. Concurrency Safety

### Decision
Accept best-effort cleanup (same pattern as existing `_cleanup_document_storage`). Use `BackgroundTasks` so HTTP response returns before cleanup starts. No server-level lock — breaks on Vercel multi-instance. The race is low-probability and self-healing.

---

## 7. Result Persistence

### Decision
Module-level `_last_cleanup_result: CleanupResult | None = None` in `cleanup.py`. Expose via `GET /api/documents/cleanup/status`. Simple, zero-dep, works within a single Vercel function instance's lifetime.

---

## 8. Upload-Limit Warning

### Decision
`ADMIN_MAX_INDEXED_DOCUMENTS` env (default 100). `admin_doc_count` computed by counting unique `source` values with `owner_role=="admin"` from `get_all_documents()`, cached in the existing LRU. `admin_docs_near_limit = count >= limit * 0.8`. Exposed in `GET /api/settings` and `GET /api/documents/metadata`.

---

## 9. Zero-Cost Notifications

### Decision
| Channel | Technology | New dependency |
|---------|-----------|----------------|
| Email | Python stdlib `smtplib` + STARTTLS | None |
| Push | ntfy.sh via `httpx.AsyncClient.post()` | None (httpx already in requirements) |

- Off by default (`NOTIFICATION_ENABLED=false`).
- Deduplication: module-level `_last_notified_at` timestamp; fires at most once per 24 h.
- SMTP password stored in env only; never logged.
- ntfy topic is a shared secret; admin should use a long random slug.

**Alternatives rejected**: Twilio (paid), Resend (requires API key signup), smtplib over sendmail binary (not available on Vercel).

---

## 10. OWASP Review

| Risk | Control |
|------|---------|
| A01 — Admin deletes guest docs | Admin filter enforces `owner_role == "admin"` before any deletion |
| A01 — Guest deletes admin docs | Cleanup endpoint requires `require_full_access` (admin JWT) |
| A04 — DoS via repeated cleanup triggers | Rate limit: `@limiter.limit("2/minute")` |
| A09 — Logging sensitive data | `audit_event` logs count/trigger/scope only; no document content or credentials |
