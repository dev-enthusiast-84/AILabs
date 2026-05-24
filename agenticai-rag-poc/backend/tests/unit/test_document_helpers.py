"""Unit tests for app.api.documents helper functions.

Covers the missing lines identified in the coverage report:
  51-52, 57-59, 75, 104-125, 137, 156-157, 159, 176, 215-217, 223-225, 230-231
"""
import pytest
from unittest.mock import MagicMock, call, patch
from langchain_core.documents import Document

from app.auth.models import UserInDB


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_user(role: str = "admin", session_id: str | None = None) -> UserInDB:
    return UserInDB(
        username="admin" if role == "admin" else "guest",
        hashed_password="hashed",
        role=role,
        session_id=session_id,
    )


def _raises(exc_type=RuntimeError, msg: str = "error"):
    """Return a callable that always raises *exc_type(msg)*."""
    def _f(*args, **kwargs):
        raise exc_type(msg)
    return _f


# ── _cleanup_document_storage ─────────────────────────────────────────────────


class TestCleanupDocumentStorage:
    def test_calls_all_three_cleanup_functions(self, monkeypatch):
        """All three storage delete functions are attempted."""
        from app.api.documents import _cleanup_document_storage

        mock_dd = MagicMock()
        mock_df = MagicMock()
        mock_dcm = MagicMock()
        monkeypatch.setattr("app.api.documents.delete_document", mock_dd)
        monkeypatch.setattr("app.api.documents.delete_file", mock_df)
        monkeypatch.setattr("app.api.documents.delete_chunk_manifest", mock_dcm)

        _cleanup_document_storage("test.txt")

        mock_dd.assert_called_once_with("test.txt")
        mock_df.assert_called_once_with("test.txt")
        mock_dcm.assert_called_once_with("test.txt")

    def test_continues_after_first_cleanup_raises(self, monkeypatch):
        """Lines 51-52: exception in one cleanup does not abort the others."""
        from app.api.documents import _cleanup_document_storage

        mock_df = MagicMock()
        mock_dcm = MagicMock()
        monkeypatch.setattr("app.api.documents.delete_document", _raises())
        monkeypatch.setattr("app.api.documents.delete_file", mock_df)
        monkeypatch.setattr("app.api.documents.delete_chunk_manifest", mock_dcm)

        # Must not raise
        _cleanup_document_storage("test.txt")

        mock_df.assert_called_once_with("test.txt")
        mock_dcm.assert_called_once_with("test.txt")

    def test_continues_when_all_three_raise(self, monkeypatch):
        """Exception handling applies to every cleanup call."""
        from app.api.documents import _cleanup_document_storage

        monkeypatch.setattr("app.api.documents.delete_document", _raises())
        monkeypatch.setattr("app.api.documents.delete_file", _raises(ValueError))
        monkeypatch.setattr("app.api.documents.delete_chunk_manifest", _raises(OSError))

        # Must not raise despite all three failing
        _cleanup_document_storage("test.txt")


# ── _delete_stale_document ────────────────────────────────────────────────────


class TestDeleteStaleDocument:
    def test_calls_cleanup_and_invalidates_cache(self, monkeypatch):
        """Lines 57-59: cleanup + cache invalidation + log.info are called."""
        from app.api.documents import _delete_stale_document

        mock_cleanup = MagicMock()
        mock_invalidate = MagicMock()
        monkeypatch.setattr("app.api.documents._cleanup_document_storage", mock_cleanup)
        monkeypatch.setattr("app.api.documents.invalidate_doc_cache", mock_invalidate)

        _delete_stale_document("stale.txt")

        mock_cleanup.assert_called_once_with("stale.txt")
        mock_invalidate.assert_called_once()


# ── _guest_display_filename ───────────────────────────────────────────────────


class TestGuestDisplayFilename:
    def test_returns_source_when_session_not_in_metadata(self, monkeypatch):
        from app.api.documents import _guest_display_filename

        result = _guest_display_filename("my.txt", {})
        assert result == "my.txt"

    def test_strips_guest_prefix_when_present(self, monkeypatch):
        from app.api.documents import _guest_display_filename

        result = _guest_display_filename("guest-sess1-my.txt", {"owner_session": "sess1"})
        assert result == "my.txt"

    def test_returns_source_when_prefix_not_present(self, monkeypatch):
        from app.api.documents import _guest_display_filename

        result = _guest_display_filename("other.txt", {"owner_session": "sess1"})
        assert result == "other.txt"

    def test_line_75_returns_source_when_stripped_name_is_empty(self, monkeypatch):
        """Line 75: source[len(prefix):] is '' → falls back to source itself."""
        from app.api.documents import _guest_display_filename

        # source == prefix exactly → stripping leaves empty string → return source
        session = "abc"
        source = f"guest-{session}-"
        result = _guest_display_filename(source, {"owner_session": session})
        # The or-branch returns source when the stripped part is falsy
        assert result == source

    def test_returns_source_when_session_is_non_string(self, monkeypatch):
        from app.api.documents import _guest_display_filename

        result = _guest_display_filename("file.txt", {"owner_session": 123})
        assert result == "file.txt"


# ── _document_availability ────────────────────────────────────────────────────


class TestDocumentAvailability:
    def test_returns_unknown_when_get_document_chunks_raises(self, monkeypatch):
        """Lines 107-108: get_document_chunks exception → 'unknown'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", _raises())

        result = _document_availability("broken.txt")
        assert result == "unknown"

    def test_returns_stale_when_no_vector_chunks(self, monkeypatch):
        """Empty vector chunks → 'stale'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: [])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: None)
        monkeypatch.setattr("app.api.documents.read_file", lambda src: None)

        result = _document_availability("stale.txt")
        assert result == "stale"

    def test_returns_usable_when_manifest_present(self, monkeypatch):
        """Manifest exists → 'usable'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: ["chunk"])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: ["chunk1"])

        result = _document_availability("ok.txt")
        assert result == "usable"

    def test_returns_usable_when_file_present(self, monkeypatch):
        """No manifest but file exists → 'usable'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: ["chunk"])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: None)
        monkeypatch.setattr("app.api.documents.read_file", lambda src: b"data")

        result = _document_availability("ok.txt")
        assert result == "usable"

    def test_returns_unknown_when_manifest_raises(self, monkeypatch):
        """Lines 116-118: read_chunk_manifest exception → storage_error=True → 'unknown'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: ["chunk"])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", _raises())
        monkeypatch.setattr("app.api.documents.read_file", _raises())

        result = _document_availability("broken.txt")
        assert result == "unknown"

    def test_returns_unknown_when_read_file_raises(self, monkeypatch):
        """Lines 120-124: read_file exception after manifest returns None → 'unknown'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: ["chunk"])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: None)
        monkeypatch.setattr("app.api.documents.read_file", _raises())

        result = _document_availability("broken.txt")
        assert result == "unknown"

    def test_line_125_returns_stale_when_no_storage_error_and_no_data(self, monkeypatch):
        """Line 125: no storage_error and neither file nor manifest → 'stale'."""
        from app.api.documents import _document_availability

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: ["chunk"])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: None)
        monkeypatch.setattr("app.api.documents.read_file", lambda src: None)

        result = _document_availability("stale.txt")
        assert result == "stale"


# ── _candidate_is_upload_duplicate ────────────────────────────────────────────


class TestCandidateIsUploadDuplicate:
    def test_returns_false_when_document_does_not_exist(self, monkeypatch):
        from app.api.documents import _candidate_is_upload_duplicate

        monkeypatch.setattr("app.api.documents.document_exists", lambda src: False)

        assert _candidate_is_upload_duplicate("new.txt") is False

    def test_returns_true_when_document_is_usable(self, monkeypatch):
        from app.api.documents import _candidate_is_upload_duplicate

        monkeypatch.setattr("app.api.documents.document_exists", lambda src: True)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "usable")

        assert _candidate_is_upload_duplicate("existing.txt") is True

    def test_deletes_stale_and_returns_false(self, monkeypatch):
        from app.api.documents import _candidate_is_upload_duplicate

        mock_delete = MagicMock()
        monkeypatch.setattr("app.api.documents.document_exists", lambda src: True)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "stale")
        monkeypatch.setattr("app.api.documents._delete_stale_document", mock_delete)

        result = _candidate_is_upload_duplicate("stale.txt")

        assert result is False
        mock_delete.assert_called_once_with("stale.txt")

    def test_line_137_raises_safe_app_error_when_availability_unknown(self, monkeypatch):
        """Line 137: availability=='unknown' → raises SafeAppError(503)."""
        from app.api.documents import _candidate_is_upload_duplicate
        from app.core.errors import SafeAppError

        monkeypatch.setattr("app.api.documents.document_exists", lambda src: True)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "unknown")

        with pytest.raises(SafeAppError) as exc_info:
            _candidate_is_upload_duplicate("unavailable.txt")

        assert exc_info.value.status_code == 503
        assert exc_info.value.category == "retrieval_error"


# ── _list_visible_document_names ──────────────────────────────────────────────


class TestListVisibleDocumentNames:
    def test_guest_stale_doc_is_deleted_and_excluded(self, monkeypatch):
        """Lines 156-157: guest stale doc triggers _delete_stale_document and is skipped."""
        from app.api.documents import _list_visible_document_names

        session = "sess-1"
        user = _make_user(role="guest", session_id=session)
        docs = [
            Document(
                page_content="x",
                metadata={
                    "source": f"guest-{session}-stale.txt",
                    "owner_role": "guest",
                    "owner_session": session,
                },
            )
        ]
        mock_delete = MagicMock()
        monkeypatch.setattr("app.api.documents.get_all_documents", lambda: docs)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "stale")
        monkeypatch.setattr("app.api.documents._delete_stale_document", mock_delete)

        result = _list_visible_document_names(user)

        assert result == []
        mock_delete.assert_called_once_with(f"guest-{session}-stale.txt")

    def test_guest_doc_with_unknown_availability_is_skipped(self, monkeypatch):
        """Line 159: guest doc with availability=='unknown' is excluded from results."""
        from app.api.documents import _list_visible_document_names

        session = "sess-2"
        user = _make_user(role="guest", session_id=session)
        docs = [
            Document(
                page_content="x",
                metadata={
                    "source": f"guest-{session}-broken.txt",
                    "filename": "broken.txt",
                    "owner_role": "guest",
                    "owner_session": session,
                },
            )
        ]
        monkeypatch.setattr("app.api.documents.get_all_documents", lambda: docs)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "unknown")

        result = _list_visible_document_names(user)
        assert result == []

    def test_admin_doc_with_unknown_availability_is_skipped(self, monkeypatch):
        """Line 176: admin doc with availability=='unknown' is excluded from results."""
        from app.api.documents import _list_visible_document_names

        user = _make_user(role="admin")
        docs = [
            Document(
                page_content="x",
                metadata={
                    "source": "broken.txt",
                    "filename": "broken.txt",
                    "owner_role": "admin",
                },
            )
        ]
        monkeypatch.setattr("app.api.documents.get_all_documents", lambda: docs)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "unknown")

        result = _list_visible_document_names(user)
        assert result == []

    def test_admin_usable_docs_are_returned(self, monkeypatch):
        """Admin usable documents are included in the list."""
        from app.api.documents import _list_visible_document_names

        user = _make_user(role="admin")
        docs = [
            Document(
                page_content="x",
                metadata={
                    "source": "good.txt",
                    "filename": "good.txt",
                    "owner_role": "admin",
                },
            )
        ]
        monkeypatch.setattr("app.api.documents.get_all_documents", lambda: docs)
        monkeypatch.setattr("app.api.documents._document_availability", lambda src: "usable")

        result = _list_visible_document_names(user)
        assert result == ["good.txt"]


# ── _load_document_chunks_for_display ─────────────────────────────────────────


class TestLoadDocumentChunksForDisplay:
    def test_returns_empty_list_when_get_document_chunks_raises(self, monkeypatch):
        """Lines 215-217: get_document_chunks exception → chunks=[] and continues."""
        from app.api.documents import _load_document_chunks_for_display

        monkeypatch.setattr("app.api.documents.get_document_chunks", _raises())
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: ["chunk-from-manifest"])

        result = _load_document_chunks_for_display("test.txt")
        # Falls through to manifest and returns those chunks
        assert result == ["chunk-from-manifest"]

    def test_returns_empty_list_when_manifest_raises(self, monkeypatch):
        """Lines 223-225: _build_chunk_manifest_from_original_file raises → return []."""
        from app.api.documents import _load_document_chunks_for_display

        monkeypatch.setattr("app.api.documents.get_document_chunks", _raises())
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", _raises())

        def _bad_build(fn):
            raise RuntimeError("build failed")

        monkeypatch.setattr(
            "app.api.documents._build_chunk_manifest_from_original_file", _bad_build
        )

        result = _load_document_chunks_for_display("test.txt")
        assert result == []

    def test_returns_chunks_even_when_save_chunk_manifest_raises(self, monkeypatch):
        """Lines 230-231: save_chunk_manifest raises but chunks still returned."""
        from app.api.documents import _load_document_chunks_for_display

        monkeypatch.setattr("app.api.documents.get_document_chunks", _raises())
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: [])
        monkeypatch.setattr(
            "app.api.documents._build_chunk_manifest_from_original_file",
            lambda fn: ["rebuilt-chunk"],
        )
        monkeypatch.setattr("app.api.documents.save_chunk_manifest", _raises())

        result = _load_document_chunks_for_display("test.txt")
        assert result == ["rebuilt-chunk"]

    def test_returns_chunks_from_vector_store_when_available(self, monkeypatch):
        """Happy path: vector store has chunks, returns them directly."""
        from app.api.documents import _load_document_chunks_for_display

        monkeypatch.setattr(
            "app.api.documents.get_document_chunks", lambda src: ["vec-chunk"]
        )

        result = _load_document_chunks_for_display("test.txt")
        assert result == ["vec-chunk"]

    def test_returns_empty_list_when_all_sources_empty(self, monkeypatch):
        """All three sources return empty → final result is []."""
        from app.api.documents import _load_document_chunks_for_display

        monkeypatch.setattr("app.api.documents.get_document_chunks", lambda src: [])
        monkeypatch.setattr("app.api.documents.read_chunk_manifest", lambda src: [])
        monkeypatch.setattr(
            "app.api.documents._build_chunk_manifest_from_original_file",
            lambda fn: [],
        )

        result = _load_document_chunks_for_display("test.txt")
        assert result == []


# ── _check_content_safety ─────────────────────────────────────────────────────


class TestCheckContentSafety:
    def test_rejects_null_bytes_in_txt(self):
        """Line 302: TXT file with null bytes raises ValueError."""
        from app.api.documents import _check_content_safety

        content = b"valid start\x00rest of file"
        with pytest.raises(ValueError, match="Binary content"):
            _check_content_safety("upload.txt", content)

    def test_rejects_null_bytes_in_csv(self):
        """Null bytes in CSV are also rejected (same branch as TXT)."""
        from app.api.documents import _check_content_safety

        content = b"col1,col2\x00val1,val2"
        with pytest.raises(ValueError, match="Binary content"):
            _check_content_safety("data.csv", content)

    def test_accepts_clean_txt(self):
        """Clean TXT file passes safety check without error."""
        from app.api.documents import _check_content_safety

        _check_content_safety("clean.txt", b"Normal document text content.")

    def test_rejects_mz_executable_header(self):
        """Line 296: content starting with MZ bytes raises ValueError."""
        from app.api.documents import _check_content_safety

        content = b"\x4d\x5a" + b"\x00" * 100  # Windows PE header
        with pytest.raises(ValueError, match="Executable content"):
            _check_content_safety("disguised.txt", content)

    def test_rejects_elf_executable_header(self):
        """Line 296: content starting with ELF magic raises ValueError."""
        from app.api.documents import _check_content_safety

        content = b"\x7f\x45\x4c\x46" + b"\x00" * 100  # ELF header
        with pytest.raises(ValueError, match="Executable content"):
            _check_content_safety("binary.txt", content)


# ── _guest_upload_key revoked-token path ──────────────────────────────────────


class TestGuestUploadKey:
    def test_revoked_token_falls_through_to_ip_key(self, monkeypatch):
        """Lines 255, 258-259: revoked JTI raises ValueError caught by bare except → IP key used."""
        from app.api.documents import _guest_upload_key
        from unittest.mock import MagicMock

        # Build a fake request with a Bearer token header
        fake_request = MagicMock()
        fake_request.headers.get.return_value = "Bearer fake.jwt.token"

        # Patch jose.jwt.decode to return payload with a JTI
        mock_payload = {"jti": "revoked-jti", "role": "guest"}

        import app.api.documents as doc_module

        original_jose = None
        try:
            from jose import jwt as real_jwt
            original_decode = real_jwt.decode
        except ImportError:
            original_decode = None

        # Patch is_token_revoked to return True (simulates revoked JTI)
        monkeypatch.setattr("app.api.documents.is_token_revoked", lambda jti: True)

        # Patch jose.jwt inside the module scope by patching the import path
        class FakeJwt:
            @staticmethod
            def decode(token, key, algorithms, **kwargs):
                return mock_payload

        import jose
        monkeypatch.setattr(jose, "jwt", FakeJwt)

        # get_remote_address should be the fallback
        monkeypatch.setattr(
            "app.api.documents.get_remote_address", lambda req: "127.0.0.1"
        )

        result = _guest_upload_key(fake_request)
        # Revoked token → ValueError raised → caught by bare except → falls back to IP
        assert result == "127.0.0.1"

    def test_invalid_bearer_token_falls_back_to_ip(self, monkeypatch):
        """Lines 258-259: malformed JWT raises JWTError caught by bare except → IP key returned."""
        from app.api.documents import _guest_upload_key
        from unittest.mock import MagicMock

        fake_request = MagicMock()
        fake_request.headers.get.return_value = "Bearer not.a.valid.jwt"

        monkeypatch.setattr(
            "app.api.documents.get_remote_address", lambda req: "10.0.0.1"
        )

        result = _guest_upload_key(fake_request)
        # Invalid JWT → JoseError caught → fallback to IP
        assert result == "10.0.0.1"


# ── get_document_suggestions ──────────────────────────────────────────────────


class TestGetDocumentSuggestions:
    """Unit tests for the /documents/suggestions endpoint helper logic."""

    def _make_admin(self) -> "UserInDB":
        return _make_user(role="admin")

    def _make_request(self):
        from unittest.mock import MagicMock
        req = MagicMock()
        req.headers.get.return_value = None
        req.cookies.get.return_value = None
        return req

    async def test_returns_empty_when_no_files(self, monkeypatch):
        """Empty files list → empty suggestions immediately."""
        from app.api.documents import get_document_suggestions

        result = await get_document_suggestions(request=self._make_request(), files=[], _user=self._make_admin())
        assert result.suggestions == []

    async def test_returns_empty_when_chunks_not_found(self, monkeypatch):
        """Files with no indexed chunks → empty suggestions."""
        from app.api.documents import get_document_suggestions

        monkeypatch.setattr("app.api.documents._document_source_key", lambda name, user: name)
        monkeypatch.setattr("app.api.documents._load_document_chunks_for_display", lambda _: [])

        result = await get_document_suggestions(request=self._make_request(), files=["missing.txt"], _user=self._make_admin())
        assert result.suggestions == []

    async def test_returns_empty_when_api_key_not_configured(self, monkeypatch):
        """No API key → skips LLM call and returns empty list.

        get_document_suggestions does a local `from app.runtime.settings_store import
        get_effective_api_key` inside the function body, so the patch must target the
        source module — not the module-level binding in app.api.documents — otherwise
        CI environments with OPENAI_API_KEY set will bypass the guard and make a real
        LLM call, causing the assertion to fail.
        """
        from app.api.documents import get_document_suggestions

        monkeypatch.setattr("app.api.documents._document_source_key", lambda name, user: name)
        monkeypatch.setattr(
            "app.api.documents._load_document_chunks_for_display",
            lambda _: ["This document describes RAG pipeline stages."],
        )
        monkeypatch.setattr("app.runtime.settings_store.get_effective_api_key", lambda: "")

        result = await get_document_suggestions(request=self._make_request(), files=["doc.txt"], _user=self._make_admin())
        assert result.suggestions == []

    async def test_returns_llm_questions_when_configured(self, monkeypatch):
        """LLM returns valid JSON array → questions surfaced as suggestions."""
        import json
        from unittest.mock import MagicMock
        from app.api.documents import get_document_suggestions

        monkeypatch.setattr("app.api.documents._document_source_key", lambda name, user: name)
        monkeypatch.setattr(
            "app.api.documents._load_document_chunks_for_display",
            lambda _: ["Retrieval-Augmented Generation (RAG) combines retrieval with generation."],
        )

        expected = [
            "What is Retrieval-Augmented Generation?",
            "How does RAG combine retrieval with generation?",
            "What problem does RAG solve?",
            "What are the stages of a RAG pipeline?",
        ]

        fake_llm = MagicMock()
        fake_llm.invoke.return_value = MagicMock(content=json.dumps(expected))
        fake_chat_class = MagicMock(return_value=fake_llm)

        monkeypatch.setattr("app.api.documents.get_effective_api_key", lambda: "sk-test", raising=False)

        import sys
        fake_module = MagicMock()
        fake_module.ChatOpenAI = fake_chat_class
        monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

        result = await get_document_suggestions(request=self._make_request(), files=["doc.txt"], _user=self._make_admin())
        assert result.suggestions == expected

    async def test_multi_doc_uses_per_doc_prompt(self, monkeypatch):
        """Multiple files → one question per doc, using the per-doc structured prompt."""
        import json
        from unittest.mock import MagicMock
        from app.api.documents import get_document_suggestions

        chunks_by_name = {
            "hr.txt": ["HR policy content about leave."],
            "it.csv": ["IT security controls CSV content."],
            "training.xlsx": ["Training catalog XLSX content."],
        }
        monkeypatch.setattr("app.api.documents._document_source_key", lambda name, user: name)
        monkeypatch.setattr(
            "app.api.documents._load_document_chunks_for_display",
            lambda name: chunks_by_name.get(name, []),
        )

        per_doc_questions = [
            "What is the annual leave entitlement?",
            "What MFA methods are required?",
            "Which course awards the AI Practitioner Certificate?",
        ]

        prompts_seen: list[str] = []
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = lambda msgs: (
            prompts_seen.append(msgs[0].content) or MagicMock(content=json.dumps(per_doc_questions))
        )
        fake_chat_class = MagicMock(return_value=fake_llm)

        monkeypatch.setattr("app.api.documents.get_effective_api_key", lambda: "sk-test", raising=False)
        import sys
        fake_module = MagicMock()
        fake_module.ChatOpenAI = fake_chat_class
        monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

        result = await get_document_suggestions(
            request=self._make_request(), files=["hr.txt", "it.csv", "training.xlsx"], _user=self._make_admin()
        )
        assert result.suggestions == per_doc_questions
        # Prompt must reference multiple documents (per-doc path)
        assert len(prompts_seen) == 1
        assert "Document 1" in prompts_seen[0]
        assert "Document 2" in prompts_seen[0]
        assert "Document 3" in prompts_seen[0]

    async def test_returns_empty_on_llm_json_parse_error(self, monkeypatch):
        """Malformed LLM response → empty list, no exception raised."""
        from unittest.mock import MagicMock
        from app.api.documents import get_document_suggestions

        monkeypatch.setattr("app.api.documents._document_source_key", lambda name, user: name)
        monkeypatch.setattr(
            "app.api.documents._load_document_chunks_for_display",
            lambda _: ["Some document content here."],
        )

        fake_llm = MagicMock()
        fake_llm.invoke.return_value = MagicMock(content="not valid json at all")
        fake_chat_class = MagicMock(return_value=fake_llm)

        monkeypatch.setattr("app.api.documents.get_effective_api_key", lambda: "sk-test", raising=False)

        import sys
        fake_module = MagicMock()
        fake_module.ChatOpenAI = fake_chat_class
        monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

        result = await get_document_suggestions(request=self._make_request(), files=["doc.txt"], _user=self._make_admin())
        assert result.suggestions == []
