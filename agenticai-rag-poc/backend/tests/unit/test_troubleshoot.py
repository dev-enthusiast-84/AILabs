"""Unit tests for app.api.troubleshoot helper functions and endpoint logic."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO

from starlette.requests import Request as StarletteRequest
from app.auth.models import UserInDB


def _make_user(role: str = "admin") -> UserInDB:
    return UserInDB(username=role, hashed_password="hashed", role=role)


# ── _sanitize_text ────────────────────────────────────────────────────────────

class TestSanitizeText:
    def test_strips_html_tags(self):
        from app.api.troubleshoot import _sanitize_text
        result = _sanitize_text("<script>alert('xss')</script>Error message", 1000)
        assert "<script>" not in result
        assert "Error message" in result

    def test_truncates_to_max_len(self):
        from app.api.troubleshoot import _sanitize_text
        assert len(_sanitize_text("a" * 200, 50)) == 50

    def test_passthrough_clean_text(self):
        from app.api.troubleshoot import _sanitize_text
        text = "TypeError: 'NoneType' object is not subscriptable"
        assert _sanitize_text(text, 1000) == text


# ── _build_user_prompt ────────────────────────────────────────────────────────

class TestBuildUserPrompt:
    def test_includes_all_context_fields(self):
        from app.api.troubleshoot import _build_user_prompt
        prompt = _build_user_prompt(
            "500 Internal Server Error",
            log_content="ERROR: connection refused",
            component="backend",
            environment="local",
            severity="high",
        )
        assert "backend" in prompt
        assert "local" in prompt
        assert "high" in prompt
        assert "500 Internal Server Error" in prompt
        assert "connection refused" in prompt

    def test_omits_context_header_when_no_fields(self):
        from app.api.troubleshoot import _build_user_prompt
        prompt = _build_user_prompt("err", None, None, None, None)
        assert "Context:" not in prompt
        assert "err" in prompt

    def test_omits_log_section_when_no_log(self):
        from app.api.troubleshoot import _build_user_prompt
        prompt = _build_user_prompt("err", None, None, None, None)
        assert "Log output" not in prompt


# ── _parse_llm_response ────────────────────────────────────────────────────────

class TestParseLlmResponse:
    def _valid_payload(self):
        return {
            "error_category": "config",
            "root_cause": "Missing API key",
            "hypotheses": [
                {"rank": 1, "title": "No API key", "confidence": 90, "explanation": "..."}
            ],
            "remediation_steps": ["1. Set OPENAI_API_KEY in .env"],
            "follow_up_questions": [],
            "affected_files": ["backend/.env.example"],
        }

    def test_parses_valid_json(self):
        from app.api.troubleshoot import _parse_llm_response
        result = _parse_llm_response(json.dumps(self._valid_payload()))
        assert result.error_category == "config"
        assert result.root_cause == "Missing API key"
        assert len(result.hypotheses) == 1
        assert result.hypotheses[0].confidence == 90

    def test_strips_markdown_fences(self):
        from app.api.troubleshoot import _parse_llm_response
        wrapped = f"```json\n{json.dumps(self._valid_payload())}\n```"
        result = _parse_llm_response(wrapped)
        assert result.error_category == "config"

    def test_clamps_confidence_to_0_100(self):
        from app.api.troubleshoot import _parse_llm_response
        payload = self._valid_payload()
        payload["hypotheses"][0]["confidence"] = 150
        result = _parse_llm_response(json.dumps(payload))
        assert result.hypotheses[0].confidence == 100

    def test_sorts_hypotheses_by_rank(self):
        from app.api.troubleshoot import _parse_llm_response
        payload = self._valid_payload()
        payload["hypotheses"] = [
            {"rank": 2, "title": "B", "confidence": 40, "explanation": ""},
            {"rank": 1, "title": "A", "confidence": 80, "explanation": ""},
        ]
        result = _parse_llm_response(json.dumps(payload))
        assert result.hypotheses[0].title == "A"
        assert result.hypotheses[1].title == "B"

    def test_raises_json_decode_error_on_bad_input(self):
        from app.api.troubleshoot import _parse_llm_response
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response("not valid json {{{")

    def test_handles_missing_optional_fields(self):
        from app.api.troubleshoot import _parse_llm_response
        minimal = json.dumps({
            "error_category": "unknown",
            "root_cause": "unclear",
            "hypotheses": [],
            "remediation_steps": [],
        })
        result = _parse_llm_response(minimal)
        assert result.follow_up_questions == []
        assert result.affected_files == []


# ── _read_screenshots ─────────────────────────────────────────────────────────

class TestReadScreenshots:
    def _make_upload(self, content: bytes, content_type: str = "image/png") -> MagicMock:
        f = MagicMock()
        f.content_type = content_type
        f.read = AsyncMock(return_value=content)
        return f

    @pytest.mark.asyncio
    async def test_encodes_valid_png(self):
        from app.api.troubleshoot import _read_screenshots
        fake = self._make_upload(b"\x89PNG\r\n\x1a\n" + b"x" * 100)
        result = await _read_screenshots([fake])
        assert len(result) == 1
        assert result[0]["type"] == "image_url"
        assert "data:image/png;base64," in result[0]["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_rejects_invalid_mime_type(self):
        from app.api.troubleshoot import _read_screenshots
        fake = self._make_upload(b"data", content_type="text/plain")
        result = await _read_screenshots([fake])
        assert result == []

    @pytest.mark.asyncio
    async def test_rejects_oversized_file(self):
        from app.api.troubleshoot import _read_screenshots, _MAX_SCREENSHOT_BYTES
        fake = self._make_upload(b"x" * (_MAX_SCREENSHOT_BYTES + 1))
        result = await _read_screenshots([fake])
        assert result == []

    @pytest.mark.asyncio
    async def test_caps_at_max_screenshots(self):
        from app.api.troubleshoot import _read_screenshots, _MAX_SCREENSHOTS
        fakes = [self._make_upload(b"img") for _ in range(_MAX_SCREENSHOTS + 2)]
        result = await _read_screenshots(fakes)
        assert len(result) <= _MAX_SCREENSHOTS

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        from app.api.troubleshoot import _read_screenshots
        result = await _read_screenshots([])
        assert result == []


# ── analyze endpoint ──────────────────────────────────────────────────────────

class TestAnalyzeEndpoint:
    def _mock_request(self) -> StarletteRequest:
        # slowapi's @limiter.limit checks isinstance(request, Request) — use a real
        # minimal Starlette Request so the rate-limit decorator passes through.
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/troubleshoot/analyze",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
        }
        return StarletteRequest(scope)

    def _good_llm_response(self):
        return json.dumps({
            "error_category": "config",
            "root_cause": "OPENAI_API_KEY not set",
            "hypotheses": [
                {"rank": 1, "title": "Missing key", "confidence": 95, "explanation": "env var absent"}
            ],
            "remediation_steps": ["1. Add OPENAI_API_KEY to backend/.env"],
            "follow_up_questions": [],
            "affected_files": ["backend/.env.example"],
        })

    @pytest.mark.asyncio
    async def test_raises_503_when_no_api_key(self, monkeypatch):
        from app.api.troubleshoot import analyze
        from app.core.errors import SafeAppError
        monkeypatch.setattr("app.runtime.settings_store.get_effective_api_key", lambda: "")

        with pytest.raises(SafeAppError) as exc_info:
            await analyze(
                request=self._mock_request(),
                error_message="Some error",
                _user=_make_user(),
            )
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_returns_structured_response(self, monkeypatch):
        from app.api.troubleshoot import analyze

        monkeypatch.setattr("app.runtime.settings_store.get_effective_api_key", lambda: "sk-test")
        monkeypatch.setattr("app.runtime.settings_store.get_effective_model", lambda: "gpt-4o")

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = self._good_llm_response()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("app.api.troubleshoot.AsyncOpenAI", return_value=mock_client):
            result = await analyze(
                request=self._mock_request(),
                error_message="OPENAI_API_KEY not set in backend/.env",
                log_content="KeyError: 'openai_api_key'",
                component="backend",
                environment="local",
                severity="high",
                screenshots=None,
                _user=_make_user(),
            )

        assert result.error_category == "config"
        assert result.root_cause
        assert len(result.hypotheses) >= 1
        assert result.hypotheses[0].confidence == 95
        assert len(result.remediation_steps) >= 1

    @pytest.mark.asyncio
    async def test_raises_502_on_llm_json_parse_error(self, monkeypatch):
        from app.api.troubleshoot import analyze
        from app.core.errors import SafeAppError

        monkeypatch.setattr("app.runtime.settings_store.get_effective_api_key", lambda: "sk-test")
        monkeypatch.setattr("app.runtime.settings_store.get_effective_model", lambda: "gpt-4o")

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "not json at all"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("app.api.troubleshoot.AsyncOpenAI", return_value=mock_client):
            with pytest.raises(SafeAppError) as exc_info:
                await analyze(
                    request=self._mock_request(),
                    error_message="some error",
                    log_content=None,
                    component=None,
                    environment=None,
                    severity=None,
                    screenshots=None,
                    _user=_make_user(),
                )
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_raises_502_on_openai_network_error(self, monkeypatch):
        from app.api.troubleshoot import analyze
        from app.core.errors import SafeAppError

        monkeypatch.setattr("app.runtime.settings_store.get_effective_api_key", lambda: "sk-test")
        monkeypatch.setattr("app.runtime.settings_store.get_effective_model", lambda: "gpt-4o")

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=ConnectionError("timeout"))

        with patch("app.api.troubleshoot.AsyncOpenAI", return_value=mock_client):
            with pytest.raises(SafeAppError) as exc_info:
                await analyze(
                    request=self._mock_request(),
                    error_message="some error",
                    log_content=None,
                    component=None,
                    environment=None,
                    severity=None,
                    screenshots=None,
                    _user=_make_user(),
                )
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_sanitizes_xss_in_error_message(self, monkeypatch):
        """HTML in error_message is stripped before reaching the LLM prompt."""
        from app.api.troubleshoot import _sanitize_text

        dirty = "<img src=x onerror=alert(1)>TypeError: bad input"
        clean = _sanitize_text(dirty, 1000)
        assert "<img" not in clean
        assert "TypeError: bad input" in clean
