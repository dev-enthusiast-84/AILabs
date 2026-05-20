from types import SimpleNamespace
from unittest.mock import patch

from app.audit import audit_event
from app.auth.models import UserInDB
from app.main import global_exception_handler


def test_audit_event_redacts_sensitive_metadata():
    user = UserInDB(username="admin", hashed_password="x", role="admin")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-123"))
    sensitive = "email jane@example.com key sk-" + "A" * 30 + " password=hunter2"

    with patch("app.audit.log.info") as mock_info:
        audit_event("settings_update", status="failed", request=request, user=user, error=sensitive)

    _, kwargs = mock_info.call_args
    assert kwargs["event_type"] == "settings_update"
    assert kwargs["request_id"] == "req-123"
    assert kwargs["user_role"] == "admin"
    serialized = str(kwargs)
    assert "jane@example.com" not in serialized
    assert "sk-" + "A" * 30 not in serialized
    assert "hunter2" not in serialized
    assert "[REDACTED_EMAIL]" in serialized
    assert "[REDACTED_API_KEY]" in serialized
    assert "[REDACTED_PASSWORD]" in serialized


def test_global_exception_log_omits_sensitive_exception_message():
    request = SimpleNamespace(url=SimpleNamespace(path="/api/test"))
    sensitive = RuntimeError("boom jane@example.com key sk-" + "A" * 30)

    with patch("app.main.log.error") as mock_error:
        import anyio

        anyio.run(global_exception_handler, request, sensitive)

    _, kwargs = mock_error.call_args
    serialized = str(kwargs)
    assert kwargs["error_type"] == "RuntimeError"
    assert "jane@example.com" not in serialized
    assert "sk-" + "A" * 30 not in serialized
