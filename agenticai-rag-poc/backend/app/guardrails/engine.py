"""Guardrail engine — evaluates text against configured rules.

Processing order:
  1. Block rules  — short-circuit; allowed=False, return immediately.
  2. Redact rules — modify the text in-place.
  3. Flag rules   — set flagged=True, accumulate violations.

OWASP A03: User-supplied regex patterns are already validated at rule-creation
           time (see store.add_rule). Engine uses re.error-safe compilation.
OWASP A09: All violations are returned to the caller for logging; nothing is
           silently swallowed here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Module-level compiled pattern cache — avoids re.compile on every rule evaluation.
_compiled_patterns: dict[str, re.Pattern[str]] = {}


def _get_compiled(pattern: str) -> re.Pattern[str] | None:
    """Return a cached compiled regex, or None if pattern is invalid."""
    if pattern not in _compiled_patterns:
        try:
            _compiled_patterns[pattern] = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return None
    return _compiled_patterns[pattern]


@dataclass
class GuardrailViolation:
    """A single rule violation encountered during a check."""

    rule_id: str
    rule_name: str
    action: str    # "block" | "flag" | "redact"
    severity: str  # "low" | "medium" | "high"


@dataclass
class GuardrailResult:
    """Result of evaluating text through the guardrail engine."""

    allowed: bool          # False if any "block" action fired
    modified_text: str     # original text or redacted version
    violations: list[GuardrailViolation] = field(default_factory=list)
    flagged: bool = False  # True if any "flag" action fired


class GuardrailEngine:
    """Stateless engine that evaluates text against the guardrail rule store.

    Import ``get_guardrail_store`` lazily inside :meth:`check` to avoid
    circular-import issues at module load time.
    """

    # ── Matching helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _matches_word(rule_words: list[str], text: str) -> bool:
        for word in rule_words:
            if re.search(r"\b" + re.escape(word) + r"\b", text, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _matches_topic(keywords: list[str], text: str) -> bool:
        lower = text.lower()
        return any(kw.lower() in lower for kw in keywords)

    @staticmethod
    def _matches_regex(pattern: str, text: str) -> bool:
        compiled = _get_compiled(pattern)
        return bool(compiled.search(text)) if compiled is not None else False

    @staticmethod
    def _apply_redact(pattern: str, replacement: str, text: str) -> str:
        compiled = _get_compiled(pattern)
        return compiled.sub(replacement, text) if compiled is not None else text

    # ── Rule applicability ────────────────────────────────────────────────────

    @staticmethod
    def _rule_applies_to_target(rule_target: str, check_target: str) -> bool:
        """Return True if this rule should be evaluated for the given target."""
        return rule_target in (check_target, "both")

    # ── Match dispatcher ──────────────────────────────────────────────────────

    def _rule_matches(self, rule, text: str) -> bool:
        if rule.type == "word":
            return self._matches_word(rule.words, text)
        if rule.type == "topic":
            return self._matches_topic(rule.keywords, text)
        if rule.type == "regex":
            return self._matches_regex(rule.pattern, text)
        return False

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, text: str, target: str) -> GuardrailResult:
        """Check *text* against all enabled rules that match *target*.

        Args:
            text:   The text to evaluate.
            target: ``"input"`` or ``"output"``.

        Returns:
            A :class:`GuardrailResult` with the (possibly redacted) text,
            violation list, ``allowed`` flag, and ``flagged`` flag.
        """
        # Lazy import to avoid circular imports at module load time.
        from app.guardrails.store import get_guardrail_store

        store = get_guardrail_store()
        all_rules = store.list_rules()

        enabled_applicable = [
            r for r in all_rules
            if r.enabled and self._rule_applies_to_target(r.target, target)
        ]

        violations: list[GuardrailViolation] = []
        modified_text = text
        flagged = False

        # ── Pass 1: Block rules (short-circuit) ───────────────────────────────
        for rule in enabled_applicable:
            if rule.action != "block":
                continue
            if self._rule_matches(rule, modified_text):
                violations.append(GuardrailViolation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action="block",
                    severity=rule.severity,
                ))
                return GuardrailResult(
                    allowed=False,
                    modified_text=modified_text,
                    violations=violations,
                    flagged=flagged,
                )

        # ── Pass 2: Redact rules (accumulate) ────────────────────────────────
        for rule in enabled_applicable:
            if rule.action != "redact":
                continue
            if self._rule_matches(rule, modified_text):
                violations.append(GuardrailViolation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action="redact",
                    severity=rule.severity,
                ))
                if rule.type == "regex" and rule.pattern:
                    modified_text = self._apply_redact(rule.pattern, rule.replacement, modified_text)

        # ── Pass 3: Flag rules ────────────────────────────────────────────────
        for rule in enabled_applicable:
            if rule.action != "flag":
                continue
            if self._rule_matches(rule, modified_text):
                violations.append(GuardrailViolation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action="flag",
                    severity=rule.severity,
                ))
                flagged = True

        return GuardrailResult(
            allowed=True,
            modified_text=modified_text,
            violations=violations,
            flagged=flagged,
        )
