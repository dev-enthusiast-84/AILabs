"""Unit tests for scripts/pre-commit secrets scanner.

The scanner is a standalone Python script; we import its helpers directly
by adding the scripts/ directory to sys.path temporarily.

No credentials are stored in this file.  Passwords required for scanner-pattern
tests are generated fresh each run via the Python `secrets` module and cleaned up
once the test module finishes.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import secrets
import sys
from pathlib import Path
from typing import Any

import pytest

# ── Bootstrap: load scripts/pre-commit as a module ────────────────────────────
# The script has no .py extension, so spec_from_file_location needs an explicit
# SourceFileLoader — the auto-detection path returns None for extensionless files.
SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
SCANNER_PATH = SCRIPTS_DIR / "pre-commit"


def _load_scanner() -> Any:
    loader = importlib.machinery.SourceFileLoader("pre_commit_scanner", str(SCANNER_PATH))
    spec = importlib.util.spec_from_loader("pre_commit_scanner", loader)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Python 3.13 dataclass looks up the module in sys.modules by __name__;
    # register before exec so @dataclass can resolve cls.__module__.
    sys.modules["pre_commit_scanner"] = mod
    loader.exec_module(mod)
    return mod


scanner = _load_scanner()


# ── Test credential generators ─────────────────────────────────────────────────
# Generated fresh each run — no credentials stored in source.
# Prefix choices are intentional: safe-marker tests need a value the scanner
# recognises as non-production; flagged tests need a value with no safe markers.

def _safe_admin_password() -> str:
    """Return a 20+ char password the scanner treats as safe ('TestPass' prefix)."""
    return f"TestPass_{secrets.token_hex(8)}"  # 25 chars; matches safe_pattern r'TestPass'


def _flagged_admin_password() -> str:
    """Return a 24-char hex password with no safe markers — scanner should flag it."""
    return secrets.token_hex(12)


def _safe_secret_key_value() -> str:
    """Return a non-hex string that cannot match the 64-char hex SECRET_KEY pattern."""
    # token_urlsafe uses base64 alphabet (A-Z a-z 0-9 - _) — always contains non-hex chars.
    return f"test-secret-{secrets.token_urlsafe(16)}-testing"


# ── Module-scoped fixture: generate + clean up ADMIN_PASSWORD env var ─────────

@pytest.fixture(scope="module", autouse=True)
def _admin_password_lifecycle():
    """Set ADMIN_PASSWORD to a generated value for the module; remove it on teardown."""
    key = "ADMIN_PASSWORD"
    original = os.environ.get(key)
    generated = _safe_admin_password()
    os.environ[key] = generated
    yield generated
    if original is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = original


# ── Helpers ───────────────────────────────────────────────────────────────────

def _findings(content: str) -> list[scanner.Finding]:
    """Run all rules against a single line of content, return findings."""
    findings: list[scanner.Finding] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        for rule in scanner.RULES:
            m = rule.pattern.search(line)
            if m is None:
                continue
            if any(sp.search(line) for sp in rule.safe_patterns):
                continue
            findings.append(
                scanner.Finding(
                    path="<test>",
                    line_no=line_no,
                    description=rule.description,
                    excerpt=scanner._redact(line.strip(), m),
                )
            )
    return findings


def _descriptions(content: str) -> list[str]:
    return [f.description for f in _findings(content)]


# ── OpenAI key detection ──────────────────────────────────────────────────────

class TestOpenAIKey:
    def test_real_key_standard_flagged(self):
        # 48 random chars after sk- → real key length
        key = "sk-" + "A" * 48
        assert "OpenAI API key" in _descriptions(f'OPENAI_API_KEY="{key}"')

    def test_real_key_project_scoped_flagged(self):
        key = "sk-proj-" + "B" * 60
        assert "OpenAI API key" in _descriptions(f"api_key = '{key}'")

    def test_short_placeholder_safe(self):
        # sk-test-key is only 11 chars total — must NOT be flagged
        assert "OpenAI API key" not in _descriptions('OPENAI_API_KEY="sk-test-key"')

    def test_safe_prefix_sk_fake_not_flagged(self):
        key = "sk-fake" + "X" * 50
        assert "OpenAI API key" not in _descriptions(f'key = "{key}"')

    def test_safe_prefix_sk_mock_not_flagged(self):
        key = "sk-mock" + "Y" * 50
        assert "OpenAI API key" not in _descriptions(f'key = "{key}"')

    def test_boundary_exactly_40_chars_flagged(self):
        key = "sk-" + "Z" * 40
        assert "OpenAI API key" in _descriptions(f'key="{key}"')

    def test_boundary_39_chars_not_flagged(self):
        key = "sk-" + "Z" * 39
        assert "OpenAI API key" not in _descriptions(f'key="{key}"')


# ── LangSmith key detection ───────────────────────────────────────────────────

class TestLangSmithKey:
    def test_real_ls_double_underscore_flagged(self):
        key = "ls__" + "a" * 30
        assert "LangSmith API key" in _descriptions(f'LANGCHAIN_API_KEY="{key}"')

    def test_real_lsv2_flagged(self):
        key = "lsv2_" + "b" * 30
        assert "LangSmith API key" in _descriptions(f'api_key="{key}"')

    def test_short_ls_not_flagged(self):
        # "ls__runtime-key" is only 15 chars and is a known safe placeholder
        assert "LangSmith API key" not in _descriptions('api_key="ls__runtime-key"')

    def test_boundary_25_chars_after_prefix_flagged(self):
        key = "ls__" + "c" * 25
        assert "LangSmith API key" in _descriptions(f'key="{key}"')

    def test_boundary_24_chars_after_prefix_not_flagged(self):
        key = "ls__" + "c" * 24
        assert "LangSmith API key" not in _descriptions(f'key="{key}"')


# ── Vercel Blob token detection ───────────────────────────────────────────────

class TestBlobToken:
    def test_real_blob_token_flagged(self):
        token = "vercel_blob_rw_" + "x" * 25
        assert "Vercel Blob read/write token" in _descriptions(f'BLOB_READ_WRITE_TOKEN="{token}"')

    def test_short_blob_not_flagged(self):
        token = "vercel_blob_rw_short"  # only 5 chars after prefix
        assert "Vercel Blob read/write token" not in _descriptions(f'token="{token}"')

    def test_case_insensitive(self):
        token = "VERCEL_BLOB_RW_" + "X" * 25
        assert "Vercel Blob read/write token" in _descriptions(f'TOKEN="{token}"')


# ── GitHub token detection ────────────────────────────────────────────────────

class TestGitHubToken:
    def test_ghp_token_flagged(self):
        token = "ghp_" + "A" * 36
        assert "GitHub token" in _descriptions(f'token = "{token}"')

    def test_gho_token_flagged(self):
        token = "gho_" + "B" * 36
        assert "GitHub token" in _descriptions(f'gh_token="{token}"')

    def test_short_ghp_not_flagged(self):
        token = "ghp_short"
        assert "GitHub token" not in _descriptions(f'token="{token}"')


# ── Pinecone key detection ────────────────────────────────────────────────────

class TestPineconeKey:
    def test_real_uuid_in_assignment_flagged(self):
        uuid = "12345678-abcd-4000-8000-abcdef012345"
        line = f'pinecone_api_key="{uuid}"'
        assert "Pinecone API key in assignment" in _descriptions(line)

    def test_fake_prefix_not_flagged(self):
        line = 'pinecone_api_key="pc-fake-key"'
        assert "Pinecone API key in assignment" not in _descriptions(line)

    def test_uuid_without_assignment_not_flagged(self):
        # Standalone UUID (e.g. in a log line) must NOT be flagged
        uuid = "12345678-abcd-4000-8000-abcdef012345"
        assert "Pinecone API key in assignment" not in _descriptions(uuid)


# ── SECRET_KEY detection ──────────────────────────────────────────────────────

class TestSecretKey:
    _DESC = "Hardcoded SECRET_KEY (64-char hex) in source"

    def test_64_char_hex_flagged(self):
        key = "a" * 64
        assert self._DESC in _descriptions(f'SECRET_KEY="{key}"')

    def test_short_test_value_not_flagged(self):
        # Generated value always contains non-hex chars (hyphens + base64 letters)
        # so it never matches the 64-char hex-only pattern.
        key = _safe_secret_key_value()
        assert self._DESC not in _descriptions(f'SECRET_KEY="{key}"')

    def test_non_hex_not_flagged(self):
        key = "z" * 64
        assert self._DESC not in _descriptions(f'SECRET_KEY="{key}"')

    def test_63_hex_chars_not_flagged(self):
        key = "a" * 63
        assert self._DESC not in _descriptions(f'SECRET_KEY="{key}"')


# ── ADMIN_PASSWORD detection ──────────────────────────────────────────────────

class TestAdminPassword:
    _DESC = "Hardcoded ADMIN_PASSWORD in source (non-test)"

    def test_long_password_in_source_flagged(self):
        # 24-char hex string, no safe markers → must be flagged
        pwd = _flagged_admin_password()
        assert self._DESC in _descriptions(f'ADMIN_PASSWORD="{pwd}"')

    def test_test_pass_not_flagged(self):
        # Generated password with 'TestPass' prefix → matches safe_pattern r'TestPass'
        pwd = _safe_admin_password()
        assert self._DESC not in _descriptions(f'ADMIN_PASSWORD="{pwd}"')

    def test_shell_substitution_not_flagged(self):
        assert self._DESC not in _descriptions(
            'ADMIN_PASSWORD="$(python3 -c \'import secrets; ...\')"'
        )

    def test_short_password_not_flagged(self):
        # Only triggered for 20+ char values
        assert self._DESC not in _descriptions(
            'ADMIN_PASSWORD="short"'
        )

    def test_placeholder_not_flagged(self):
        assert self._DESC not in _descriptions(
            'ADMIN_PASSWORD="<your-strong-password-here>"'
        )


# ── .env file blocking ────────────────────────────────────────────────────────

class TestEnvFileBlocking:
    def test_env_file_blocked(self):
        result = scanner.check_env_files(["backend/.env"])
        assert "backend/.env" in result

    def test_env_example_not_blocked(self):
        result = scanner.check_env_files(["backend/.env.example"])
        assert result == []

    def test_dotenv_in_subdir_blocked(self):
        result = scanner.check_env_files(["some/dir/.env"])
        assert len(result) == 1

    def test_non_env_file_not_blocked(self):
        result = scanner.check_env_files(["backend/app/config.py"])
        assert result == []

    def test_env_test_blocked(self):
        result = scanner.check_env_files([".env.test"])
        assert len(result) == 1


# ── Skip rules ────────────────────────────────────────────────────────────────

class TestSkipRules:
    def test_scanner_itself_skipped(self):
        findings = scanner.audit_file("scripts/pre-commit", ci_mode=True)
        assert findings == [], "The scanner script should not flag its own pattern strings"

    def test_env_example_skipped(self):
        findings = scanner.audit_file("backend/.env.example", ci_mode=True)
        assert findings == []

    def test_binary_extension_skipped(self):
        findings = scanner.audit_file("some/file.png", ci_mode=True)
        assert findings == []
