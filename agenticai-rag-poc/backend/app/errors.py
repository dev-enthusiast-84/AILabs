"""Typed, sanitized API errors for dependency and boundary failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import Request, status
from fastapi.responses import JSONResponse

ErrorCategory = Literal[
    "openai_provider_error",
    "vector_store_error",
    "blob_storage_error",
    "storage_error",
    "retrieval_error",
    "internal_error",
]

_CATEGORY_MESSAGES: dict[ErrorCategory, str] = {
    "openai_provider_error": "The AI provider is unavailable. Check provider settings and try again.",
    "vector_store_error": "The vector index is unavailable. Please try again shortly.",
    "blob_storage_error": "The file storage service is unavailable. Please try again shortly.",
    "storage_error": "Document storage is unavailable. Please try again shortly.",
    "retrieval_error": "Document retrieval is unavailable. Please try again shortly.",
    "internal_error": "An internal error occurred.",
}


@dataclass
class SafeAppError(Exception):
    """Exception carrying only safe response/log metadata."""

    category: ErrorCategory
    status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE
    public_message: str | None = None
    cause_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def message(self) -> str:
        return self.public_message or _CATEGORY_MESSAGES[self.category]


def request_id_from(request: Request | None) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def safe_error_response(request: Request, exc: SafeAppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error_category": exc.category,
            "request_id": request_id_from(request),
        },
    )


def _module_name(exc: Exception) -> str:
    return type(exc).__module__.lower()


def _type_name(exc: Exception) -> str:
    return type(exc).__name__.lower()


def categorize_exception(exc: Exception, *, default: ErrorCategory = "internal_error") -> ErrorCategory:
    """Map dependency exceptions to coarse, non-sensitive categories.

    The classifier intentionally uses exception type/module names, not exception
    messages, so provider prompts, keys, documents, and URLs are never copied
    into API responses or audit metadata.
    """
    module = _module_name(exc)
    name = _type_name(exc)

    if "openai" in module or "openai" in name or "ratelimit" in name or "authentication" in name:
        return "openai_provider_error"
    if "pinecone" in module or "chroma" in module or "vector" in module:
        return "vector_store_error"
    if "vercel" in module or "blob" in module:
        return "blob_storage_error"
    if isinstance(exc, (OSError, IOError)):
        return "storage_error"
    return default


def safe_app_error_from_exception(
    exc: Exception,
    *,
    default: ErrorCategory,
    status_code: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> SafeAppError:
    category = categorize_exception(exc, default=default)
    if status_code is None:
        status_code = (
            status.HTTP_500_INTERNAL_SERVER_ERROR
            if category == "internal_error"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return SafeAppError(
        category=category,
        status_code=status_code,
        cause_type=type(exc).__name__,
        metadata=metadata or {},
    )
