"""Tests for the shared chat language contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.chat_languages import CHAT_LANGUAGES, SUPPORTED_LANGUAGES


ROOT = Path(__file__).resolve().parents[3]


def _shared_languages() -> list[dict[str, str]]:
    return json.loads((ROOT / "shared" / "chat_languages.json").read_text(encoding="utf-8"))


def test_backend_chat_languages_match_shared_contract():
    expected = _shared_languages()

    assert list(CHAT_LANGUAGES) == expected
    assert SUPPORTED_LANGUAGES == {
        language["code"]: language["label"] for language in expected
    }


def test_generated_chat_language_contract_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_chat_languages.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
