"""Input validation and safety guardrails — OWASP A03, A04."""
import re
import unicodedata
import bleach
from fastapi import HTTPException, status

from app.config import get_settings

settings = get_settings()

# Patterns for prompt injection attempts
_INJECTION_PATTERNS = [
    r"ignore (all |previous |above )?instructions",
    r"you are now",
    r"act as (a )?",
    r"disregard (your |all )?",
    r"forget (everything|instructions)",
    r"system prompt",
    r"<\|.*?\|>",           # Instruction tokens
    r"\[INST\]",
    r"###\s*instruction",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Very basic harmful-content patterns
_HARMFUL_PATTERNS = [
    r"\b(synthesize|create|make|produce)\b.{0,30}\b(weapon|bomb|explosive|poison|drug)\b",
]
_HARMFUL_RE = re.compile("|".join(_HARMFUL_PATTERNS), re.IGNORECASE)


def sanitize_query(query: str) -> str:
    """Validate and sanitize user query."""
    if not query or not query.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query cannot be empty.")

    if len(query) > settings.max_query_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Query exceeds maximum length of {settings.max_query_length} characters.",
        )

    # Strip HTML tags (XSS prevention)
    clean = bleach.clean(query, tags=[], strip=True)

    if _INJECTION_RE.search(clean):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query contains disallowed patterns.",
        )

    if _HARMFUL_RE.search(clean):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query contains potentially harmful content.",
        )

    return clean.strip()


def validate_filename(filename: str) -> str:
    """Prevent path traversal — OWASP A01."""
    # NFC normalisation before regex: prevents NFD variant filenames bypassing
    # duplicate detection (e.g. résumé.txt NFC vs NFD are logically the same file).
    filename = unicodedata.normalize('NFC', filename)
    clean = re.sub(r"[^\w.\-]", "_", filename)
    if ".." in clean or clean.startswith("/"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid filename.")
    return clean
