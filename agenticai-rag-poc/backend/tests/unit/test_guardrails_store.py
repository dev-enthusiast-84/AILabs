"""Unit tests for GuardrailStore — CRUD, built-in seeding, and validation.

Covers:
  - Built-in rules are seeded on construction (count and specific IDs).
  - add_rule generates a UUID-backed rule and returns it.
  - get_rule returns the correct rule or None for an unknown ID.
  - update_rule partial-patches fields; restricts built-in rules to the
    'enabled' flag only; raises KeyError for unknown IDs.
  - delete_rule removes a user rule; raises ValueError for built-in rules
    and KeyError for unknown IDs.
  - list_rules returns all rules (built-in + custom) and supports
    target-based filtering.
  - Enabling and disabling a rule via update_rule reflects immediately.
"""
import uuid

import pytest

from app.guardrails.store import GuardrailRule, GuardrailStore

# ── Built-in seeding ───────────────────────────────────────────────────────────

_EXPECTED_BUILTIN_IDS = {
    "prompt-injection",
    "sql-injection",
    "input-pii-email",
    "input-profanity",
    "output-pii-email",
    "output-pii-phone",
    "output-ssn",
    "output-credit-card",
    "output-ai-disclaimer",
    "violence-harmful",
    "adult-content",
}


def test_builtin_rules_seeded_on_init():
    """A brand-new GuardrailStore must contain all 11 built-in rules."""
    store = GuardrailStore()
    rule_ids = {r.id for r in store.list_rules()}
    assert len(store.list_rules()) >= len(_EXPECTED_BUILTIN_IDS)
    assert _EXPECTED_BUILTIN_IDS.issubset(rule_ids)


def test_builtin_rule_count_at_least_eleven():
    """Store must seed at least 11 rules."""
    store = GuardrailStore()
    assert len(store.list_rules()) >= 11


def test_specific_builtin_ids_present():
    """Individual spot-check for each expected built-in rule ID."""
    store = GuardrailStore()
    for rule_id in _EXPECTED_BUILTIN_IDS:
        assert store.get_rule(rule_id) is not None, f"Missing built-in rule: {rule_id}"


def test_builtin_rules_are_marked_as_builtin():
    """All seeded rules must have builtin=True."""
    store = GuardrailStore()
    for rule in store.list_rules():
        if rule.id in _EXPECTED_BUILTIN_IDS:
            assert rule.builtin is True, f"Rule '{rule.id}' should be builtin=True"


# ── add_rule ───────────────────────────────────────────────────────────────────

def _make_custom_rule(**overrides) -> GuardrailRule:
    """Return a minimal valid user-defined GuardrailRule."""
    defaults = dict(
        id=str(uuid.uuid4()),
        name="Custom Rule",
        description="A test rule",
        type="word",
        target="input",
        action="block",
        severity="low",
        enabled=True,
        builtin=False,
        words=["testword"],
    )
    defaults.update(overrides)
    return GuardrailRule(**defaults)


def test_add_rule_returns_the_rule():
    """add_rule should return the rule object that was stored."""
    store = GuardrailStore()
    rule = _make_custom_rule()
    returned = store.add_rule(rule)
    assert returned is rule
    assert returned.id == rule.id
    assert returned.name == "Custom Rule"


def test_add_rule_is_retrievable_by_id():
    """A rule added via add_rule must be accessible through get_rule."""
    store = GuardrailStore()
    rule = _make_custom_rule()
    store.add_rule(rule)
    retrieved = store.get_rule(rule.id)
    assert retrieved is not None
    assert retrieved.id == rule.id


def test_add_rule_duplicate_id_raises():
    """Adding a rule whose ID already exists must raise ValueError."""
    store = GuardrailStore()
    rule = _make_custom_rule()
    store.add_rule(rule)
    with pytest.raises(ValueError, match="already exists"):
        store.add_rule(rule)


def test_add_rule_invalid_regex_raises():
    """A regex-type rule with a syntactically invalid pattern must raise ValueError."""
    store = GuardrailStore()
    rule = _make_custom_rule(type="regex", pattern="[invalid(regex", words=[])
    with pytest.raises(ValueError, match="Invalid regex"):
        store.add_rule(rule)


def test_add_rule_valid_regex_succeeds():
    """A regex-type rule with a valid pattern must be accepted."""
    store = GuardrailStore()
    rule = _make_custom_rule(type="regex", pattern=r"\d{3}-\d{2}-\d{4}", words=[])
    returned = store.add_rule(rule)
    assert returned.pattern == r"\d{3}-\d{2}-\d{4}"


# ── get_rule ───────────────────────────────────────────────────────────────────

def test_get_rule_unknown_id_returns_none():
    """get_rule with a nonexistent ID must return None (not raise)."""
    store = GuardrailStore()
    result = store.get_rule("definitely-does-not-exist-" + str(uuid.uuid4()))
    assert result is None


def test_get_rule_builtin_returns_rule():
    """get_rule with a known built-in ID returns the expected rule."""
    store = GuardrailStore()
    rule = store.get_rule("prompt-injection")
    assert rule is not None
    assert rule.id == "prompt-injection"
    assert rule.builtin is True


# ── update_rule ────────────────────────────────────────────────────────────────

def test_update_rule_patches_custom_field():
    """update_rule on a user rule must patch the requested field."""
    store = GuardrailStore()
    rule = _make_custom_rule(name="Original Name")
    store.add_rule(rule)
    updated = store.update_rule(rule.id, name="Updated Name")
    assert updated.name == "Updated Name"
    # Verify persistence
    assert store.get_rule(rule.id).name == "Updated Name"


def test_update_rule_enable_builtin():
    """update_rule(enabled=True) must work on a built-in rule."""
    store = GuardrailStore()
    # input-profanity starts disabled
    store.update_rule("input-profanity", enabled=True)
    assert store.get_rule("input-profanity").enabled is True


def test_update_rule_disable_builtin():
    """update_rule(enabled=False) must work on a built-in rule."""
    store = GuardrailStore()
    store.update_rule("prompt-injection", enabled=False)
    assert store.get_rule("prompt-injection").enabled is False
    # Restore for other tests
    store.update_rule("prompt-injection", enabled=True)


def test_update_rule_non_enabled_field_on_builtin_raises():
    """Patching a non-'enabled' field on a built-in rule must raise ValueError."""
    store = GuardrailStore()
    with pytest.raises(ValueError, match="only allows 'enabled'"):
        store.update_rule("prompt-injection", name="Hacked")


def test_update_rule_unknown_id_raises_key_error():
    """update_rule on a non-existent rule ID must raise KeyError."""
    store = GuardrailStore()
    with pytest.raises(KeyError):
        store.update_rule("non-existent-rule-xyz", enabled=True)


def test_update_rule_invalid_regex_raises():
    """update_rule with a bad regex pattern on a user rule must raise ValueError."""
    store = GuardrailStore()
    rule = _make_custom_rule(type="regex", pattern=r"\d+", words=[])
    store.add_rule(rule)
    with pytest.raises(ValueError, match="Invalid regex"):
        store.update_rule(rule.id, pattern="[broken(regex")


# ── delete_rule ────────────────────────────────────────────────────────────────

def test_delete_rule_removes_user_rule():
    """delete_rule must remove a user-defined rule from the store."""
    store = GuardrailStore()
    rule = _make_custom_rule()
    store.add_rule(rule)
    store.delete_rule(rule.id)
    assert store.get_rule(rule.id) is None


def test_delete_rule_builtin_raises_value_error():
    """Attempting to delete a built-in rule must raise ValueError."""
    store = GuardrailStore()
    with pytest.raises(ValueError, match="cannot be deleted"):
        store.delete_rule("prompt-injection")


def test_delete_rule_builtin_still_present_after_failed_delete():
    """Built-in rule must still be present after a failed delete attempt."""
    store = GuardrailStore()
    try:
        store.delete_rule("sql-injection")
    except ValueError:
        pass
    assert store.get_rule("sql-injection") is not None


def test_delete_rule_unknown_id_raises_key_error():
    """delete_rule on a non-existent ID must raise KeyError."""
    store = GuardrailStore()
    with pytest.raises(KeyError):
        store.delete_rule("this-does-not-exist")


# ── list_rules ─────────────────────────────────────────────────────────────────

def test_list_rules_includes_builtins_and_custom():
    """list_rules must return both built-in and user-defined rules."""
    store = GuardrailStore()
    rule = _make_custom_rule(name="My Custom Rule")
    store.add_rule(rule)
    all_rules = store.list_rules()
    rule_ids = {r.id for r in all_rules}
    assert rule.id in rule_ids
    assert "prompt-injection" in rule_ids


def test_list_rules_length_grows_after_add():
    """list_rules must reflect newly added rules."""
    store = GuardrailStore()
    before = len(store.list_rules())
    store.add_rule(_make_custom_rule())
    store.add_rule(_make_custom_rule())
    assert len(store.list_rules()) == before + 2


def test_list_rules_filtered_by_input_target():
    """list_rules(target='input') must return only input-targeted rules."""
    store = GuardrailStore()
    input_rules = store.list_rules(target="input")
    assert len(input_rules) > 0
    assert all(r.target == "input" for r in input_rules)


def test_list_rules_filtered_by_output_target():
    """list_rules(target='output') must return only output-targeted rules."""
    store = GuardrailStore()
    output_rules = store.list_rules(target="output")
    assert len(output_rules) > 0
    assert all(r.target == "output" for r in output_rules)


def test_list_rules_no_filter_larger_than_filtered():
    """Unfiltered list must include more rules than any single target filter."""
    store = GuardrailStore()
    all_rules = store.list_rules()
    input_rules = store.list_rules(target="input")
    output_rules = store.list_rules(target="output")
    assert len(all_rules) >= len(input_rules) + len(output_rules)


# ── Enable / disable toggle ────────────────────────────────────────────────────

def test_enable_disable_custom_rule_via_update():
    """Toggling enabled on a user rule must persist in the store."""
    store = GuardrailStore()
    rule = _make_custom_rule(enabled=True)
    store.add_rule(rule)

    store.update_rule(rule.id, enabled=False)
    assert store.get_rule(rule.id).enabled is False

    store.update_rule(rule.id, enabled=True)
    assert store.get_rule(rule.id).enabled is True


def test_enable_disable_builtin_rule_via_update():
    """Toggling enabled on a built-in rule must persist in the store."""
    store = GuardrailStore()
    # violence-harmful starts as disabled
    original_state = store.get_rule("violence-harmful").enabled

    store.update_rule("violence-harmful", enabled=True)
    assert store.get_rule("violence-harmful").enabled is True

    store.update_rule("violence-harmful", enabled=False)
    assert store.get_rule("violence-harmful").enabled is False

    # restore
    store.update_rule("violence-harmful", enabled=original_state)
