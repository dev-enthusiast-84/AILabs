# Data Model: Document Cleanup

**Phase 1 output for plan.md** | Date: 2026-05-24

---

## Entities

### CleanupResult

Returned by `POST /api/documents/cleanup` and cached for `GET /api/documents/cleanup/status`.

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | `"manual" \| "session_start"` | How the cleanup was initiated |
| `scope` | `"admin" \| "guest"` | Which role's documents were swept |
| `force_mode` | `bool` | True when age threshold was bypassed |
| `deleted_count` | `int` | Documents successfully removed |
| `eligible_count` | `int` | Documents that matched the filter |
| `cadence` | `str \| None` | Preset label used; `None` for guest session sweep |
| `retention_hours` | `int \| None` | Effective age threshold in hours; `None` when force_mode=true |
| `deleted_sources` | `list[str]` | Display filenames of deleted documents |
| `errors` | `list[str]` | Safe error descriptions for partial failures |
| `ran_at` | `str` | ISO-8601 UTC timestamp |

### CleanupStatusResponse

| Field | Type | Description |
|-------|------|-------------|
| `has_result` | `bool` | False if no cleanup has run since server start |
| `result` | `CleanupResult \| None` | Last cleanup result |

### SettingsResponse (additions)

| Field | Type | Description |
|-------|------|-------------|
| `admin_cleanup_cadence` | `str` | Active preset: `hourly\|daily\|weekly\|biweekly\|monthly\|custom` |
| `admin_cleanup_custom_value` | `int \| None` | Custom value (only when cadence = `"custom"`) |
| `admin_cleanup_custom_unit` | `"hours" \| "days"` | Unit for custom value |
| `admin_cleanup_retention_hours` | `int` | Effective retention age in hours (derived, read-only) |
| `admin_doc_count` | `int` | Current admin-owned document count (read-only) |
| `admin_doc_limit` | `int` | Near-limit warning threshold (read-only) |
| `admin_docs_near_limit` | `bool` | True when `admin_doc_count >= admin_doc_limit × 0.8` |
| `notification_enabled` | `bool` | Notifications master switch |
| `notification_email` | `str` | Masked recipient email (e.g. `o**@example.com`) |
| `notification_ntfy_topic` | `str` | Masked ntfy.sh topic (first 4 chars + `***`) |

### SettingsUpdateRequest (additions)

| Field | Type | Validation |
|-------|------|------------|
| `admin_cleanup_cadence` | `str \| None` | Must be in `{hourly,daily,weekly,biweekly,monthly,custom}` |
| `admin_cleanup_custom_value` | `int \| None` | 1–8760 (max 1 year in hours) |
| `admin_cleanup_custom_unit` | `str \| None` | `"hours"` or `"days"` |
| `admin_doc_limit` | `int \| None` | 1–10000 |
| `notification_enabled` | `bool \| None` | |
| `notification_email` | `str \| None` | RFC-5322 pattern; bleach-sanitised |
| `notification_ntfy_topic` | `str \| None` | Alphanumeric + hyphens; bleach-sanitised |

*(Existing `admin_doc_retention_days` retained for backward compatibility; superseded by cadence fields.)*

---

## Config Additions (`backend/app/config.py`)

| Config key | Env var | Default |
|------------|---------|---------|
| `admin_cleanup_cadence` | `ADMIN_CLEANUP_CADENCE` | `"monthly"` |
| `admin_cleanup_custom_value` | `ADMIN_CLEANUP_CUSTOM_VALUE` | `30` |
| `admin_cleanup_custom_unit` | `ADMIN_CLEANUP_CUSTOM_UNIT` | `"days"` |
| `admin_max_indexed_documents` | `ADMIN_MAX_INDEXED_DOCUMENTS` | `100` |
| `notification_enabled` | `NOTIFICATION_ENABLED` | `False` |
| `notification_email` | `NOTIFICATION_EMAIL` | `""` |
| `notification_smtp_host` | `NOTIFICATION_SMTP_HOST` | `""` |
| `notification_smtp_port` | `NOTIFICATION_SMTP_PORT` | `587` |
| `notification_smtp_user` | `NOTIFICATION_SMTP_USER` | `""` |
| `notification_smtp_password` | `NOTIFICATION_SMTP_PASSWORD` | `""` |
| `notification_ntfy_topic` | `NOTIFICATION_NTFY_TOPIC` | `""` |

---

## Cadence → Retention Hours Mapping

| Preset | `retention_hours` |
|--------|-------------------|
| `hourly` | 1 |
| `daily` | 24 |
| `weekly` | 168 |
| `biweekly` | 336 |
| `monthly` *(default)* | 720 |
| `custom` | `value × (1 if unit="hours" else 24)` |

---

## Dual-Store Delete Operation

Every cleanup touches three stores per `source_key`:

```
1. delete_document(source_key)        → vector chunks (ChromaDB or Pinecone)
2. delete_file(source_key)            → raw file (local disk or Vercel Blob)
3. delete_chunk_manifest(source_key)  → chunk manifest (local disk or Vercel Blob)
4. invalidate_doc_cache()             → clear LRU cache
```

Errors from steps 2–3 are captured in `CleanupResult.errors` and do not abort the sweep.

---

## Isolation Predicates

```python
# Admin sweep — normal mode
def _admin_filter(meta, cutoff_ts):
    return meta.get("owner_role") == "admin" and int(meta.get("uploaded_at", 0)) < cutoff_ts

# Admin sweep — force mode
def _admin_force_filter(meta):
    return meta.get("owner_role") == "admin"

# Guest sweep
def _guest_session_filter(meta, current_session):
    return meta.get("owner_role") == "guest" and meta.get("owner_session", "") != current_session
```

Disjoint by `owner_role` — admin and guest documents cannot be cross-deleted.

---

## Existing Metadata (unchanged)

All chunk metadata is written in `_document_metadata()` at `backend/app/api/documents.py:84`. No schema changes required.
