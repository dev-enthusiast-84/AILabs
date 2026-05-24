"""Unit tests for app.core.errors — SafeAppError, categorize_exception,
safe_app_error_from_exception, and safe_error_response.

Covers:
  - SafeAppError can be instantiated with all fields and exposes expected attrs.
  - SafeAppError.message falls back to _CATEGORY_MESSAGES when public_message is None.
  - SafeAppError.message uses public_message when provided.
  - safe_app_error_from_exception wraps a generic Exception as 'internal_error'.
  - safe_app_error_from_exception wraps an OpenAI-flavoured exception as
    'openai_provider_error' with 503.
  - safe_app_error_from_exception wraps an IOError as 'storage_error'.
  - categorize_exception classifies module/type name patterns correctly.
  - safe_error_response returns a JSONResponse with the expected keys.
"""
import pytest
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from unittest.mock import MagicMock

from app.core.errors import (
    SafeAppError,
    categorize_exception,
    safe_app_error_from_exception,
    safe_error_response,
)


# ── SafeAppError dataclass ─────────────────────────────────────────────────────

class TestSafeAppError:
    def test_instantiation_with_required_field(self):
        """SafeAppError can be created with only the category field."""
        err = SafeAppError(category="internal_error")
        assert err.category == "internal_error"

    def test_default_status_code_is_503(self):
        """Default status_code is HTTP 503."""
        err = SafeAppError(category="vector_store_error")
        assert err.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_public_message_defaults_to_none(self):
        """public_message defaults to None."""
        err = SafeAppError(category="retrieval_error")
        assert err.public_message is None

    def test_message_falls_back_to_category_messages(self):
        """message property returns the category fallback when public_message is None."""
        err = SafeAppError(category="timeout")
        assert "too long" in err.message.lower() or "timeout" in err.message.lower()

    def test_message_uses_public_message_when_set(self):
        """message property returns public_message when it is not None."""
        err = SafeAppError(category="internal_error", public_message="Custom error text")
        assert err.message == "Custom error text"

    def test_is_exception_subclass(self):
        """SafeAppError is a subclass of Exception (can be raised and caught)."""
        err = SafeAppError(category="blob_storage_error")
        with pytest.raises(SafeAppError):
            raise err

    def test_cause_type_and_metadata_defaults(self):
        """cause_type defaults to None; metadata defaults to empty dict."""
        err = SafeAppError(category="openai_provider_error")
        assert err.cause_type is None
        assert err.metadata == {}

    def test_all_fields_set_explicitly(self):
        """All fields can be set on construction."""
        err = SafeAppError(
            category="storage_error",
            status_code=500,
            public_message="Storage is down",
            cause_type="OSError",
            metadata={"file": "data.txt"},
        )
        assert err.category == "storage_error"
        assert err.status_code == 500
        assert err.message == "Storage is down"
        assert err.cause_type == "OSError"
        assert err.metadata == {"file": "data.txt"}

    def test_all_error_categories_have_fallback_message(self):
        """Every valid error category must produce a non-empty message."""
        categories = [
            "openai_provider_error",
            "vector_store_error",
            "blob_storage_error",
            "storage_error",
            "retrieval_error",
            "internal_error",
            "timeout",
        ]
        for cat in categories:
            err = SafeAppError(category=cat)  # type: ignore[arg-type]
            assert err.message, f"Empty message for category: {cat}"


# ── categorize_exception ───────────────────────────────────────────────────────

class TestCategorizeException:
    def test_generic_exception_returns_internal_error(self):
        """A plain Exception maps to the provided default category."""
        exc = Exception("something broke")
        result = categorize_exception(exc, default="internal_error")
        assert result == "internal_error"

    def test_openai_module_exception_returns_openai_category(self):
        """An exception whose type lives in an 'openai' module maps to openai_provider_error."""
        # Simulate an openai-flavoured exception by creating a class in a
        # module that contains 'openai' in its name.
        class FakeOpenAIError(Exception):
            pass
        FakeOpenAIError.__module__ = "openai.error"

        result = categorize_exception(FakeOpenAIError("quota exceeded"))
        assert result == "openai_provider_error"

    def test_ratelimit_name_in_type_returns_openai_category(self):
        """An exception named 'RateLimitError' maps to openai_provider_error."""
        class RateLimitError(Exception):
            pass

        result = categorize_exception(RateLimitError("too many requests"))
        assert result == "openai_provider_error"

    def test_ioerror_returns_storage_error(self):
        """An IOError maps to storage_error."""
        result = categorize_exception(IOError("disk full"))
        assert result == "storage_error"

    def test_oserror_returns_storage_error(self):
        """An OSError maps to storage_error."""
        result = categorize_exception(OSError("no such file"))
        assert result == "storage_error"

    def test_chroma_module_exception_returns_vector_store_error(self):
        """An exception from a 'chroma' module maps to vector_store_error."""
        class ChromaError(Exception):
            pass
        ChromaError.__module__ = "chromadb.errors"

        result = categorize_exception(ChromaError("index error"))
        assert result == "vector_store_error"

    def test_blob_module_exception_returns_blob_storage_error(self):
        """An exception from a 'blob' module maps to blob_storage_error."""
        class BlobError(Exception):
            pass
        BlobError.__module__ = "vercel.blob"

        result = categorize_exception(BlobError("upload failed"))
        assert result == "blob_storage_error"

    def test_default_override_is_used_when_no_match(self):
        """When no pattern matches, the caller-supplied default is returned."""
        result = categorize_exception(ValueError("unrecognised"), default="retrieval_error")
        assert result == "retrieval_error"


# ── safe_app_error_from_exception ─────────────────────────────────────────────

class TestSafeAppErrorFromException:
    def test_wraps_generic_exception_as_internal_error(self):
        """A plain ValueError becomes a SafeAppError with category=internal_error."""
        exc = ValueError("something went wrong")
        safe_err = safe_app_error_from_exception(exc, default="internal_error")
        assert isinstance(safe_err, SafeAppError)
        assert safe_err.category == "internal_error"
        assert safe_err.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_wraps_oserror_as_storage_error(self):
        """An OSError becomes a SafeAppError with category=storage_error and 503."""
        exc = OSError("disk full")
        safe_err = safe_app_error_from_exception(exc, default="internal_error")
        assert safe_err.category == "storage_error"
        assert safe_err.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_cause_type_is_set_to_exception_class_name(self):
        """cause_type is set to the class name of the wrapped exception."""
        exc = RuntimeError("boom")
        safe_err = safe_app_error_from_exception(exc, default="internal_error")
        assert safe_err.cause_type == "RuntimeError"

    def test_explicit_status_code_overrides_default(self):
        """status_code parameter overrides the auto-derived value."""
        exc = ValueError("oops")
        safe_err = safe_app_error_from_exception(
            exc, default="internal_error", status_code=418
        )
        assert safe_err.status_code == 418

    def test_metadata_is_forwarded(self):
        """metadata dict is attached to the resulting SafeAppError."""
        exc = IOError("no space")
        safe_err = safe_app_error_from_exception(
            exc, default="storage_error", metadata={"path": "/data/chroma"}
        )
        assert safe_err.metadata == {"path": "/data/chroma"}

    def test_openai_exception_mapped_to_503(self):
        """An openai-flavoured exception gets HTTP 503."""
        class AuthenticationError(Exception):
            pass
        AuthenticationError.__module__ = "openai"

        exc = AuthenticationError("invalid api key")
        safe_err = safe_app_error_from_exception(exc, default="internal_error")
        assert safe_err.category == "openai_provider_error"
        assert safe_err.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_non_internal_error_category_defaults_to_503(self):
        """Non-internal categories default to HTTP 503 status code."""
        exc = IOError("unavailable")
        safe_err = safe_app_error_from_exception(exc, default="retrieval_error")
        # storage_error is not internal_error, so expect 503
        assert safe_err.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ── safe_error_response ────────────────────────────────────────────────────────

class TestSafeErrorResponse:
    def _make_request(self, request_id: str | None = None) -> MagicMock:
        """Build a minimal Request-like mock."""
        request = MagicMock()
        state = MagicMock()
        if request_id is not None:
            state.request_id = request_id
        else:
            # Simulate absence of request_id attribute
            del state.request_id
        request.state = state
        return request

    def test_returns_json_response(self):
        """safe_error_response must return a JSONResponse instance."""
        request = MagicMock()
        request.state = MagicMock(spec=[])
        err = SafeAppError(category="internal_error")
        response = safe_error_response(request, err)
        assert isinstance(response, JSONResponse)

    def test_status_code_matches_error(self):
        """Response status_code must match the SafeAppError.status_code."""
        request = MagicMock()
        request.state = MagicMock(spec=[])
        err = SafeAppError(category="timeout", status_code=504)
        response = safe_error_response(request, err)
        assert response.status_code == 504

    def test_response_body_has_detail_key(self):
        """Response JSON body must contain a 'detail' key."""
        import json
        request = MagicMock()
        request.state = MagicMock(spec=[])
        err = SafeAppError(category="vector_store_error")
        response = safe_error_response(request, err)
        body = json.loads(response.body)
        assert "detail" in body

    def test_response_body_has_error_category_key(self):
        """Response JSON body must contain the 'error_category' key."""
        import json
        request = MagicMock()
        request.state = MagicMock(spec=[])
        err = SafeAppError(category="openai_provider_error")
        response = safe_error_response(request, err)
        body = json.loads(response.body)
        assert "error_category" in body
        assert body["error_category"] == "openai_provider_error"

    def test_response_body_has_request_id_key(self):
        """Response JSON body must contain the 'request_id' key (may be None)."""
        import json
        request = MagicMock()
        request.state = MagicMock(spec=[])
        err = SafeAppError(category="internal_error")
        response = safe_error_response(request, err)
        body = json.loads(response.body)
        assert "request_id" in body

    def test_detail_matches_error_message(self):
        """The 'detail' value must match the SafeAppError.message property."""
        import json
        request = MagicMock()
        request.state = MagicMock(spec=[])
        err = SafeAppError(category="internal_error", public_message="Detailed public info")
        response = safe_error_response(request, err)
        body = json.loads(response.body)
        assert body["detail"] == "Detailed public info"

    def test_request_id_propagated_from_state(self):
        """request_id from request.state must appear in the response body."""
        import json
        request = MagicMock()
        request.state = MagicMock()
        request.state.request_id = "req-abc-123"
        err = SafeAppError(category="retrieval_error")
        response = safe_error_response(request, err)
        body = json.loads(response.body)
        assert body["request_id"] == "req-abc-123"
