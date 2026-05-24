"""Unit tests for backend/app/voice/redaction.py.

Covers:
  - RedactionResult dataclass invariants
  - redact_and_flag() return type and was_redacted flag
  - redact_sensitive_text() backward-compatibility wrapper
  - All 11 canonical patterns (evaluation order, label correctness)
  - Pattern ordering invariant: payment card (10) before long-token catch-all (11)
  - build_redacted_transcript() integration
"""
import pytest
from app.voice.redaction import (
    RedactionResult,
    _PATTERNS,
    build_redacted_transcript,
    redact_and_flag,
    redact_sensitive_text,
)


# ── RedactionResult dataclass ─────────────────────────────────────────────────

def test_redaction_result_is_frozen():
    r = RedactionResult(text="hello", was_redacted=False)
    with pytest.raises((AttributeError, TypeError)):
        r.text = "changed"  # type: ignore[misc]


def test_redaction_result_fields():
    r = RedactionResult(text="abc", was_redacted=True)
    assert r.text == "abc"
    assert r.was_redacted is True


def test_redact_and_flag_no_match_returns_false():
    r = redact_and_flag("This is normal prose with no secrets.")
    assert r.was_redacted is False
    assert r.text == "This is normal prose with no secrets."


def test_redact_and_flag_match_returns_true():
    r = redact_and_flag("email me at user@example.com")
    assert r.was_redacted is True
    assert "[REDACTED_EMAIL]" in r.text


def test_redact_and_flag_empty_string():
    r = redact_and_flag("")
    assert r.text == ""
    assert r.was_redacted is False


def test_redact_and_flag_text_equals_redact_sensitive_text():
    inputs = [
        "sk-abcdefghijklmnopqrstu",
        "send to user@example.com",
        "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9token",
        "normal prose",
    ]
    for text in inputs:
        assert redact_and_flag(text).text == redact_sensitive_text(text)


# ── redact_sensitive_text() backward-compat wrapper ───────────────────────────

def test_redact_sensitive_text_returns_str():
    result = redact_sensitive_text("hello world")
    assert isinstance(result, str)


def test_redact_sensitive_text_no_change_for_clean_text():
    assert redact_sensitive_text("Hello, how are you?") == "Hello, how are you?"


# ── Pattern 1: PEM private key ────────────────────────────────────────────────

def test_pattern_private_key():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PRIVATE_KEY]" in result
    assert "PRIVATE KEY-----" not in result.replace("[REDACTED_PRIVATE_KEY]", "")


def test_pattern_private_key_ec():
    text = "-----BEGIN EC PRIVATE KEY-----\ndata\n-----END EC PRIVATE KEY-----"
    assert "[REDACTED_PRIVATE_KEY]" in redact_sensitive_text(text)


# ── Pattern 2: API key (sk- / sk-proj-) ──────────────────────────────────────

def test_pattern_api_key_sk():
    text = "my key is sk-abcdefghijklmnopqrstuvwxyz12345"
    result = redact_sensitive_text(text)
    assert "[REDACTED_API_KEY]" in result
    assert "sk-abcdefghijklmnopqrstuvwxyz12345" not in result


def test_pattern_api_key_sk_proj():
    text = "key=sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    result = redact_sensitive_text(text)
    assert "[REDACTED_API_KEY]" in result


def test_pattern_api_key_too_short_not_redacted():
    text = "sk-short"
    result = redact_sensitive_text(text)
    assert "[REDACTED_API_KEY]" not in result


# ── Pattern 3: Bearer token ───────────────────────────────────────────────────

def test_pattern_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
    result = redact_sensitive_text(text)
    assert "[REDACTED_TOKEN]" in result
    assert "Bearer" not in result


def test_pattern_bearer_token_case_insensitive():
    text = "authorization: bearer AAABBBCCCDDDEEEFFFGGG"
    result = redact_sensitive_text(text)
    assert "[REDACTED_TOKEN]" in result


# ── Pattern 4: password= / passwd= / pwd= ────────────────────────────────────

def test_pattern_password():
    text = "password=SuperSecret123"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PASSWORD]" in result
    assert "SuperSecret123" not in result


def test_pattern_passwd():
    text = "passwd: MyP@ssw0rd"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PASSWORD]" in result


def test_pattern_pwd():
    text = "connection: host=db.example.com pwd=s3cr3t"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PASSWORD]" in result


# ── Pattern 5: access/refresh/id/api token key=value ─────────────────────────

def test_pattern_access_token():
    text = "access_token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9payload"
    result = redact_sensitive_text(text)
    assert "[REDACTED_TOKEN]" in result


def test_pattern_refresh_token():
    text = "refresh_token=abcdefghijklmnopqrstuvwxyz1234"
    result = redact_sensitive_text(text)
    assert "[REDACTED_TOKEN]" in result


def test_pattern_api_token():
    text = "api_token=AAAABBBBCCCCDDDDEEEE1234"
    result = redact_sensitive_text(text)
    assert "[REDACTED_TOKEN]" in result


# ── Pattern 6: secret= / client_secret= / api_secret= ────────────────────────

def test_pattern_secret():
    text = "secret=mysupersecretvalue123456"
    result = redact_sensitive_text(text)
    assert "[REDACTED_SECRET]" in result


def test_pattern_client_secret():
    text = "client_secret=abcdefghijklmnopqrstuvwxyz"
    result = redact_sensitive_text(text)
    assert "[REDACTED_SECRET]" in result


def test_pattern_api_secret():
    text = "api_secret=XXXXXXXXXXXXXXXXXXXXXXXXXXX"
    result = redact_sensitive_text(text)
    assert "[REDACTED_SECRET]" in result


# ── Pattern 7: email address ──────────────────────────────────────────────────

def test_pattern_email():
    text = "contact us at support@example.com for help"
    result = redact_sensitive_text(text)
    assert "[REDACTED_EMAIL]" in result
    assert "support@example.com" not in result


def test_pattern_email_uppercase_domain():
    text = "ADMIN@COMPANY.ORG"
    result = redact_sensitive_text(text)
    assert "[REDACTED_EMAIL]" in result


# ── Pattern 8: US SSN ─────────────────────────────────────────────────────────

def test_pattern_ssn():
    text = "SSN: 123-45-6789"
    result = redact_sensitive_text(text)
    assert "[REDACTED_SSN]" in result
    assert "123-45-6789" not in result


def test_pattern_ssn_label_not_gov_id():
    """Backend canonical label is [REDACTED_SSN], NOT [REDACTED_GOV_ID]."""
    text = "SSN: 987-65-4321"
    result = redact_sensitive_text(text)
    assert "[REDACTED_GOV_ID]" not in result
    assert "[REDACTED_SSN]" in result


# ── Pattern 9: US phone number ────────────────────────────────────────────────

def test_pattern_phone_dashes():
    text = "call me at 555-867-5309"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PHONE]" in result
    assert "555-867-5309" not in result


def test_pattern_phone_with_country_code():
    text = "reach me at +1 800 555 1234"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PHONE]" in result


def test_pattern_phone_parentheses():
    text = "phone: (415) 555-2671"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PHONE]" in result


# ── Pattern 10: Payment card ──────────────────────────────────────────────────

def test_pattern_payment_card_16_digits():
    text = "card: 4111 1111 1111 1111"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PAYMENT_CARD]" in result
    assert "4111" not in result


def test_pattern_payment_card_no_spaces():
    text = "card=4111111111111111"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PAYMENT_CARD]" in result


# ── Pattern 11: Long opaque token catch-all ───────────────────────────────────

def test_pattern_long_token_catch_all():
    text = "token: abcdefghijklmnopqrstuvwxyzABCDEFGH"
    result = redact_sensitive_text(text)
    assert "[REDACTED_SECRET]" in result


# ── Ordering invariant: payment card before long-token catch-all ──────────────

def test_ordering_payment_card_before_catch_all():
    """A 16-digit card number must receive [REDACTED_PAYMENT_CARD], not [REDACTED_SECRET]."""
    text = "4111111111111111"
    result = redact_sensitive_text(text)
    assert "[REDACTED_PAYMENT_CARD]" in result
    assert "[REDACTED_SECRET]" not in result


def test_pattern_count():
    """Canonical pattern count is 11 — alert if accidentally added or removed."""
    assert len(_PATTERNS) == 11


# ── Non-sensitive text passthrough ────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "What is the remote work policy?",
    "Hello, how can I help you today?",
    "The meeting is at 3pm on Tuesday.",
    "Paris is the capital of France.",
    "",
])
def test_no_false_positives(text: str):
    assert redact_sensitive_text(text) == text


# ── build_redacted_transcript ─────────────────────────────────────────────────

def test_build_redacted_transcript_redacts_content():
    messages = [("user", "email me at secret@example.com"), ("assistant", "OK")]
    transcript = build_redacted_transcript(messages)
    assert "[REDACTED_EMAIL]" in transcript
    assert "secret@example.com" not in transcript


def test_build_redacted_transcript_skips_empty_content():
    messages = [("user", "   "), ("assistant", "Hello")]
    transcript = build_redacted_transcript(messages)
    assert "User:" not in transcript
    assert "Assistant: Hello" in transcript


def test_build_redacted_transcript_formats_roles():
    messages = [("user", "hi"), ("assistant", "hello")]
    transcript = build_redacted_transcript(messages)
    assert transcript.startswith("User: hi")
    assert "Assistant: hello" in transcript
