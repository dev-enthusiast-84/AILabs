#!/usr/bin/env bash
# spec-check.sh — CI spec compliance validator for Spec-Kit (SDD)
#
# Usage:
#   bash .specify/scripts/bash/spec-check.sh
#   make spec-check
#
# To make executable (one-time):
#   chmod +x .specify/scripts/bash/spec-check.sh
#
# Exit codes:
#   0 — all specs are valid
#   1 — one or more specs are missing or contain unresolved placeholders
#
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Locate repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SPECS_DIR="$REPO_ROOT/.specify/specs"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

# Only emit colour when writing to a real terminal
if [[ ! -t 1 ]]; then
  RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

# ── Placeholder patterns that indicate an unresolved template ─────────────────
# Matches tokens like [FEATURE NAME], [DATE], [Brief Title], etc.
PLACEHOLDER_PATTERN='\[FEATURE NAME\]\|\[DATE\]\|\[Brief Title\]\|\[Describe this user journey\]\|\[ALL_CAPS_IDENTIFIER\]\|\[NEEDS CLARIFICATION\]\|ACTION REQUIRED.*placeholder'

# ── Counters ──────────────────────────────────────────────────────────────────
TOTAL=0
MISSING_SPEC=0
PLACEHOLDER_SPEC=0
VALID=0

declare -a ERRORS=()

# ── Guard: no specs directory ─────────────────────────────────────────────────
if [[ ! -d "$SPECS_DIR" ]]; then
  echo -e "${YELLOW}Warning:${NC} No specs directory found at ${CYAN}$SPECS_DIR${NC}"
  echo "  Create feature specs with: /speckit-specify [feature-name] inside a Claude Code session"
  echo ""
  echo -e "${GREEN}Result: 0 specs found — nothing to validate.${NC}"
  exit 0
fi

# ── Main validation loop ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Spec-Kit — Spec Compliance Check${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  Scanning: ${CYAN}${SPECS_DIR/$REPO_ROOT\//}${NC}"
echo ""

for spec_dir in "$SPECS_DIR"/*/; do
  # Skip if glob matched nothing (empty directory)
  [[ -d "$spec_dir" ]] || continue

  feature_name="$(basename "$spec_dir")"
  spec_file="$spec_dir/spec.md"
  TOTAL=$(( TOTAL + 1 ))

  # ── Check 1: spec.md must exist ─────────────────────────────────────────
  if [[ ! -f "$spec_file" ]]; then
    MISSING_SPEC=$(( MISSING_SPEC + 1 ))
    ERRORS+=("MISSING  [$feature_name] spec.md not found in .specify/specs/$feature_name/")
    echo -e "  ${RED}✗ MISSING${NC}  $feature_name"
    echo -e "            spec.md not found — run /speckit-specify to generate it"
    continue
  fi

  # ── Check 2: spec.md must not contain unresolved template placeholders ───
  if grep -qE '\[FEATURE NAME\]|\[DATE\]|\[Brief Title\]|\[Describe this user journey\]|\[ALL_CAPS_IDENTIFIER\]' "$spec_file" 2>/dev/null; then
    PLACEHOLDER_SPEC=$(( PLACEHOLDER_SPEC + 1 ))
    first_placeholder=$(grep -Em1 '\[FEATURE NAME\]|\[DATE\]|\[Brief Title\]|\[Describe this user journey\]|\[ALL_CAPS_IDENTIFIER\]' "$spec_file" | head -c 80)
    ERRORS+=("TEMPLATE [$feature_name] spec.md still contains placeholder text: $first_placeholder")
    echo -e "  ${YELLOW}⚠ TEMPLATE${NC} $feature_name"
    echo -e "            spec.md has unresolved placeholders (e.g. '${first_placeholder}')"
    continue
  fi

  # ── All checks passed ────────────────────────────────────────────────────
  VALID=$(( VALID + 1 ))
  echo -e "  ${GREEN}✓ VALID${NC}    $feature_name"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$TOTAL" -eq 0 ]]; then
  echo -e "${GREEN}Result: No feature specs found under .specify/specs/ — nothing to validate.${NC}"
  echo "  Tip: create your first spec with /speckit-specify inside a Claude Code session."
  exit 0
fi

FAILED=$(( MISSING_SPEC + PLACEHOLDER_SPEC ))

echo -e "  Total specs scanned : ${BOLD}$TOTAL${NC}"
echo -e "  Valid               : ${GREEN}$VALID${NC}"
echo -e "  Missing spec.md     : ${RED}$MISSING_SPEC${NC}"
echo -e "  Unresolved template : ${YELLOW}$PLACEHOLDER_SPEC${NC}"
echo ""

if [[ "$FAILED" -gt 0 ]]; then
  echo -e "${RED}${BOLD}FAILED${NC} — $FAILED spec(s) require attention:"
  echo ""
  for err in "${ERRORS[@]}"; do
    echo -e "  ${RED}•${NC} $err"
  done
  echo ""
  echo "  Remediation:"
  echo "  • Missing spec.md   → Run /speckit-specify [feature-name] in a Claude Code session"
  echo "  • Template placeholders → Edit the spec.md and replace all [BRACKETED] tokens"
  echo ""
  exit 1
else
  echo -e "${GREEN}${BOLD}PASSED${NC} — all $TOTAL spec(s) are valid."
  echo ""
  exit 0
fi
