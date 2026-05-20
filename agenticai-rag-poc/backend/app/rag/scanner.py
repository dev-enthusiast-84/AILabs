"""
Virus/malware scanning and stored-injection prevention for uploaded files.

Scanning layers (defence-in-depth, OWASP A04 / A03):
  1. ZIP bomb detection — rejects archives with extreme compression ratios.
  2. ClamAV scan — optional; set CLAMAV_HOST env var and run a clamd daemon.
     Skips gracefully (warning log) when ClamAV is unavailable so development
     flows are unaffected.
  3. Stored-injection scan — checks extracted document text for prompt-injection
     patterns before the text is written to the vector store (indirect/stored
     prompt injection, OWASP A03).
"""
import io
import logging
import os
import re
import zipfile
from typing import Optional

log = logging.getLogger(__name__)

_ZIP_BOMB_RATIO = 50          # max uncompressed/compressed ratio
_ZIP_BOMB_MAX_BYTES = 50 * 1024 * 1024  # 50 MB uncompressed cap

# Patterns that indicate an attempt to hijack LLM behaviour from document content.
# Kept broad — a false positive is preferable to a missed stored-injection attack.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"forget\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+a?\s*[\w\s]{1,30}assistant", re.I),
    re.compile(r"\[\[?SYSTEM\]?\]", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"print\s+your\s+(system\s+)?prompt", re.I),
    re.compile(r"reveal\s+your\s+(system\s+)?prompt", re.I),
    re.compile(r"output\s+your\s+(system\s+)?instructions", re.I),
    re.compile(r"new\s+instructions?\s*:", re.I),
    re.compile(r"<\s*INST\s*>", re.I),  # Llama-style instruction tags
]


def check_zip_bomb(content: bytes) -> None:
    """Reject ZIP-based archives whose uncompressed size or ratio is extreme."""
    if content[:4] != b"PK\x03\x04":
        return
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            if total_uncompressed > _ZIP_BOMB_MAX_BYTES:
                raise ValueError(
                    f"Archive uncompressed size ({total_uncompressed // (1024 * 1024)} MB) "
                    f"exceeds the {_ZIP_BOMB_MAX_BYTES // (1024 * 1024)} MB safety limit."
                )
            if len(content) > 0 and (total_uncompressed / len(content)) > _ZIP_BOMB_RATIO:
                raise ValueError(
                    f"Archive compression ratio ({total_uncompressed / len(content):.0f}×) "
                    f"exceeds the {_ZIP_BOMB_RATIO}× safety limit. Upload rejected."
                )
    except zipfile.BadZipFile:
        raise ValueError("Archive is corrupt or not a valid ZIP/XLSX file.")


def scan_with_clamav(filename: str, content: bytes) -> None:
    """Scan file bytes with ClamAV daemon when CLAMAV_HOST is configured.

    Skips silently when CLAMAV_HOST is not set or the daemon is unreachable.
    Raises ValueError on virus detection.

    OWASP A04 — additional AV layer on top of magic-byte/executable checks.
    """
    host = os.environ.get("CLAMAV_HOST", "")
    if not host:
        return

    port = int(os.environ.get("CLAMAV_PORT", "3310"))
    try:
        import clamd  # lazy import — optional dependency
        cd = clamd.ClamdNetworkSocket(host=host, port=port, timeout=10)
        result = cd.instream(io.BytesIO(content))
        status, virus_name = result.get("stream", ("OK", None))
        if status == "FOUND":
            raise ValueError(
                f"Virus/malware detected in '{filename}': {virus_name}. Upload rejected."
            )
    except ImportError:
        log.warning("clamd package not installed — ClamAV scan skipped for '%s'", filename)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        log.warning(
            "ClamAV unavailable for '%s': %s — proceeding without AV scan", filename, exc
        )


def check_stored_injection(filename: str, text: str) -> None:
    """Reject extracted text that contains prompt-injection patterns.

    Prevents attackers from embedding LLM instruction overrides inside uploaded
    documents (indirect / stored prompt injection, OWASP A03).
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise ValueError(
                f"Document '{filename}' contains content resembling a prompt-injection "
                "attack and cannot be indexed. Remove the suspicious text and re-upload."
            )


def scan_upload(filename: str, content: bytes, extracted_text: Optional[str] = None) -> None:
    """Run all scanning layers on an uploaded file.

    1. ZIP bomb check (fast, always runs on ZIP/XLSX files)
    2. ClamAV scan (only when CLAMAV_HOST env var is set)
    3. Stored injection check (only when extracted_text is provided)
    """
    check_zip_bomb(content)
    scan_with_clamav(filename, content)
    if extracted_text is not None:
        check_stored_injection(filename, extracted_text)
