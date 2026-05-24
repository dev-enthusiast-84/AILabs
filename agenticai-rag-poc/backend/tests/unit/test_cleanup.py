"""Unit tests for app.rag.cleanup module.

Covers:
- T006: _guest_session_filter predicate
- T007: CleanupService.sweep_guest
- T011: CleanupService.sweep_admin (cadence, weekly, force)
- T019: Force mode vs. normal mode with recent docs
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from app.rag.cleanup import (
    CADENCE_HOURS,
    CleanupResult,
    CleanupService,
    _admin_filter,
    _admin_force_filter,
    _guest_session_filter,
    _safe_uploaded_at,
    _select_documents_for_cleanup,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_doc(role: str, session: str = "", source: str = "", uploaded_at: int | None = None) -> MagicMock:
    """Build a minimal MagicMock document with .metadata dict."""
    d = MagicMock()
    d.metadata = {
        "owner_role": role,
        "owner_session": session,
        "source": source or f"src-{role}-{session}",
        "uploaded_at": str(uploaded_at if uploaded_at is not None else int(time.time())),
    }
    return d


# ── CADENCE_HOURS contract ─────────────────────────────────────────────────────

def test_cadence_hours_keys():
    assert set(CADENCE_HOURS.keys()) == {"hourly", "daily", "weekly", "biweekly", "monthly"}


def test_cadence_hours_values():
    assert CADENCE_HOURS["hourly"] == 1
    assert CADENCE_HOURS["daily"] == 24
    assert CADENCE_HOURS["weekly"] == 168
    assert CADENCE_HOURS["biweekly"] == 336
    assert CADENCE_HOURS["monthly"] == 720


# ── _guest_session_filter (T006) ───────────────────────────────────────────────

class TestGuestSessionFilter:
    """_guest_session_filter returns True only for stale guest docs from other sessions."""

    def test_includes_other_session_guest_docs(self):
        meta = {"owner_role": "guest", "owner_session": "session-A"}
        assert _guest_session_filter(meta, "session-B") is True

    def test_excludes_current_session_docs(self):
        meta = {"owner_role": "guest", "owner_session": "session-A"}
        assert _guest_session_filter(meta, "session-A") is False

    def test_excludes_admin_docs(self):
        meta = {"owner_role": "admin", "owner_session": ""}
        assert _guest_session_filter(meta, "session-B") is False

    def test_excludes_docs_with_empty_session(self):
        meta = {"owner_role": "guest", "owner_session": ""}
        assert _guest_session_filter(meta, "session-B") is False

    def test_excludes_docs_without_session_key(self):
        meta = {"owner_role": "guest"}
        assert _guest_session_filter(meta, "session-B") is False

    def test_excludes_docs_with_no_role(self):
        meta = {"owner_session": "session-A"}
        assert _guest_session_filter(meta, "session-B") is False

    def test_different_non_empty_sessions_included(self):
        meta = {"owner_role": "guest", "owner_session": "old-abc"}
        assert _guest_session_filter(meta, "new-xyz") is True


# ── CleanupService.sweep_guest (T007) ─────────────────────────────────────────

class TestSweepGuest:
    """sweep_guest should delete docs from previous guest sessions only."""

    def _make_docs(self):
        admin_doc = _make_doc("admin", source="admin-doc.txt")
        current_guest = _make_doc("guest", session="session-NOW", source="current.txt")
        old_guest_1 = _make_doc("guest", session="session-OLD", source="old1.txt")
        old_guest_2 = _make_doc("guest", session="session-OLDER", source="old2.txt")
        return [admin_doc, current_guest, old_guest_1, old_guest_2]

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_sweeps_previous_session_docs(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        mock_get.return_value = self._make_docs()

        result = CleanupService().sweep_guest("session-NOW")

        assert result.trigger == "session_start"
        assert result.scope == "guest"
        assert result.force_mode is False
        assert result.deleted_count == 2
        assert result.cadence is None
        assert result.retention_hours is None
        assert set(result.deleted_sources) == {"old1.txt", "old2.txt"}
        # delete_document called once per stale source
        assert mock_del_doc.call_count == 2

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_admin_docs_untouched(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        admin_doc = _make_doc("admin", source="admin.txt")
        mock_get.return_value = [admin_doc]

        result = CleanupService().sweep_guest("session-X")
        assert result.deleted_count == 0
        mock_del_doc.assert_not_called()

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_updates_last_cleanup_result(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        import app.rag.cleanup as cleanup_mod
        mock_get.return_value = []

        result = CleanupService().sweep_guest("some-session")
        assert cleanup_mod._last_cleanup_result is result

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_empty_doc_list_returns_zero_result(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        mock_get.return_value = []

        result = CleanupService().sweep_guest("session-X")
        assert result.deleted_count == 0
        assert result.eligible_count == 0
        assert result.deleted_sources == []
        mock_del_doc.assert_not_called()

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_current_session_doc_not_deleted(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        current = _make_doc("guest", session="my-session", source="mine.txt")
        mock_get.return_value = [current]

        result = CleanupService().sweep_guest("my-session")
        assert result.deleted_count == 0
        mock_del_doc.assert_not_called()


# ── CleanupService.sweep_admin (T011) ─────────────────────────────────────────

def _admin_docs_at_ages(ages_hours: list[int]) -> list[MagicMock]:
    """Build admin docs with uploaded_at set to (now - age_hours * 3600)."""
    now = int(time.time())
    docs = []
    for i, age in enumerate(ages_hours):
        docs.append(_make_doc("admin", source=f"doc-{i}.txt", uploaded_at=now - age * 3600))
    return docs


class TestSweepAdmin:
    """sweep_admin should respect cadence retention and force flag."""

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    @patch("app.runtime.settings_store.get_effective_cleanup_retention_hours", return_value=720)
    def test_monthly_cadence_deletes_only_stale_docs(
        self, mock_retention, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        # ages: 10h (recent), 200h (recent), 800h (stale > 720h)
        mock_get.return_value = _admin_docs_at_ages([10, 200, 800])

        result = CleanupService().sweep_admin(force=False)
        assert result.deleted_count == 1
        assert result.force_mode is False

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    @patch("app.runtime.settings_store.get_effective_cleanup_retention_hours", return_value=168)
    def test_weekly_cadence_deletes_multiple(
        self, mock_retention, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        # ages: 10h (recent), 200h (stale > 168h), 800h (stale > 168h)
        mock_get.return_value = _admin_docs_at_ages([10, 200, 800])

        result = CleanupService().sweep_admin(force=False)
        assert result.deleted_count == 2

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    @patch("app.runtime.settings_store.get_effective_cleanup_retention_hours", return_value=336)
    def test_biweekly_custom_cadence_correct_boundary(
        self, mock_retention, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        # Custom 14 days = 336h: only the 800h doc crosses the threshold
        mock_get.return_value = _admin_docs_at_ages([10, 200, 800])

        result = CleanupService().sweep_admin(force=False)
        assert result.deleted_count == 1

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_force_mode_deletes_all_admin_docs(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        # All very recent — force=True must still delete them all
        mock_get.return_value = _admin_docs_at_ages([1, 2, 3])

        result = CleanupService().sweep_admin(force=True)
        assert result.deleted_count == 3
        assert result.force_mode is True
        assert result.retention_hours is None

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    @patch("app.runtime.settings_store.get_effective_cleanup_retention_hours", return_value=720)
    def test_guest_docs_never_deleted_by_admin_sweep(
        self, mock_retention, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        now = int(time.time())
        guest_doc = _make_doc("guest", session="s1", source="guest.txt",
                              uploaded_at=now - 9999 * 3600)
        mock_get.return_value = [guest_doc]

        result = CleanupService().sweep_admin(force=True)
        assert result.deleted_count == 0
        mock_del_doc.assert_not_called()

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest", side_effect=Exception("manifest error"))
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_partial_file_store_error_captured_without_aborting(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        mock_get.return_value = _admin_docs_at_ages([9999])  # definitely stale

        # force=True so no retention lookup needed
        result = CleanupService().sweep_admin(force=True)
        # Source still counted as deleted even though manifest call failed
        assert result.deleted_count == 1
        # Error captured in errors list
        assert len(result.errors) > 0

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_sweep_admin_updates_last_cleanup_result(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        import app.rag.cleanup as cleanup_mod
        mock_get.return_value = []

        result = CleanupService().sweep_admin(force=True)
        assert cleanup_mod._last_cleanup_result is result


# ── Force mode vs. normal mode (T019) ─────────────────────────────────────────

class TestForceMode:
    """Force mode should bypass retention window; normal mode should respect it."""

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    @patch("app.runtime.settings_store.get_effective_cleanup_retention_hours", return_value=720)
    def test_normal_sweep_skips_recent_docs(
        self, mock_retention, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        # All docs uploaded < 1 h ago — well under any retention threshold
        now = int(time.time())
        docs = []
        for i in range(3):
            docs.append(_make_doc("admin", source=f"r{i}.txt", uploaded_at=now - 100))
        mock_get.return_value = docs

        result = CleanupService().sweep_admin(force=False)
        assert result.deleted_count == 0
        mock_del_doc.assert_not_called()

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_force_sweep_deletes_all_admin_regardless_of_age(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        now = int(time.time())
        docs = []
        for i in range(3):
            docs.append(_make_doc("admin", source=f"r{i}.txt", uploaded_at=now - 100))
        mock_get.return_value = docs

        result = CleanupService().sweep_admin(force=True)
        assert result.deleted_count == 3
        assert result.force_mode is True
        assert result.retention_hours is None

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    def test_force_result_has_no_cadence(
        self, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        mock_get.return_value = _admin_docs_at_ages([5000])

        result = CleanupService().sweep_admin(force=True)
        assert result.cadence is None
        assert result.retention_hours is None

    @patch("app.rag.cleanup.invalidate_doc_cache")
    @patch("app.rag.cleanup.delete_chunk_manifest")
    @patch("app.rag.cleanup.delete_file")
    @patch("app.rag.cleanup.delete_document")
    @patch("app.rag.cleanup.get_all_documents")
    @patch("app.runtime.settings_store.get_effective_cleanup_retention_hours", return_value=720)
    def test_normal_result_has_retention_hours(
        self, mock_retention, mock_get, mock_del_doc, mock_del_file, mock_del_manifest, mock_invalidate
    ):
        mock_get.return_value = []

        result = CleanupService().sweep_admin(force=False)
        assert result.retention_hours == 720
        assert result.force_mode is False


# ── _safe_uploaded_at ─────────────────────────────────────────────────────────

class TestSafeUploadedAt:
    def test_valid_int_string(self):
        assert _safe_uploaded_at({"uploaded_at": "1700000000"}) == 1700000000

    def test_missing_key_returns_zero(self):
        assert _safe_uploaded_at({}) == 0

    def test_none_value_returns_zero(self):
        assert _safe_uploaded_at({"uploaded_at": None}) == 0

    def test_non_numeric_string_returns_zero(self):
        assert _safe_uploaded_at({"uploaded_at": "not-a-number"}) == 0


# ── CleanupResult schema ───────────────────────────────────────────────────────

class TestCleanupResultSchema:
    def test_valid_result_constructs_without_error(self):
        from datetime import datetime, timezone
        r = CleanupResult(
            trigger="manual",
            scope="admin",
            force_mode=False,
            deleted_count=0,
            eligible_count=0,
            cadence="monthly",
            retention_hours=720,
            deleted_sources=[],
            errors=[],
            ran_at=datetime.now(timezone.utc).isoformat(),
        )
        assert r.trigger == "manual"
        assert r.scope == "admin"

    def test_scope_guest_allowed(self):
        from datetime import datetime, timezone
        r = CleanupResult(
            trigger="session_start",
            scope="guest",
            force_mode=False,
            deleted_count=1,
            eligible_count=1,
            cadence=None,
            retention_hours=None,
            deleted_sources=["old.txt"],
            errors=[],
            ran_at=datetime.now(timezone.utc).isoformat(),
        )
        assert r.scope == "guest"
        assert r.cadence is None
