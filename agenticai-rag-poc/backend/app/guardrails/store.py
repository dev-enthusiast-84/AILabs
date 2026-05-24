"""Guardrail rule store — mutable singleton with built-in and user-defined rules.

OWASP A01: Builtin rules cannot be deleted, only toggled.
OWASP A03: Regex patterns are validated at add_rule time.
OWASP A09: Rule IDs are stable fixed strings for built-ins (not UUIDs) so audit
           logs referencing them remain meaningful across restarts.
"""
from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class GuardrailRule:
    """A single configurable guardrail rule."""

    id: str
    name: str
    description: str
    type: str           # "word" | "topic" | "regex"
    target: str         # "input" | "output" | "both"
    action: str         # "block" | "flag" | "redact"
    severity: str       # "low" | "medium" | "high"
    enabled: bool
    builtin: bool       # True = cannot be deleted, only toggled

    # type-specific (only one set will be used)
    words: list[str] = field(default_factory=list)       # word-type
    keywords: list[str] = field(default_factory=list)    # topic-type
    pattern: str = ""                                     # regex-type
    replacement: str = "[REDACTED]"                       # regex-type redact replacement


def _default_rules() -> list[GuardrailRule]:
    """Return all built-in default guardrail rules."""
    return [
        # ── Input rules ──────────────────────────────────────────────────────
        GuardrailRule(
            id="prompt-injection",
            name="Prompt Injection Block",
            description=(
                "Blocks queries that attempt to override system instructions "
                "via prompt injection techniques."
            ),
            type="regex",
            target="input",
            action="block",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=(
                r"(ignore\s+(all\s+)?(previous|above)?\s*instructions?"
                r"|you are now"
                r"|act as (a )?"
                r"|disregard (your |all )?"
                r"|forget (everything|instructions)"
                r"|system prompt"
                r"|\[INST\]"
                r"|###\s*instruction)"
            ),
            replacement="[REDACTED]",
        ),
        GuardrailRule(
            id="sql-injection",
            name="SQL Injection Block",
            description="Blocks queries containing SQL injection patterns.",
            type="regex",
            target="input",
            action="block",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=(
                r"(\bUNION\b.*\bSELECT\b"
                r"|\bDROP\b.*\bTABLE\b"
                r"|\bINSERT\b.*\bINTO\b"
                r"|\bDELETE\b.*\bFROM\b"
                r"|;\s*(DROP|ALTER|TRUNCATE))"
            ),
            replacement="[REDACTED]",
        ),
        GuardrailRule(
            id="input-pii-email",
            name="Input PII — Email Redact",
            description="Redacts email addresses from input queries (PII). Applies to text and voice inputs for both admin and guest.",
            type="regex",
            target="input",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            replacement="[EMAIL REDACTED]",
        ),
        GuardrailRule(
            id="input-pii-phone",
            name="Input PII — Phone Redact",
            description="Redacts phone numbers from input queries. Applies to text and voice inputs for both admin and guest.",
            type="regex",
            target="input",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=r"\b(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b",
            replacement="[PHONE REDACTED]",
        ),
        GuardrailRule(
            id="input-pii-ssn",
            name="Input PII — SSN Redact",
            description="Redacts US Social Security Numbers from input queries. Applies to text and voice inputs for both admin and guest.",
            type="regex",
            target="input",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b",
            replacement="[SSN REDACTED]",
        ),
        GuardrailRule(
            id="input-pci-card",
            name="Input PCI — Payment Card Redact",
            description="Redacts payment card numbers from input queries (PCI DSS compliance). Applies to text and voice inputs for both admin and guest.",
            type="regex",
            target="input",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=(
                r"\b(?:4[0-9]{12}(?:[0-9]{3})?"
                r"|5[1-5][0-9]{14}"
                r"|3[47][0-9]{13}"
                r"|3(?:0[0-5]|[68][0-9])[0-9]{11}"
                r"|6(?:011|5[0-9]{2})[0-9]{12})\b"
            ),
            replacement="[CARD REDACTED]",
        ),
        GuardrailRule(
            id="input-profanity",
            name="Input Profanity Block",
            description=(
                "Blocks input containing profanity. Disabled by default — "
                "enable and expand the word list to suit your audience."
            ),
            type="word",
            target="input",
            action="block",
            severity="medium",
            enabled=False,
            builtin=True,
            words=["damn", "crap", "hell", "ass", "bastard"],
        ),
        # ── Output rules ─────────────────────────────────────────────────────
        GuardrailRule(
            id="output-pii-email",
            name="Output PII — Email Redact",
            description="Redacts email addresses from LLM output to prevent PII leakage.",
            type="regex",
            target="output",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            replacement="[EMAIL REDACTED]",
        ),
        GuardrailRule(
            id="output-pii-phone",
            name="Output PII — Phone Redact",
            description="Redacts phone numbers from LLM output.",
            type="regex",
            target="output",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=r"\b(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b",
            replacement="[PHONE REDACTED]",
        ),
        GuardrailRule(
            id="output-ssn",
            name="Output PII — SSN Redact",
            description="Redacts US Social Security Numbers from LLM output.",
            type="regex",
            target="output",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b",
            replacement="[SSN REDACTED]",
        ),
        GuardrailRule(
            id="output-credit-card",
            name="Output PII — Credit Card Redact",
            description="Redacts credit card numbers from LLM output.",
            type="regex",
            target="output",
            action="redact",
            severity="high",
            enabled=True,
            builtin=True,
            pattern=(
                r"\b(?:4[0-9]{12}(?:[0-9]{3})?"
                r"|5[1-5][0-9]{14}"
                r"|3[47][0-9]{13}"
                r"|3(?:0[0-5]|[68][0-9])[0-9]{11}"
                r"|6(?:011|5[0-9]{2})[0-9]{12})\b"
            ),
            replacement="[CARD REDACTED]",
        ),
        GuardrailRule(
            id="output-ai-disclaimer",
            name="Output AI Self-Identification Flag",
            description=(
                "Flags output where the LLM identifies itself as an AI. "
                "Useful for auditing self-disclosure slip-throughs."
            ),
            type="regex",
            target="output",
            action="flag",
            severity="low",
            enabled=True,
            builtin=True,
            pattern=r"\b(as an AI|as a language model|I am an AI|I'm an AI)\b",
            replacement="[REDACTED]",
        ),
        # ── Both-direction rules ──────────────────────────────────────────────
        GuardrailRule(
            id="violence-harmful",
            name="Violence / Harmful Content Block",
            description=(
                "Blocks queries or outputs containing instructions for violence "
                "or the manufacture of weapons. Disabled by default."
            ),
            type="topic",
            target="both",
            action="block",
            severity="high",
            enabled=False,
            builtin=True,
            keywords=[
                "how to make a bomb",
                "how to synthesize",
                "weapons manufacture",
                "kill someone",
                "mass shooting",
                "terrorism instructions",
            ],
        ),
        GuardrailRule(
            id="adult-content",
            name="Adult Content Block",
            description=(
                "Blocks explicit adult content in queries and responses. "
                "Disabled by default."
            ),
            type="topic",
            target="both",
            action="block",
            severity="high",
            enabled=False,
            builtin=True,
            keywords=[
                "pornography",
                "explicit sexual",
                "child sexual",
            ],
        ),
    ]


class GuardrailStore:
    """Mutable in-memory store for guardrail rules.

    Holds both built-in rules (immutable except for the ``enabled`` toggle)
    and user-defined rules.  All public methods are thread-safe via RLock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, GuardrailRule] = {}
        for rule in _default_rules():
            self._rules[rule.id] = rule

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_rules(self, target: str | None = None) -> list[GuardrailRule]:
        """Return all rules, optionally filtered by target ('input'|'output'|'both')."""
        with self._lock:
            rules = list(self._rules.values())
        if target is not None:
            rules = [r for r in rules if r.target == target]
        return rules

    def get_rule(self, rule_id: str) -> GuardrailRule | None:
        """Return the rule with the given ID, or None if not found."""
        with self._lock:
            return self._rules.get(rule_id)

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_rule(self, rule: GuardrailRule) -> GuardrailRule:
        """Add a user-defined rule.

        Raises:
            ValueError: if the ID collides with an existing rule, or if the
                        regex pattern is syntactically invalid.
        """
        if rule.type == "regex" and rule.pattern:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {exc}") from exc
        with self._lock:
            if rule.id in self._rules:
                raise ValueError(f"Rule with ID '{rule.id}' already exists.")
            self._rules[rule.id] = rule
        return rule

    def update_rule(self, rule_id: str, **kwargs) -> GuardrailRule:
        """Patch fields on an existing rule.

        For built-in rules only the ``enabled`` field may be changed.

        Raises:
            KeyError: if the rule is not found.
            ValueError: if a non-permitted field is updated on a built-in rule,
                        or if the new regex pattern is syntactically invalid.
        """
        if "pattern" in kwargs and kwargs["pattern"]:
            try:
                re.compile(kwargs["pattern"])
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {exc}") from exc
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                raise KeyError(f"Rule '{rule_id}' not found.")
            if rule.builtin:
                disallowed = {k for k in kwargs if k != "enabled"}
                if disallowed:
                    raise ValueError(
                        f"Built-in rule '{rule_id}' only allows 'enabled' to be patched. "
                        f"Disallowed fields: {disallowed}"
                    )
            for k, v in kwargs.items():
                if hasattr(rule, k):
                    object.__setattr__(rule, k, v)
        return rule

    def delete_rule(self, rule_id: str) -> None:
        """Delete a user-defined rule.

        Raises:
            KeyError: if the rule is not found.
            ValueError: if the rule is a built-in.
        """
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                raise KeyError(f"Rule '{rule_id}' not found.")
            if rule.builtin:
                raise ValueError(f"Built-in rule '{rule_id}' cannot be deleted; toggle 'enabled' instead.")
            del self._rules[rule_id]


# ── Module-level singleton ────────────────────────────────────────────────────

_store: GuardrailStore | None = None


def get_guardrail_store() -> GuardrailStore:
    """Return the process-wide GuardrailStore singleton."""
    global _store
    if _store is None:
        _store = GuardrailStore()
    return _store
