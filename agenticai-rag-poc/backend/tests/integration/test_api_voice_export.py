"""Integration tests for chat voice export (OpenAI mocked, no network)."""

import base64
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APITimeoutError


_VALID_KEY = "sk-" + "V" * 48


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    from app.auth.router import limiter as auth_limiter
    from app.api.voice_export import _job_store

    _job_store.reset()
    auth_limiter._storage.reset()
    yield
    _job_store.reset()
    auth_limiter._storage.reset()


def _mock_openai_audio(mock_openai, audio: bytes = b"mp3-bytes"):
    client = mock_openai.return_value
    client.audio.speech.create.return_value = MagicMock(content=audio)
    return client


def test_voice_export_requires_auth(client):
    resp = client.post("/api/chat/voice/export", json={"text": "Hello"})

    assert resp.status_code == 403


def test_voice_export_returns_redacted_playable_mp3_payload(client, auth_headers):
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        openai_client = _mock_openai_audio(mock_openai, b"fake-mp3")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={
                "messages": [
                    {"role": "user", "content": "My email is jane@example.com and key sk-" + "A" * 30},
                    {"role": "assistant", "content": "Call 416-555-1212 for help."},
                ]
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_mime_type"] == "audio/mpeg"
    assert body["audio_format"] == "mp3"
    assert base64.b64decode(body["audio_base64"]) == b"fake-mp3"
    assert "jane@example.com" not in body["transcript"]
    assert "416-555-1212" not in body["transcript"]
    assert "sk-" + "A" * 30 not in body["transcript"]
    assert "[REDACTED_EMAIL]" in body["transcript"]
    assert "[REDACTED_PHONE]" in body["transcript"]
    assert "[REDACTED_API_KEY]" in body["transcript"]
    assert openai_client.audio.speech.create.call_args.kwargs["input"] == body["transcript"]
    assert "jane@example.com" not in openai_client.audio.speech.create.call_args.kwargs["input"]


def test_voice_export_redacts_voice_transcript_before_audio_synthesis(client, auth_headers):
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        openai_client = _mock_openai_audio(mock_openai, b"voice-mp3")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={
                "language": "es",
                "messages": [
                    {
                        "role": "user",
                        "origin": "voice",
                        "content": "Mi correo es jane@example.com y mi token es Bearer " + "a" * 32,
                    },
                    {
                        "role": "assistant",
                        "content": "La respuesta segura usa la tarjeta 4111 1111 1111 1111.",
                    },
                ],
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    synthesis_input = openai_client.audio.speech.create.call_args.kwargs["input"]
    assert synthesis_input == body["transcript"]
    assert "jane@example.com" not in synthesis_input
    assert "a" * 32 not in synthesis_input
    assert "4111 1111 1111 1111" not in synthesis_input
    assert "[REDACTED_EMAIL]" in synthesis_input
    assert "[REDACTED_TOKEN]" in synthesis_input
    assert "[REDACTED_PAYMENT_CARD]" in synthesis_input


def test_voice_redact_endpoint_returns_authoritative_redacted_transcript(client, auth_headers):
    resp = client.post(
        "/api/chat/voice/redact",
        headers=auth_headers,
        json={
            "messages": [
                {"role": "user", "content": "email jane@example.com password=hunter2"},
                {"role": "assistant", "content": "token Bearer " + "a" * 32},
            ]
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["redacted"] is True
    assert "jane@example.com" not in body["transcript"]
    assert "hunter2" not in body["transcript"]
    assert "a" * 32 not in body["transcript"]
    assert "[REDACTED_EMAIL]" in body["transcript"]
    assert "[REDACTED_PASSWORD]" in body["transcript"]
    assert "[REDACTED_TOKEN]" in body["transcript"]


def test_voice_redact_endpoint_requires_auth(client):
    resp = client.post("/api/chat/voice/redact", json={"text": "jane@example.com"})

    assert resp.status_code == 403


def test_voice_export_uses_vercel_stripped_prefix(client, auth_headers):
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        _mock_openai_audio(mock_openai)
        resp = client.post(
            "/chat/voice/export",
            headers=auth_headers,
            json={"transcript": "Assistant: hello"},
        )

    assert resp.status_code == 200


def test_voice_export_missing_api_key_returns_clear_error(client, auth_headers):
    with patch("app.api.voice_export.get_effective_api_key", return_value=""), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Hello"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "missing_api_key"
    assert "api key" in resp.json()["detail"]["message"].lower()
    mock_openai.assert_not_called()


def test_voice_export_generation_failure_returns_clear_error(client, auth_headers):
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.side_effect = RuntimeError("boom")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Hello"},
        )

    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "voice_export_generation_failed"
    assert "failed to generate" in resp.json()["detail"]["message"].lower()


def test_voice_export_rejects_transcript_over_safe_limit(client, auth_headers):
    text = "A" * 12001
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": text},
        )

    assert resp.status_code == 422
    mock_openai.assert_not_called()


def _wait_for_job(client, headers, job_id: str, *, target: str = "succeeded", attempts: int = 40):
    body = None
    for _ in range(attempts):
        resp = client.get(f"/api/chat/voice/export/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] == target:
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {target}: {body}")


def test_voice_export_defers_large_transcript_and_exposes_expiring_artifact(client, auth_headers):
    text = ("Large export sentence. " * 250).strip()
    assert len(text) > 4000

    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        openai_client = _mock_openai_audio(mock_openai, b"chunk-mp3")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": text},
        )

        assert resp.status_code == 202
        assert resp.headers["Retry-After"] == "1"
        accepted = resp.json()
        assert accepted["status"] == "queued"
        assert accepted["job_id"]
        assert accepted["status_url"].endswith(accepted["job_id"])
        assert accepted["cancel_url"].endswith(accepted["job_id"])
        assert accepted["policy"] == {
            "max_retries": 1,
            "timeout_seconds": 30.0,
            "retry_after_seconds": 1,
            "artifact_ttl_seconds": 600,
        }

        done = _wait_for_job(client, auth_headers, accepted["job_id"])

    assert done["status"] == "succeeded"
    assert done["artifact"]["audio_mime_type"] == "audio/mpeg"
    assert done["artifact"]["audio_format"] == "mp3"
    assert base64.b64decode(done["artifact"]["audio_base64"]) == b"chunk-mp3" * openai_client.audio.speech.create.call_count
    assert done["artifact"]["expires_at"] == done["artifact_expires_at"]
    assert openai_client.audio.speech.create.call_count >= 2
    for call in openai_client.audio.speech.create.call_args_list:
        assert len(call.kwargs["input"]) <= 4000


def test_voice_export_cancel_marks_job_canceled_and_suppresses_artifact(client, auth_headers):
    def slow_audio(**_kwargs):
        time.sleep(0.05)
        return MagicMock(content=b"late-mp3")

    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.side_effect = slow_audio
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Cancelable export", "defer": True},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        cancel = client.delete(f"/api/chat/voice/export/jobs/{job_id}", headers=auth_headers)
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "canceled"

        time.sleep(0.08)
        status_resp = client.get(f"/api/chat/voice/export/jobs/{job_id}", headers=auth_headers)

    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "canceled"
    assert body["artifact"] is None


def test_voice_export_artifact_expiration_clears_audio_payload(client, auth_headers):
    from app.api.voice_export import _job_store

    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        _mock_openai_audio(mock_openai, b"expiring-mp3")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Expire this export", "defer": True},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        _wait_for_job(client, auth_headers, job_id)

    _job_store.force_expire(job_id=job_id)
    expired = client.get(f"/api/chat/voice/export/jobs/{job_id}", headers=auth_headers)

    assert expired.status_code == 200
    body = expired.json()
    assert body["status"] == "expired"
    assert body["artifact"] is None


def test_voice_export_job_status_is_scoped_to_owner(client, auth_headers):
    guest_token = client.post("/api/auth/guest").json()["access_token"]
    guest_headers = {"Authorization": f"Bearer {guest_token}"}

    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        _mock_openai_audio(mock_openai, b"scoped-mp3")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Owner scoped export", "defer": True},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

    unauthorized = client.get(f"/api/chat/voice/export/jobs/{job_id}", headers=guest_headers)
    cancel = client.delete(f"/api/chat/voice/export/jobs/{job_id}", headers=guest_headers)
    owner = _wait_for_job(client, auth_headers, job_id)

    assert unauthorized.status_code == 404
    assert unauthorized.json()["detail"]["code"] == "voice_export_job_not_found"
    assert cancel.status_code == 404
    assert owner["status"] == "succeeded"


def test_voice_export_deferred_job_retries_timeout_once(client, auth_headers):
    request = httpx.Request("POST", "https://api.openai.test/v1/audio/speech")

    with patch("app.api.voice_export._ASYNC_EXPORT_RETRY_AFTER_SECONDS", 0), \
         patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.side_effect = [
            APITimeoutError(request),
            MagicMock(content=b"after-retry"),
        ]
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Retry this export", "defer": True},
        )
        assert resp.status_code == 202
        done = _wait_for_job(client, auth_headers, resp.json()["job_id"])

    assert done["status"] == "succeeded"
    assert done["retry_count"] == 1
    assert done["policy"]["max_retries"] == 1
    assert done["policy"]["timeout_seconds"] == 30.0
    assert base64.b64decode(done["artifact"]["audio_base64"]) == b"after-retry"


def test_voice_redact_rejects_aggregate_transcript_over_safe_limit(client, auth_headers):
    messages = [
        {"role": "user", "content": "A" * 6000},
        {"role": "assistant", "content": "B" * 6000},
        {"role": "user", "content": "C"},
    ]

    resp = client.post(
        "/api/chat/voice/redact",
        headers=auth_headers,
        json={"messages": messages},
    )

    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["code"] == "transcript_too_large"
    assert detail["limit_chars"] == 12000
    assert detail["actual_chars"] > 12000


def test_voice_export_timeout_returns_safe_retry_message(client, auth_headers):
    request = httpx.Request("POST", "https://api.openai.test/v1/audio/speech")
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.side_effect = APITimeoutError(request)
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Hello"},
        )

    assert resp.status_code == 504
    detail = resp.json()["detail"]
    assert detail["code"] == "voice_export_timeout"
    assert "timed out" in detail["message"].lower()
    assert detail["timeout_seconds"] == 30.0


def test_voice_export_rejects_oversized_audio_response(client, auth_headers):
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export._MAX_AUDIO_BYTES", 4), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        _mock_openai_audio(mock_openai, b"12345")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Hello"},
        )

    assert resp.status_code == 502
    assert resp.json()["detail"] == {
        "code": "audio_response_too_large",
        "message": "Audio export response was too large to return safely. Try a shorter transcript.",
        "limit_bytes": 4,
    }


def test_voice_export_uses_guest_runtime_api_key_scope(client):
    guest_token = client.post("/api/auth/guest").json()["access_token"]
    headers = {"Authorization": f"Bearer {guest_token}"}
    settings_resp = client.post(
        "/api/settings/",
        headers=headers,
        json={"api_key": _VALID_KEY, "model": "gpt-4o-mini"},
    )
    assert settings_resp.status_code == 200

    with patch("app.api.voice_export.OpenAI") as mock_openai:
        _mock_openai_audio(mock_openai)
        resp = client.post(
            "/api/chat/voice/export",
            headers=headers,
            json={"text": "Guest scoped export"},
        )

    assert resp.status_code == 200
    mock_openai.assert_called_once_with(api_key=_VALID_KEY, timeout=30.0)


# ── Validation edge cases for ChatVoiceExportRequest ─────────────────────────

def test_voice_export_invalid_voice_name_returns_422(client, auth_headers):
    """An unsupported voice name is rejected at the request validation layer."""
    resp = client.post(
        "/api/chat/voice/export",
        headers=auth_headers,
        json={"text": "Hello there", "voice": "invalid_voice"},
    )
    assert resp.status_code == 422


def test_voice_export_message_content_too_long_returns_422(client, auth_headers):
    """A message with content exceeding _MAX_MESSAGE_CHARS is rejected."""
    long_content = "A" * 6001  # _MAX_MESSAGE_CHARS = 6000
    resp = client.post(
        "/api/chat/voice/export",
        headers=auth_headers,
        json={
            "messages": [
                {"role": "assistant", "content": long_content}
            ]
        },
    )
    assert resp.status_code == 422


def test_voice_export_transcript_too_long_returns_422(client, auth_headers):
    """A transcript field exceeding _MAX_TRANSCRIPT_CHARS is rejected."""
    long_transcript = "B" * 12001  # _MAX_TRANSCRIPT_CHARS = 12000
    resp = client.post(
        "/api/chat/voice/export",
        headers=auth_headers,
        json={"transcript": long_transcript},
    )
    assert resp.status_code == 422


def test_voice_export_no_content_returns_422(client, auth_headers):
    """A request with no text, transcript, or messages is rejected."""
    resp = client.post(
        "/api/chat/voice/export",
        headers=auth_headers,
        json={"voice": "alloy"},
    )
    assert resp.status_code == 422


def test_voice_export_too_many_messages_returns_422(client, auth_headers):
    """A request with more than _MAX_MESSAGES messages is rejected."""
    messages = [{"role": "user", "content": "Hello"} for _ in range(101)]  # _MAX_MESSAGES = 100
    resp = client.post(
        "/api/chat/voice/export",
        headers=auth_headers,
        json={"messages": messages},
    )
    assert resp.status_code == 422


def test_voice_export_text_field_too_long_returns_422(client, auth_headers):
    """A text field exceeding _MAX_TRANSCRIPT_CHARS is rejected."""
    long_text = "C" * 12001  # _MAX_TRANSCRIPT_CHARS = 12000
    resp = client.post(
        "/api/chat/voice/export",
        headers=auth_headers,
        json={"text": long_text},
    )
    assert resp.status_code == 422


def test_voice_export_deferred_job_fails_on_general_exception(client, auth_headers):
    """When job execution raises a non-timeout exception, job status is failed."""
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.side_effect = RuntimeError("unexpected crash")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Fail this export", "defer": True},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        done = _wait_for_job(client, auth_headers, job_id, target="failed")

    assert done["status"] == "failed"
    assert done["error"]["code"] == "voice_export_generation_failed"


def test_voice_export_deferred_job_not_found_returns_404(client, auth_headers):
    """Polling a non-existent job ID returns 404."""
    resp = client.get("/api/chat/voice/export/jobs/nonexistent-job-id", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "voice_export_job_not_found"


def test_voice_export_cancel_nonexistent_job_returns_404(client, auth_headers):
    """Canceling a non-existent job returns 404."""
    resp = client.delete("/api/chat/voice/export/jobs/does-not-exist-job", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "voice_export_job_not_found"


def test_voice_redact_no_content_returns_422(client, auth_headers):
    """The /redact endpoint also requires at least one content field."""
    resp = client.post(
        "/api/chat/voice/redact",
        headers=auth_headers,
        json={"voice": "alloy"},
    )
    assert resp.status_code == 422


def test_voice_export_deferred_job_fails_on_max_retries_timeout(client, auth_headers):
    """When all retries are exhausted due to timeout, job status is failed."""
    import httpx as _httpx
    request = _httpx.Request("POST", "https://api.openai.test/v1/audio/speech")

    with patch("app.api.voice_export._ASYNC_EXPORT_RETRY_AFTER_SECONDS", 0), \
         patch("app.api.voice_export._ASYNC_EXPORT_MAX_RETRIES", 0), \
         patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.side_effect = APITimeoutError(request)
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Timeout this export", "defer": True},
        )
        assert resp.status_code == 202
        done = _wait_for_job(client, auth_headers, resp.json()["job_id"], target="failed")

    assert done["status"] == "failed"
    assert done["error"]["code"] == "voice_export_timeout"


def test_voice_export_sync_empty_audio_triggers_generation_failed(client, auth_headers):
    """When OpenAI returns empty bytes in sync path, a 502 error is returned."""
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        mock_openai.return_value.audio.speech.create.return_value = MagicMock(content=b"")
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Short text"},
        )

    # Empty audio raises ValueError which is caught as generation_failed
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "voice_export_generation_failed"


def test_voice_export_empty_after_redaction_returns_422(client, auth_headers):
    """When transcript is empty after redaction, export returns 422."""
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export._export_text", return_value=""), \
         patch("app.api.voice_export._raw_export_text", return_value="some original text"), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "some original text"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "empty_after_redaction"
    mock_openai.assert_not_called()


def test_voice_redact_empty_after_redaction_returns_422(client, auth_headers):
    """When transcript is empty after redaction on /redact endpoint, returns 422."""
    with patch("app.api.voice_export._export_text", return_value=""), \
         patch("app.api.voice_export._raw_export_text", return_value="some text"):
        resp = client.post(
            "/api/chat/voice/redact",
            headers=auth_headers,
            json={"text": "some text"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "empty_after_redaction"


def test_voice_export_deferred_job_audio_too_large_fails_job(client, auth_headers):
    """When async job generates audio exceeding max bytes, job status is failed."""
    with patch("app.api.voice_export.get_effective_api_key", return_value=_VALID_KEY), \
         patch("app.api.voice_export._MAX_AUDIO_BYTES", 4), \
         patch("app.api.voice_export.OpenAI") as mock_openai:
        _mock_openai_audio(mock_openai, b"12345")  # 5 bytes > limit of 4
        resp = client.post(
            "/api/chat/voice/export",
            headers=auth_headers,
            json={"text": "Test deferred too large", "defer": True},
        )
        assert resp.status_code == 202
        done = _wait_for_job(client, auth_headers, resp.json()["job_id"], target="failed")

    assert done["status"] == "failed"
    assert done["error"]["code"] == "audio_response_too_large"
