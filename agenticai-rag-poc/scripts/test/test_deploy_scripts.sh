#!/usr/bin/env bash
# tests/test_deploy_scripts.sh — Smoke tests for deploy/redeploy/undeploy Vercel scripts.
#
# These tests do NOT contact Vercel — they verify script structure, guard-clause
# behaviour, and environment-variable handling entirely locally.
#
# Usage:
#   bash tests/test_deploy_scripts.sh
#
# Exit code 0 = all tests passed; non-zero = at least one test failed.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY="$SCRIPT_DIR/scripts/remote/deploy-vercel.sh"
REDEPLOY="$SCRIPT_DIR/scripts/remote/redeploy-vercel.sh"
UNDEPLOY="$SCRIPT_DIR/scripts/remote/undeploy-vercel.sh"
WALKTHROUGH="$SCRIPT_DIR/scripts/record-walkthrough.sh"
VERCEL_JSON="$SCRIPT_DIR/frontend/vercel.json"

PASS=0
FAIL=0

# ── Helpers ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL + 1)); }

assert_exit_zero() {
    if [[ "$1" -eq 0 ]]; then pass "$2"; else fail "$2 (exit $1, expected 0)"; fi
}
assert_exit_nonzero() {
    if [[ "$1" -ne 0 ]]; then pass "$2"; else fail "$2 (exit $1, expected non-zero)"; fi
}
assert_contains() {
    # Use grep -- to prevent leading-dash strings being treated as flags (macOS BSD grep)
    if echo "$1" | grep -qF -- "$2"; then pass "$3"; else fail "$3 (expected '$2' in output)"; fi
}
assert_not_contains() {
    if echo "$1" | grep -qF -- "$2"; then fail "$3 (unexpected '$2' in output)"; else pass "$3"; fi
}

# Temporary bin dir used to simulate "vercel not installed":
# We symlink node (and other needed tools) but NOT vercel, so the scripts
# can still find node/python/curl while vercel appears absent.
_TMP_NO_VERCEL=$(mktemp -d)
_TMP_FAKE_REPO=$(mktemp -d)
for _tool in node npm python3 openssl curl sed grep awk; do
    _p=$(command -v "$_tool" 2>/dev/null)
    [[ -n "$_p" ]] && ln -sf "$_p" "$_TMP_NO_VERCEL/$_tool"
done
PATH_WITHOUT_VERCEL="$_TMP_NO_VERCEL:/usr/bin:/bin"
# Clean up at test exit
trap 'rm -rf "$_TMP_NO_VERCEL" "$_TMP_FAKE_REPO"' EXIT

echo ""
echo "=== deploy/redeploy/undeploy Vercel script smoke tests ==="
echo ""

# ── 1. Scripts exist and are executable ──────────────────────────────────────
echo "── 1. Script existence and permissions"
if [[ -f "$DEPLOY" ]];   then pass "deploy-vercel.sh exists";        else fail "deploy-vercel.sh not found at $DEPLOY"; fi
if [[ -x "$DEPLOY" ]];   then pass "deploy-vercel.sh is executable"; else fail "deploy-vercel.sh is not executable (run: chmod +x deploy-vercel.sh)"; fi
if [[ -f "$REDEPLOY" ]]; then pass "redeploy-vercel.sh exists";      else fail "redeploy-vercel.sh not found at $REDEPLOY"; fi
if [[ -x "$REDEPLOY" ]]; then pass "redeploy-vercel.sh is executable"; else fail "redeploy-vercel.sh is not executable (run: chmod +x redeploy-vercel.sh)"; fi
if [[ -f "$UNDEPLOY" ]]; then pass "undeploy-vercel.sh exists";       else fail "undeploy-vercel.sh not found at $UNDEPLOY"; fi
if [[ -x "$UNDEPLOY" ]]; then pass "undeploy-vercel.sh is executable"; else fail "undeploy-vercel.sh is not executable (run: chmod +x undeploy-vercel.sh)"; fi
if [[ -f "$WALKTHROUGH" ]]; then pass "record-walkthrough.sh exists"; else fail "record-walkthrough.sh not found at $WALKTHROUGH"; fi
if [[ -x "$WALKTHROUGH" ]]; then pass "record-walkthrough.sh is executable"; else fail "record-walkthrough.sh is not executable (run: chmod +x record-walkthrough.sh)"; fi

# ── 2. Shebang lines are correct ─────────────────────────────────────────────
echo ""
echo "── 2. Shebang lines"
DEPLOY_SHEBANG=$(head -1 "$DEPLOY")
REDEPLOY_SHEBANG=$(head -1 "$REDEPLOY")
UNDEPLOY_SHEBANG=$(head -1 "$UNDEPLOY")
WALKTHROUGH_SHEBANG=$(head -1 "$WALKTHROUGH")
assert_contains "$DEPLOY_SHEBANG"   "#!/usr/bin/env bash" "deploy-vercel.sh has env-bash shebang"
assert_contains "$REDEPLOY_SHEBANG" "#!/usr/bin/env bash" "redeploy-vercel.sh has env-bash shebang"
assert_contains "$UNDEPLOY_SHEBANG" "#!/usr/bin/env bash" "undeploy-vercel.sh has env-bash shebang"
assert_contains "$WALKTHROUGH_SHEBANG" "#!/usr/bin/env bash" "record-walkthrough.sh has env-bash shebang"

# ── 3. Bash syntax check ─────────────────────────────────────────────────────
echo ""
echo "── 3. Bash syntax check"
bash -n "$DEPLOY"   2>/dev/null;  assert_exit_zero   $? "deploy-vercel.sh passes bash -n syntax check"
bash -n "$REDEPLOY" 2>/dev/null;  assert_exit_zero   $? "redeploy-vercel.sh passes bash -n syntax check"
bash -n "$UNDEPLOY" 2>/dev/null;  assert_exit_zero   $? "undeploy-vercel.sh passes bash -n syntax check"
bash -n "$WALKTHROUGH" 2>/dev/null; assert_exit_zero $? "record-walkthrough.sh passes bash -n syntax check"

# ── 4. --help flag exits 0 and prints usage ───────────────────────────────────
echo ""
echo "── 4. --help flag"
DEPLOY_HELP=$(bash "$DEPLOY" --help 2>&1); RC=$?
assert_exit_zero $RC "deploy-vercel.sh --help exits 0"
assert_contains "$DEPLOY_HELP" "BACKEND_URL" "deploy-vercel.sh --help mentions BACKEND_URL"
assert_contains "$DEPLOY_HELP" "Usage"        "deploy-vercel.sh --help shows Usage"

REDEPLOY_HELP=$(bash "$REDEPLOY" --help 2>&1); RC=$?
assert_exit_zero $RC "redeploy-vercel.sh --help exits 0"
assert_contains "$REDEPLOY_HELP" "--frontend-only" "redeploy-vercel.sh --help mentions --frontend-only"
assert_contains "$REDEPLOY_HELP" "BACKEND_URL"     "redeploy-vercel.sh --help mentions BACKEND_URL"
assert_contains "$REDEPLOY_HELP" "Usage"           "redeploy-vercel.sh --help shows Usage"

UNDEPLOY_HELP=$(bash "$UNDEPLOY" --help 2>&1); RC=$?
assert_exit_zero $RC "undeploy-vercel.sh --help exits 0"
assert_contains "$UNDEPLOY_HELP" "--project-name"  "undeploy-vercel.sh --help mentions --project-name"
assert_contains "$UNDEPLOY_HELP" "--frontend-only" "undeploy-vercel.sh --help mentions --frontend-only"
assert_contains "$UNDEPLOY_HELP" "--yes"            "undeploy-vercel.sh --help documents --yes flag"
assert_contains "$UNDEPLOY_HELP" "PERMANENTLY"      "undeploy-vercel.sh --help warns about permanent removal"

WALKTHROUGH_HELP=$(bash "$WALKTHROUGH" --help 2>&1); RC=$?
assert_exit_zero $RC "record-walkthrough.sh --help exits 0"
assert_contains "$WALKTHROUGH_HELP" "--url" "record-walkthrough.sh --help documents --url"
assert_contains "$WALKTHROUGH_HELP" "--interactive-settings" "record-walkthrough.sh --help documents Settings pause"
assert_contains "$WALKTHROUGH_HELP" "WALKTHROUGH_BASE_URL" "record-walkthrough.sh --help documents env override"

# ── 5. deploy-vercel.sh: unknown flag exits non-zero ─────────────────────────
echo ""
echo "── 5. Unknown flags are rejected"
bash "$DEPLOY" --nonexistent-flag 2>/dev/null; RC=$?
assert_exit_nonzero $RC "deploy-vercel.sh exits non-zero on unknown flag"

bash "$REDEPLOY" --nonexistent-flag 2>/dev/null; RC=$?
assert_exit_nonzero $RC "redeploy-vercel.sh exits non-zero on unknown flag"

bash "$UNDEPLOY" --nonexistent-flag 2>/dev/null; RC=$?
assert_exit_nonzero $RC "undeploy-vercel.sh exits non-zero on unknown flag"

bash "$WALKTHROUGH" --nonexistent-flag 2>/dev/null; RC=$?
assert_exit_nonzero $RC "record-walkthrough.sh exits non-zero on unknown flag"

# ── 5b. walkthrough recorder validates options without launching Playwright ───
echo ""
echo "── 5b. Walkthrough recorder dry-run"
WALKTHROUGH_DRY_RUN=$(bash "$WALKTHROUGH" --url "https://example.com" --username admin --password "secret-value" --headed --interactive-settings --dry-run 2>&1); RC=$?
assert_exit_zero $RC "record-walkthrough.sh --dry-run exits 0"
assert_contains "$WALKTHROUGH_DRY_RUN" "Mode       : admin" "record-walkthrough.sh reports admin mode"
assert_contains "$WALKTHROUGH_DRY_RUN" "Dry run only" "record-walkthrough.sh prints dry-run summary"
assert_not_contains "$WALKTHROUGH_DRY_RUN" "secret-value" "record-walkthrough.sh does not print admin password"

WALKTHROUGH_GUEST_DRY_RUN=$(bash "$WALKTHROUGH" --url "http://localhost:5173" --dry-run 2>&1); RC=$?
assert_exit_zero $RC "record-walkthrough.sh guest --dry-run exits 0"
assert_contains "$WALKTHROUGH_GUEST_DRY_RUN" "Mode       : guest" "record-walkthrough.sh defaults to guest mode"

WALKTHROUGH_BAD_URL=$(bash "$WALKTHROUGH" --url "not-a-url" --dry-run 2>&1); RC=$?
assert_exit_nonzero $RC "record-walkthrough.sh rejects invalid URL"
assert_contains "$WALKTHROUGH_BAD_URL" "must start with http" "record-walkthrough.sh explains URL requirement"

# ── 6. deploy-vercel.sh: exits non-zero when vercel CLI is absent ─────────────
echo ""
echo "── 6. Missing Vercel CLI detection"
# Use PATH that has node but not vercel, so the script reaches the vercel CLI check
NO_VERCEL_OUTPUT=$(PATH="$PATH_WITHOUT_VERCEL" bash "$DEPLOY" --backend-url "https://example.com" 2>&1); RC=$?
assert_exit_nonzero $RC "deploy-vercel.sh exits non-zero when vercel CLI is missing"
assert_contains "$NO_VERCEL_OUTPUT" "not installed"       "deploy-vercel.sh prints 'not installed' message"
assert_contains "$NO_VERCEL_OUTPUT" "npm install -g vercel" "deploy-vercel.sh prints npm install hint"

NO_VERCEL_OUTPUT2=$(PATH="$PATH_WITHOUT_VERCEL" bash "$UNDEPLOY" --project-name dummy --yes 2>&1); RC=$?
assert_exit_nonzero $RC "undeploy-vercel.sh exits non-zero when vercel CLI is missing"
assert_contains "$NO_VERCEL_OUTPUT2" "not installed" "undeploy-vercel.sh prints 'not installed' message"

NO_VERCEL_OUTPUT3=$(PATH="$PATH_WITHOUT_VERCEL" bash "$REDEPLOY" --frontend-only --project-name dummy --yes 2>&1); RC=$?
assert_exit_nonzero $RC "redeploy-vercel.sh exits non-zero when Vercel CLI is missing"
assert_contains "$NO_VERCEL_OUTPUT3" "not installed" "redeploy-vercel.sh prints 'not installed' message"

# ── 7. deploy-vercel.sh: invalid BACKEND_URL format rejected ─────────────────
echo ""
echo "── 7. BACKEND_URL validation"
# Only reachable if vercel CLI is installed; skip gracefully if not
if command -v vercel &>/dev/null; then
    BAD_URL_OUTPUT=$(bash "$DEPLOY" --backend-url "not-a-url" 2>&1); RC=$?
    assert_exit_nonzero $RC "deploy-vercel.sh rejects URL without http(s):// prefix"
    assert_contains "$BAD_URL_OUTPUT" "must start with http" "deploy-vercel.sh explains URL format requirement"
else
    echo -e "  ${YELLOW}SKIP${NC}  BACKEND_URL validation (vercel CLI not installed — install to enable)"
fi

# ── 7b. frontend-only redeploy/undeploy use frontend project link ─────────────
echo ""
echo "── 7b. Frontend-only redeploy/undeploy with mocked Vercel CLI"
FAKE_ROOT="$_TMP_FAKE_REPO/fake-project"
FAKE_BIN="$_TMP_FAKE_REPO/bin"
FAKE_LOG="$_TMP_FAKE_REPO/vercel.log"
mkdir -p "$FAKE_ROOT/scripts/remote" "$FAKE_ROOT/frontend/.vercel" "$FAKE_ROOT/.vercel" "$FAKE_BIN"
cp "$DEPLOY" "$FAKE_ROOT/scripts/remote/deploy-vercel.sh"
cp "$REDEPLOY" "$FAKE_ROOT/scripts/remote/redeploy-vercel.sh"
cp "$UNDEPLOY" "$FAKE_ROOT/scripts/remote/undeploy-vercel.sh"
cp "$VERCEL_JSON" "$FAKE_ROOT/frontend/vercel.json"
chmod +x "$FAKE_ROOT/scripts/remote/"*.sh
printf '%s\n' '{"projectName":"root-project","projectId":"root","orgId":"team"}' > "$FAKE_ROOT/.vercel/project.json"
printf '%s\n' '{"projectName":"frontend-project","projectId":"front","orgId":"team"}' > "$FAKE_ROOT/frontend/.vercel/project.json"
cat > "$FAKE_BIN/vercel" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "PWD=$PWD ARGS=$*" >> "$FAKE_VERCEL_LOG"
case "${1:-}" in
  --version)
    echo "vercel 99.0.0"
    ;;
  whoami)
    echo "mock-user"
    ;;
  env)
    [[ "${2:-}" == "add" ]] && echo "Added ${3:-ENV_VAR} to ${4:-scope}"
    exit 0
    ;;
  remove)
    echo "Removed $2"
    ;;
  *)
    echo "https://frontend-project.vercel.app"
    ;;
esac
EOF
chmod +x "$FAKE_BIN/vercel"

FAKE_PATH="$FAKE_BIN:$PATH_WITHOUT_VERCEL"
FAKE_ORIGINAL_VERCEL_JSON=$(cat "$FAKE_ROOT/frontend/vercel.json")
FAKE_REDEPLOY_OUTPUT=$(FAKE_VERCEL_LOG="$FAKE_LOG" PATH="$FAKE_PATH" bash "$FAKE_ROOT/scripts/remote/redeploy-vercel.sh" --frontend-only --backend-url "https://backend.example.com" --yes 2>&1); RC=$?
assert_exit_zero $RC "redeploy-vercel.sh --frontend-only succeeds with mocked Vercel"
assert_contains "$FAKE_REDEPLOY_OUTPUT" "Frontend-only redeploy complete" "redeploy-vercel.sh reports frontend-only completion"
assert_contains "$(cat "$FAKE_LOG")" "$FAKE_ROOT/frontend ARGS=env add VITE_API_URL production" "redeploy-vercel.sh sets production VITE_API_URL from frontend directory"
assert_contains "$(cat "$FAKE_LOG")" "$FAKE_ROOT/frontend ARGS=--prod --yes" "redeploy-vercel.sh deploys from frontend directory"
if [[ "$FAKE_ORIGINAL_VERCEL_JSON" == "$(cat "$FAKE_ROOT/frontend/vercel.json")" ]]; then
    pass "redeploy-vercel.sh restores frontend/vercel.json after frontend-only redeploy"
else
    fail "redeploy-vercel.sh did not restore frontend/vercel.json"
fi

: > "$FAKE_LOG"
FAKE_UNDEPLOY_OUTPUT=$(printf 'yes\n' | FAKE_VERCEL_LOG="$FAKE_LOG" PATH="$FAKE_PATH" bash "$FAKE_ROOT/scripts/remote/undeploy-vercel.sh" --frontend-only 2>&1); RC=$?
assert_exit_zero $RC "undeploy-vercel.sh --frontend-only succeeds with mocked Vercel"
assert_contains "$FAKE_UNDEPLOY_OUTPUT" "frontend-project" "undeploy-vercel.sh selects frontend-only project"
assert_contains "$(cat "$FAKE_LOG")" "$FAKE_ROOT/frontend ARGS=remove frontend-project --yes" "undeploy-vercel.sh removes frontend project from frontend directory"
if [[ ! -d "$FAKE_ROOT/frontend/.vercel" ]]; then
    pass "undeploy-vercel.sh removes frontend .vercel link"
else
    fail "undeploy-vercel.sh left frontend .vercel link behind"
fi
if [[ -d "$FAKE_ROOT/.vercel" ]]; then
    pass "undeploy-vercel.sh preserves unrelated root .vercel link"
else
    fail "undeploy-vercel.sh removed unrelated root .vercel link"
fi

# ── 8. deploy-vercel.sh: vercel.json is restored after a failed deploy ────────
echo ""
echo "── 8. frontend/vercel.json integrity"
ORIGINAL_CONTENT=$(cat "$VERCEL_JSON")

# Run with no-vercel PATH so script exits at step 1; trap should still restore vercel.json
PATH="$PATH_WITHOUT_VERCEL" bash "$DEPLOY" --backend-url "https://example.com" 2>/dev/null || true

AFTER_CONTENT=$(cat "$VERCEL_JSON")
if [[ "$ORIGINAL_CONTENT" == "$AFTER_CONTENT" ]]; then
    pass "frontend/vercel.json is identical after aborted deploy"
else
    fail "frontend/vercel.json was modified and not restored"
fi

if [[ ! -f "${VERCEL_JSON}.bak" ]]; then
    pass "frontend/vercel.json.bak was cleaned up by trap"
else
    fail "frontend/vercel.json.bak was left behind"
fi

# ── 9. vercel.json contains required structure ────────────────────────────────
echo ""
echo "── 9. frontend/vercel.json structure"
VERCEL_JSON_CONTENT=$(cat "$VERCEL_JSON")
assert_contains "$VERCEL_JSON_CONTENT" "rewrites"         "vercel.json contains rewrites"
assert_contains "$VERCEL_JSON_CONTENT" "/api/(.*)"        "vercel.json has /api/* rewrite rule"
assert_contains "$VERCEL_JSON_CONTENT" "/index.html"      "vercel.json has SPA fallback rewrite"
assert_contains "$VERCEL_JSON_CONTENT" "X-Frame-Options"  "vercel.json sets X-Frame-Options header"

echo ""
echo "── 9b. root vercel.json Services structure"
ROOT_VERCEL_JSON_CONTENT=$(cat "$SCRIPT_DIR/vercel.json")
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "experimentalServices" "root vercel.json enables Vercel Services"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"web\""              "root vercel.json defines web service"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"api\""              "root vercel.json defines api service"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"entrypoint\": \"frontend\"" "web service points at frontend"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"entrypoint\": \"backend/main.py\"" "api service points at FastAPI entrypoint"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"routePrefix\": \"/api\"" "api service is mounted at /api"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"framework\": \"fastapi\"" "api service pins FastAPI framework"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "\"framework\": \"vite\"" "web service pins Vite framework"
assert_contains "$ROOT_VERCEL_JSON_CONTENT" "frame-src 'self' blob:" "root CSP allows blob PDF previews"

# ── 10. Key guard phrases present in script bodies ───────────────────────────
echo ""
echo "── 10. Script content guards"
DEPLOY_BODY=$(cat "$DEPLOY")
REDEPLOY_BODY=$(cat "$REDEPLOY")
UNDEPLOY_BODY=$(cat "$UNDEPLOY")
WALKTHROUGH_BODY=$(cat "$WALKTHROUGH")
assert_contains "$DEPLOY_BODY"   "set -euo pipefail"     "deploy-vercel.sh uses strict mode"
assert_contains "$REDEPLOY_BODY" "set -euo pipefail"     "redeploy-vercel.sh uses strict mode"
assert_contains "$UNDEPLOY_BODY" "set -euo pipefail"     "undeploy-vercel.sh uses strict mode"
assert_contains "$WALKTHROUGH_BODY" "set -euo pipefail"  "record-walkthrough.sh uses strict mode"
assert_contains "$DEPLOY_BODY"   "trap cleanup EXIT"     "deploy-vercel.sh registers cleanup trap"
assert_contains "$REDEPLOY_BODY" "trap cleanup EXIT"     "redeploy-vercel.sh registers cleanup trap"
assert_contains "$UNDEPLOY_BODY" "PERMANENTLY"           "undeploy-vercel.sh warns about permanent removal"
assert_contains "$UNDEPLOY_BODY" "vercel remove"         "undeploy-vercel.sh calls vercel remove"
assert_contains "$DEPLOY_BODY"   "vercel env add"        "deploy-vercel.sh sets Vercel env vars"
assert_contains "$DEPLOY_BODY"   "VITE_API_URL"          "deploy-vercel.sh sets VITE_API_URL"
assert_contains "$REDEPLOY_BODY" "--frontend-only"       "redeploy-vercel.sh supports frontend-only mode"
assert_contains "$REDEPLOY_BODY" "VITE_API_URL"          "redeploy-vercel.sh sets VITE_API_URL"
assert_contains "$UNDEPLOY_BODY" "--frontend-only"       "undeploy-vercel.sh supports frontend-only mode"
assert_contains "$WALKTHROUGH_BODY" "WALKTHROUGH_BASE_URL" "record-walkthrough.sh exports Playwright base URL"
assert_contains "$WALKTHROUGH_BODY" "walkthrough:record"    "record-walkthrough.sh calls frontend recorder"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
TOTAL=$((PASS + FAIL))
echo "=== Results: $PASS/$TOTAL passed ==="
if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}$FAIL test(s) failed.${NC}"
    echo ""
    exit 1
else
    echo -e "${GREEN}All tests passed.${NC}"
    echo ""
    exit 0
fi
