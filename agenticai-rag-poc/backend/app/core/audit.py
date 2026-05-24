"""Safe audit logging helpers for security-relevant backend events."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request

from app.auth.models import UserInDB
from app.voice.redaction import redact_sensitive_text

log = structlog.get_logger("audit")

_MAX_FIELD_LENGTH = 160


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        redacted = redact_sensitive_text(value)
        return redacted[:_MAX_FIELD_LENGTH]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k)[:64]: _safe_value(v) for k, v in value.items()}
    return type(value).__name__


def audit_event(
    event_type: str,
    *,
    status: str,
    request: Request | None = None,
    user: UserInDB | None = None,
    error_category: str | None = None,
    **metadata: Any,
) -> None:
    """Emit an audit event with scoped metadata and no raw prompt/content fields."""
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    payload: dict[str, Any] = {
        "event_type": event_type,
        "status": status,
        "request_id": request_id,
    }
    if user is not None:
        payload["user_role"] = user.role
        payload["session_scope"] = "present" if user.session_id else "none"
    if error_category:
        payload["error_category"] = error_category
    payload.update({key: _safe_value(value) for key, value in metadata.items()})
    log.info("audit_event", **payload)
