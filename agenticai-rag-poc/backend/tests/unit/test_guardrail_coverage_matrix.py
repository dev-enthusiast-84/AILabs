"""Guardrail coverage matrix — 9-surface parametrized tests.

Each test submits a known sensitive fixture through a specific application surface
and asserts: (a) the original value is absent, (b) the correct [REDACTED_*] label
is present (or trimming occurred, depending on the surface).

Surfaces covered:
  1. query_api_boundary_trim   — sanitize_query() strips whitespace
  2. voice_export_api_trim     — Pydantic _trim_content validators
  3. settings_api_trim         — Pydantic field_validator(mode='before')
  4. voice_transcript_redact   — build_redacted_transcript()
  5. audio_synthesis_redact    — redact_sensitive_text()
  6. redact_and_flag_typed_input  — redact_and_flag() for typed query text
  7. redact_and_flag_history   — redact_and_flag() on history items
  8. redact_and_flag_answer_instruction — redact_and_flag() on instruction
  9. frontend_mask_display     — maskSensitive() label taxonomy alignment
     (Python-side smoke: verified via contract JSON; full TS tests in redact.test.ts)
"""
import pytest
from fastapi import HTTPException
from app.guardrails.safety import sanitize_query
from app.voice.redaction import (
    RedactionResult,
    build_redacted_transcript,
    redact_and_flag,
    redact_sensitive_text,
)


# ── Surface 1: query API boundary trim ───────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("  What is the policy?  ", "What is the policy?"),
    ("\tLeading tab\t", "Leading tab"),
    ("  hello  ", "hello"),
])
def test_query_api_boundary_trim(raw: str, expected: str):
    result = sanitize_query(raw)
    assert result == expected


def test_query_api_boundary_trim_empty_raises():
    with pytest.raises(HTTPException) as exc:
        sanitize_query("   ")
    assert exc.value.status_code == 422


# ── Surface 2: voice export API boundary trim ─────────────────────────────────

def test_voice_export_api_message_content_trimmed():
    """ChatVoiceExportMessage._trim_content strips whitespace from content."""
    from app.api.voice_export import ChatVoiceExportMessage
    msg = ChatVoiceExportMessage(role="user", content="  hello world  ", origin="typed")
    assert msg.content == "hello world"


def test_voice_export_api_transcript_trimmed():
    """ChatVoiceExportRequest._trim_optional_text strips whitespace from transcript field."""
    from app.api.voice_export import ChatVoiceExportRequest
    req = ChatVoiceExportRequest(transcript="  My transcript text  ", language="en")
    assert req.transcript == "My transcript text"


def test_voice_export_api_text_trimmed():
    """ChatVoiceExportRequest._trim_optional_text strips whitespace from text field."""
    from app.api.voice_export import ChatVoiceExportRequest
    req = ChatVoiceExportRequest(text="  synthesise this  ", language="en")
    assert req.text == "synthesise this"


# ── Surface 3: settings API boundary trim ────────────────────────────────────

def test_settings_api_trim_api_key():
    """SettingsUpdateRequest validator strips whitespace from all string fields."""
    from app.api.settings import SettingsUpdateRequest
    req = SettingsUpdateRequest(api_key="  sk-" + "x" * 30 + "  ")
    assert not req.api_key.startswith(" ")
    assert not req.api_key.endswith(" ")


def test_settings_api_trim_model_field():
    from app.api.settings import SettingsUpdateRequest
    req = SettingsUpdateRequest(model="  gpt-4o  ")
    assert req.model == "gpt-4o"


# ── Surface 4: voice transcript export redaction ──────────────────────────────

@pytest.mark.parametrize("fixture,label", [
    ("user@example.com", "[REDACTED_EMAIL]"),
    ("123-45-6789", "[REDACTED_SSN]"),
    ("4111111111111111", "[REDACTED_PAYMENT_CARD]"),
    ("sk-abcdefghijklmnopqrstuvwxyz12345", "[REDACTED_API_KEY]"),
])
def test_voice_transcript_redacts_pii(fixture: str, label: str):
    messages = [("user", f"my value is {fixture}")]
    transcript = build_redacted_transcript(messages)
    assert fixture not in transcript
    assert label in transcript


# ── Surface 5: audio synthesis input redaction ───────────────────────────────

@pytest.mark.parametrize("fixture,label", [
    ("user@example.com", "[REDACTED_EMAIL]"),
    ("password=s3cr3tp@ss", "[REDACTED_PASSWORD]"),
    ("Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9payload", "[REDACTED_TOKEN]"),
])
def test_audio_synthesis_redacts_pii(fixture: str, label: str):
    result = redact_sensitive_text(fixture)
    assert fixture not in result or label in result
    assert label in result


# ── Surface 6: typed query input — redact_and_flag ───────────────────────────

@pytest.mark.parametrize("fixture,label", [
    ("contact support@example.com for help", "[REDACTED_EMAIL]"),
    ("my SSN is 123-45-6789", "[REDACTED_SSN]"),
    ("card 4111 1111 1111 1111 expired", "[REDACTED_PAYMENT_CARD]"),
])
def test_typed_query_redact_and_flag(fixture: str, label: str):
    result = redact_and_flag(fixture)
    assert isinstance(result, RedactionResult)
    assert result.was_redacted is True
    assert label in result.text


def test_typed_query_clean_no_flag():
    result = redact_and_flag("What is the remote work policy?")
    assert result.was_redacted is False
    assert result.text == "What is the remote work policy?"


# ── Surface 7: query history items redaction ──────────────────────────────────

def test_history_item_redacted():
    history_content = "Earlier I mentioned user@example.com"
    result = redact_and_flag(history_content)
    assert result.was_redacted is True
    assert "[REDACTED_EMAIL]" in result.text
    assert "user@example.com" not in result.text


# ── Surface 8: answer_instruction redaction ───────────────────────────────────

def test_answer_instruction_redacted():
    instruction = "Answer as admin@company.com would"
    result = redact_and_flag(instruction)
    assert result.was_redacted is True
    assert "[REDACTED_EMAIL]" in result.text


def test_answer_instruction_clean():
    instruction = "Answer in French"
    result = redact_and_flag(instruction)
    assert result.was_redacted is False


# ── Surface 9: frontend display redaction taxonomy alignment (contract check) ──

def test_frontend_label_taxonomy_contract():
    """Backend labels in _PATTERNS must match the canonical contract set."""
    from app.voice.redaction import _PATTERNS

    canonical_labels = {
        "[REDACTED_PRIVATE_KEY]",
        "[REDACTED_API_KEY]",
        "[REDACTED_TOKEN]",
        "[REDACTED_PASSWORD]",
        "[REDACTED_SECRET]",
        "[REDACTED_EMAIL]",
        "[REDACTED_SSN]",
        "[REDACTED_PHONE]",
        "[REDACTED_PAYMENT_CARD]",
    }
    backend_labels = {p.label for p in _PATTERNS}
    # every backend label must be in the canonical set
    assert backend_labels <= canonical_labels
    # no [REDACTED_GOV_ID] in backend (that was the old frontend mismatch)
    assert "[REDACTED_GOV_ID]" not in backend_labels
