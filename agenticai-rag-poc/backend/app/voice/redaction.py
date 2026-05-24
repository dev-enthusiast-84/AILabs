"""Best-effort redaction helpers for chat transcript and audio exports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RedactionPattern:
    label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RedactionResult:
    """Return type of :func:`redact_and_flag` — redacted text plus an occurrence flag."""

    text: str
    was_redacted: bool


_PATTERNS: tuple[RedactionPattern, ...] = (
    RedactionPattern(
        "[REDACTED_PRIVATE_KEY]",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    RedactionPattern(
        "[REDACTED_API_KEY]",
        re.compile(r"\bsk(?:-proj)?-[A-Za-z0-9_-]{20,}\b"),
    ),
    RedactionPattern(
        "[REDACTED_TOKEN]",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    ),
    RedactionPattern(
        "[REDACTED_PASSWORD]",
        re.compile(
            r"\b(password|passwd|pwd)\s*[:=]\s*([^\s,;]+)",
            re.IGNORECASE,
        ),
    ),
    RedactionPattern(
        "[REDACTED_TOKEN]",
        re.compile(
            r"\b(access[_-]?token|refresh[_-]?token|id[_-]?token|api[_-]?token)\s*[:=]\s*([A-Za-z0-9._~+/=-]{12,})",
            re.IGNORECASE,
        ),
    ),
    RedactionPattern(
        "[REDACTED_SECRET]",
        re.compile(
            r"\b(secret|client[_-]?secret|api[_-]?secret)\s*[:=]\s*([A-Za-z0-9._~+/=-]{12,})",
            re.IGNORECASE,
        ),
    ),
    RedactionPattern(
        "[REDACTED_EMAIL]",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    RedactionPattern(
        "[REDACTED_SSN]",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    RedactionPattern(
        "[REDACTED_PHONE]",
        re.compile(
            r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"
        ),
    ),
    RedactionPattern(
        "[REDACTED_PAYMENT_CARD]",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    ),
    RedactionPattern(
        "[REDACTED_SECRET]",
        re.compile(
            r"\b[A-Za-z0-9_-]{32,}\b",
        ),
    ),
)


def redact_and_flag(text: str) -> RedactionResult:
    """Return a :class:`RedactionResult` with redacted text and occurrence flag."""
    redacted = text
    for item in _PATTERNS:
        redacted = item.pattern.sub(item.label, redacted)
    return RedactionResult(text=redacted, was_redacted=redacted != text)


def redact_sensitive_text(text: str) -> str:
    """Return text with common secrets and PII replaced by readable labels."""
    return redact_and_flag(text).text


def build_redacted_transcript(messages: Iterable[tuple[str, str]]) -> str:
    """Build an ordered redacted chat transcript from ``(role, content)`` pairs."""
    lines: list[str] = []
    for role, content in messages:
        clean_role = role.strip().title() or "Message"
        clean_content = redact_sensitive_text(content.strip())
        if clean_content:
            lines.append(f"{clean_role}: {clean_content}")
    return "\n\n".join(lines)

