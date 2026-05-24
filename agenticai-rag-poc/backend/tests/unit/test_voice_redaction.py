import pytest

from app.voice.redaction import build_redacted_transcript, redact_sensitive_text


PRIVATE_KEY_FIXTURE = (
    "-----BEGIN " + "PRIVATE KEY-----\nabc123\n-----END " + "PRIVATE KEY-----"
)


def test_redact_sensitive_text_covers_required_secret_and_pii_types():
    text = (
        "email jane.doe@example.com phone 416-555-1212 ssn 123-45-6789 "
        "card 4111 1111 1111 1111 key " + "sk-proj-" + "A" * 32 + " "
        "Authorization: Bearer " + "b" * 32 + " password=hunter2 "
        "client_secret=abcdefghijklmnopqrstuvwxyz123456"
    )

    redacted = redact_sensitive_text(text)

    assert "jane.doe@example.com" not in redacted
    assert "416-555-1212" not in redacted
    assert "123-45-6789" not in redacted
    assert "4111 1111 1111 1111" not in redacted
    assert "sk-proj-" not in redacted
    assert "hunter2" not in redacted
    assert "b" * 32 not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_SSN]" in redacted
    assert "[REDACTED_PAYMENT_CARD]" in redacted
    assert "[REDACTED_API_KEY]" in redacted
    assert "[REDACTED_PASSWORD]" in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_build_redacted_transcript_preserves_order_and_roles():
    transcript = build_redacted_transcript(
        [
            ("user", "My email is jane@example.com"),
            ("assistant", "I will not repeat jane@example.com"),
        ]
    )

    assert transcript.split("\n\n") == [
        "User: My email is [REDACTED_EMAIL]",
        "Assistant: I will not repeat [REDACTED_EMAIL]",
    ]


@pytest.mark.parametrize(
    ("label", "secret"),
    [
        ("[REDACTED_PRIVATE_KEY]", PRIVATE_KEY_FIXTURE),
        ("[REDACTED_API_KEY]", "sk-" + "A" * 32),
        ("[REDACTED_API_KEY]", "sk-proj-" + "B" * 32),
        ("[REDACTED_TOKEN]", "Bearer " + "c" * 32),
        ("[REDACTED_TOKEN]", "refresh_token=" + "d" * 24),
        ("[REDACTED_TOKEN]", "api-token=" + "e" * 24),
        ("[REDACTED_SECRET]", "client_secret=" + "f" * 24),
        ("[REDACTED_PASSWORD]", "passwd=swordfish"),
        ("[REDACTED_EMAIL]", "jane.doe+demo@example.co.uk"),
        ("[REDACTED_PHONE]", "+1 (416) 555-1212"),
        ("[REDACTED_SSN]", "123-45-6789"),
        ("[REDACTED_PAYMENT_CARD]", "4111-1111-1111-1111"),
        ("[REDACTED_SECRET]", "a" * 40),
    ],
)
def test_redact_sensitive_text_fixture_matrix(label: str, secret: str):
    redacted = redact_sensitive_text(f"before {secret} after")

    assert secret not in redacted
    assert label in redacted


def test_build_redacted_transcript_applies_fixture_matrix_per_message():
    transcript = build_redacted_transcript(
        [
            ("user", "private key " + PRIVATE_KEY_FIXTURE),
            ("assistant", "use refresh_token=" + "r" * 24),
            ("user", "card 4111-1111-1111-1111 and jane.doe+demo@example.co.uk"),
        ]
    )

    assert PRIVATE_KEY_FIXTURE not in transcript
    assert "refresh_token=" not in transcript
    assert "4111-1111-1111-1111" not in transcript
    assert "jane.doe+demo@example.co.uk" not in transcript
    assert "[REDACTED_PRIVATE_KEY]" in transcript
    assert "[REDACTED_TOKEN]" in transcript
    assert "[REDACTED_PAYMENT_CARD]" in transcript
    assert "[REDACTED_EMAIL]" in transcript
