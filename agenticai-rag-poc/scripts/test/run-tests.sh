#!/usr/bin/env bash
# run-tests.sh — Run all backend unit/integration tests and frontend unit/E2E tests.
# Reports are generated in test-reports/ (not checked into git).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORTS="$ROOT/test-reports"
PASS=0
FAIL=0

mkdir -p "$REPORTS"

cyan()   { printf '\033[0;36m%s\033[0m\n' "$*"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
bold()   { printf '\033[1m%s\033[0m\n' "$*"; }

run_suite() {
  local name="$1"; shift
  cyan "▶ Running: $name"
  if "$@"; then
    green "✓ $name passed"
    ((PASS++)) || true
  else
    red "✗ $name failed"
    ((FAIL++)) || true
  fi
  echo ""
}

# ── Backend tests ──────────────────────────────────────────────────────────────
bold "=== BACKEND TESTS ==="
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
  cyan "Creating Python virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements-dev.txt

# Copy .env.example → .env for test run if .env doesn't exist
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "⚠  Created backend/.env from .env.example. Set OPENAI_API_KEY before running live tests."
fi

# ── Admin password: generate → inject into .env → export → clear on exit ───────
_ENV_FILE="$ROOT/backend/.env"
_PWD_INJECTED=false

_clear_admin_password() {
  if [[ "$_PWD_INJECTED" == "true" ]] && [[ -f "$_ENV_FILE" ]]; then
    sed -i '' 's|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=|' "$_ENV_FILE"
    green "✓ ADMIN_PASSWORD cleared from backend/.env"
  fi
}
trap _clear_admin_password EXIT

ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
export ADMIN_PASSWORD
if grep -q '^ADMIN_PASSWORD=' "$_ENV_FILE" 2>/dev/null; then
  sed -i '' "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASSWORD}|" "$_ENV_FILE"
else
  printf '\nADMIN_PASSWORD=%s\n' "$ADMIN_PASSWORD" >> "$_ENV_FILE"
fi
_PWD_INJECTED=true
cyan "✓ Auto-generated ADMIN_PASSWORD injected into backend/.env (cleared on exit)"

run_suite "Backend Unit Tests" python -m pytest tests/unit/ -v \
  --html="$REPORTS/backend-unit-report.html" \
  --self-contained-html \
  --no-header \
  -q

run_suite "Backend Integration Tests" python -m pytest tests/integration/ -v \
  --html="$REPORTS/backend-integration-report.html" \
  --self-contained-html \
  --no-header \
  -q

deactivate
cd "$ROOT"

# ── Frontend tests ─────────────────────────────────────────────────────────────
bold "=== FRONTEND TESTS ==="
cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
  cyan "Installing frontend dependencies..."
  npm ci
fi

run_suite "Frontend Unit Tests" npm run test -- \
  --reporter=verbose \
  --outputFile="$REPORTS/frontend-unit-report.json"

# E2E requires a running backend; skip in CI unless BACKEND_URL is set
if [ "${RUN_E2E:-false}" = "true" ]; then
  cyan "Installing Playwright browsers (first run)..."
  npx playwright install --with-deps chromium
  run_suite "Frontend E2E Tests" npm run test:e2e:report
else
  cyan "Skipping E2E tests (set RUN_E2E=true to include them)"
fi

cd "$ROOT"

# ── Summary ────────────────────────────────────────────────────────────────────
bold "=== TEST SUMMARY ==="
green "Passed: $PASS"
[ "$FAIL" -gt 0 ] && red "Failed: $FAIL" || echo "Failed: 0"

echo ""
bold "Reports written to: $REPORTS/"
echo "  backend-unit-report.html"
echo "  backend-integration-report.html"
echo "  frontend-unit-report.json"
[ "${RUN_E2E:-false}" = "true" ] && echo "  e2e-report/index.html"

echo ""
cyan "Open reports: open $REPORTS/backend-unit-report.html"

[ "$FAIL" -eq 0 ]
