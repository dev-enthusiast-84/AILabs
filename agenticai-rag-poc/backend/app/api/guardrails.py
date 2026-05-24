"""Guardrails management API — CRUD for configurable guardrail rules.

OWASP notes:
  A01 (Broken Access Control): All write operations (POST, PATCH, DELETE) require
      full-access (admin) tokens via require_full_access dependency.
  A03 (Injection): Regex patterns submitted by users are validated with re.compile
      at rule-creation and rule-update time; invalid patterns return HTTP 422.
  A09 (Security Logging): All violations from the /check endpoint are logged via
      structlog before returning the response.
"""
from __future__ import annotations

import re
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.utils import get_current_user, require_full_access
from app.guardrails.engine import GuardrailEngine
from app.guardrails.store import GuardrailRule, get_guardrail_store

log = structlog.get_logger()
router = APIRouter()
_engine = GuardrailEngine()


# ── Pydantic models ───────────────────────────────────────────────────────────

class GuardrailRuleResponse(BaseModel):
    id: str
    name: str
    description: str
    type: str
    target: str
    action: str
    severity: str
    enabled: bool
    builtin: bool
    words: list[str]
    keywords: list[str]
    pattern: str
    replacement: str


class GuardrailRuleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str = ""
    type: str = Field(..., pattern="^(word|topic|regex)$")
    target: str = Field(..., pattern="^(input|output|both)$")
    action: str = Field(..., pattern="^(block|flag|redact)$")
    severity: str = Field("medium", pattern="^(low|medium|high)$")
    enabled: bool = True
    words: list[str] = []
    keywords: list[str] = []
    pattern: str = ""
    replacement: str = "[REDACTED]"


class GuardrailRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    words: list[str] | None = None
    keywords: list[str] | None = None
    pattern: str | None = None
    replacement: str | None = None
    severity: str | None = None


class GuardrailCheckRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    target: str = Field(..., pattern="^(input|output|both)$")


class GuardrailCheckResponse(BaseModel):
    allowed: bool
    modified_text: str
    flagged: bool
    violations: list[dict]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(rule: GuardrailRule) -> GuardrailRuleResponse:
    return GuardrailRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        type=rule.type,
        target=rule.target,
        action=rule.action,
        severity=rule.severity,
        enabled=rule.enabled,
        builtin=rule.builtin,
        words=rule.words,
        keywords=rule.keywords,
        pattern=rule.pattern,
        replacement=rule.replacement,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[GuardrailRuleResponse])
async def list_rules(_user=Depends(get_current_user)):
    """List all guardrail rules. Available to any authenticated user."""
    store = get_guardrail_store()
    return [_to_response(r) for r in store.list_rules()]


@router.get("/{rule_id}", response_model=GuardrailRuleResponse)
async def get_rule(rule_id: str, _user=Depends(get_current_user)):
    """Get a single guardrail rule by ID. Available to any authenticated user."""
    store = get_guardrail_store()
    rule = store.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found.")
    return _to_response(rule)


@router.post("/", response_model=GuardrailRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(body: GuardrailRuleCreate, _user=Depends(require_full_access)):
    """Create a new user-defined guardrail rule. Admin only (A01).

    Validates regex patterns before persisting (A03).
    """
    if body.type == "regex" and body.pattern:
        try:
            re.compile(body.pattern)
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid regex pattern: {exc}",
            ) from exc

    rule = GuardrailRule(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        type=body.type,
        target=body.target,
        action=body.action,
        severity=body.severity,
        enabled=body.enabled,
        builtin=False,
        words=body.words,
        keywords=body.keywords,
        pattern=body.pattern,
        replacement=body.replacement,
    )

    store = get_guardrail_store()
    try:
        created = store.add_rule(rule)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    log.info("guardrail_rule_created", rule_id=created.id, name=created.name)
    return _to_response(created)


@router.patch("/{rule_id}", response_model=GuardrailRuleResponse)
async def update_rule(rule_id: str, body: GuardrailRuleUpdate, _user=Depends(require_full_access)):
    """Update an existing rule. Admin only (A01).

    Built-in rules may only have ``enabled`` patched.
    Validates updated regex patterns (A03).
    """
    if body.pattern is not None and body.pattern:
        try:
            re.compile(body.pattern)
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid regex pattern: {exc}",
            ) from exc

    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    store = get_guardrail_store()
    try:
        updated = store.update_rule(rule_id, **updates)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    log.info("guardrail_rule_updated", rule_id=rule_id, changes=list(updates.keys()))
    return _to_response(updated)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: str, _user=Depends(require_full_access)):
    """Delete a user-defined rule. Admin only (A01).

    Built-in rules cannot be deleted; returns HTTP 400.
    """
    store = get_guardrail_store()
    try:
        store.delete_rule(rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    log.info("guardrail_rule_deleted", rule_id=rule_id)


@router.post("/check", response_model=GuardrailCheckResponse)
async def check_text(body: GuardrailCheckRequest, _user=Depends(get_current_user)):
    """Test text against the active guardrail rules.

    Any authenticated user may use this endpoint.
    Violations are logged server-side (A09).
    """
    result = _engine.check(body.text, body.target)

    if result.violations:
        log.info(
            "guardrail_check_violations",
            target=body.target,
            allowed=result.allowed,
            flagged=result.flagged,
            violations=[
                {"rule_id": v.rule_id, "action": v.action, "severity": v.severity}
                for v in result.violations
            ],
        )

    return GuardrailCheckResponse(
        allowed=result.allowed,
        modified_text=result.modified_text,
        flagged=result.flagged,
        violations=[
            {
                "rule_id": v.rule_id,
                "rule_name": v.rule_name,
                "action": v.action,
                "severity": v.severity,
            }
            for v in result.violations
        ],
    )
