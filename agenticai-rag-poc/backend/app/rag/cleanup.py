"""
Document cleanup service — guest session pruning and admin retention sweeps.

OWASP A01 — admin and guest documents are filtered by owner_role; the predicates
are disjoint so a sweep can never cross role boundaries.
OWASP A04 — cleanup endpoints are rate-limited (2/minute); the service itself
performs best-effort deletion and captures partial errors without aborting.
OWASP A09 — only filenames and counts are logged; no document content.
"""
import time
from datetime import datetime, timezone

import structlog
from pydantic import BaseModel

from app.rag.file_store import delete_chunk_manifest, delete_file
from app.rag.vector_store import delete_document, get_all_documents, invalidate_doc_cache

log = structlog.get_logger()

CADENCE_HOURS: dict[str, int] = {
    "hourly": 1,
    "daily": 24,
    "weekly": 168,
    "biweekly": 336,
    "monthly": 720,
}


class CleanupResult(BaseModel):
    trigger: str        # "manual" | "session_start"
    scope: str          # "admin" | "guest"
    force_mode: bool
    deleted_count: int
    eligible_count: int
    cadence: str | None
    retention_hours: int | None
    deleted_sources: list[str]
    errors: list[str]
    ran_at: str


_last_cleanup_result: CleanupResult | None = None


def _admin_filter(meta: dict, cutoff_ts: int) -> bool:
    return (
        meta.get("owner_role") == "admin"
        and _safe_uploaded_at(meta) < cutoff_ts
    )


def _admin_force_filter(meta: dict) -> bool:
    return meta.get("owner_role") == "admin"


def _guest_session_filter(meta: dict, current_session: str) -> bool:
    session = meta.get("owner_session", "")
    return (
        meta.get("owner_role") == "guest"
        and isinstance(session, str)
        and session != ""
        and session != current_session
    )


def _safe_uploaded_at(meta: dict) -> int:
    try:
        return int(meta.get("uploaded_at", 0))
    except (TypeError, ValueError):
        return 0


def _select_documents_for_cleanup(filter_fn) -> list[str]:
    """Return unique source keys matching filter_fn, de-duped by source."""
    seen: set[str] = set()
    result: list[str] = []
    for doc in get_all_documents():
        meta = doc.metadata or {}
        source = meta.get("source", "")
        if not source or source in seen:
            continue
        if filter_fn(meta):
            seen.add(source)
            result.append(source)
    return result


def _delete_source(source_key: str) -> list[str]:
    """Delete all storage for one source; return list of safe error strings."""
    errors: list[str] = []
    for fn, label in [
        (delete_document, "vector_store"),
        (delete_file, "file_store"),
        (delete_chunk_manifest, "chunk_manifest"),
    ]:
        try:
            fn(source_key)
        except Exception as exc:
            msg = f"{label}: {type(exc).__name__}"
            errors.append(msg)
            log.warning("cleanup_delete_failed", source=source_key, store=label, error_type=type(exc).__name__)
    return errors


class CleanupService:
    def sweep_admin(self, force: bool = False) -> CleanupResult:
        """Delete admin documents older than the effective retention threshold (or all when force=True)."""
        global _last_cleanup_result

        from app.runtime.settings_store import (
            get_effective_cleanup_retention_hours,
            _runtime_cleanup_cadence,
        )
        from app.config import get_settings

        cfg = get_settings()

        if force:
            filter_fn = _admin_force_filter
            retention_hours: int | None = None
            cadence_label: str | None = None
        else:
            retention_hours = get_effective_cleanup_retention_hours()
            cutoff_ts = int(time.time()) - (retention_hours * 3600)
            filter_fn = lambda meta: _admin_filter(meta, cutoff_ts)
            cadence_label = _runtime_cleanup_cadence or cfg.admin_cleanup_cadence

        eligible_sources = _select_documents_for_cleanup(filter_fn)
        deleted: list[str] = []
        all_errors: list[str] = []

        for source in eligible_sources:
            errs = _delete_source(source)
            all_errors.extend(errs)
            deleted.append(source)
            invalidate_doc_cache()
            log.info("admin_cleanup_deleted", source=source, force=force)

        result = CleanupResult(
            trigger="manual",
            scope="admin",
            force_mode=force,
            deleted_count=len(deleted),
            eligible_count=len(eligible_sources),
            cadence=cadence_label if not force else None,
            retention_hours=retention_hours,
            deleted_sources=deleted,
            errors=all_errors,
            ran_at=datetime.now(timezone.utc).isoformat(),
        )
        _last_cleanup_result = result
        return result

    def sweep_guest(self, current_session: str) -> CleanupResult:
        """Delete documents uploaded by other guest sessions."""
        global _last_cleanup_result

        filter_fn = lambda meta: _guest_session_filter(meta, current_session)
        eligible_sources = _select_documents_for_cleanup(filter_fn)
        deleted: list[str] = []
        all_errors: list[str] = []

        for source in eligible_sources:
            errs = _delete_source(source)
            all_errors.extend(errs)
            deleted.append(source)
            invalidate_doc_cache()
            log.info("guest_cleanup_deleted", source=source, session=current_session)

        result = CleanupResult(
            trigger="session_start",
            scope="guest",
            force_mode=False,
            deleted_count=len(deleted),
            eligible_count=len(eligible_sources),
            cadence=None,
            retention_hours=None,
            deleted_sources=deleted,
            errors=all_errors,
            ran_at=datetime.now(timezone.utc).isoformat(),
        )
        _last_cleanup_result = result
        return result
