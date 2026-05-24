from types import SimpleNamespace
from unittest.mock import patch

from app.core.audit import _safe_value, audit_event
from app.auth.models import UserInDB
from app.main import global_exception_handler


def test_audit_event_redacts_sensitive_metadata():
    user = UserInDB(username="admin", hashed_password="x", role="admin")
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-123"))
    sensitive = "email jane@example.com key sk-" + "A" * 30 + " password=hunter2"

    with patch("app.core.audit.log.info") as mock_info:
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


def test_safe_value_dict_recurses():
    """_safe_value with a dict value applies safe_value to each item (lines 26-27)."""
    result = _safe_value({"key": "plain text", "num": 42})
    assert result == {"key": "plain text", "num": 42}


def test_safe_value_dict_key_truncated_to_64():
    """Dict keys longer than 64 chars are truncated (line 27)."""
    long_key = "k" * 100
    result = _safe_value({long_key: "val"})
    assert list(result.keys())[0] == "k" * 64


def test_safe_value_non_standard_type_returns_type_name():
    """An object of an unrecognised type returns its class name (line 28)."""
    class _Custom:
        pass

    result = _safe_value(_Custom())
    assert result == "_Custom"


def test_audit_event_with_dict_metadata():
    """audit_event with a dict metadata value exercises the dict branch (lines 26-27)."""
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-dict"))
    user = UserInDB(username="admin", hashed_password="x", role="admin")

    with patch("app.core.audit.log.info") as mock_info:
        audit_event("query", status="completed", request=request, user=user,
                    extra={"count": 3, "mode": "agentic"})

    _, kwargs = mock_info.call_args
    assert kwargs["extra"] == {"count": 3, "mode": "agentic"}
