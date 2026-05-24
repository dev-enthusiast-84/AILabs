#!/usr/bin/env bash
# deploy-local.sh — One-command local startup for Agentic RAG.
#
# Runs first-time setup automatically when needed, then starts backend and frontend.
# Credentials are ephemeral in all modes: written to backend/.env for the session
# and wiped automatically when you press Ctrl-C.
#
# Modes:
#   Default (dev)   — uvicorn --reload on :8000, Vite dev server on :5173.
#   --prod          — uvicorn (no reload) on :8000, built frontend preview on :4173.
#
# Usage:
#   bash deploy-local.sh                          # dev mode (hot reload)
#   bash deploy-local.sh --prod                   # production-preview mode
#   bash deploy-local.sh --open                   # open browser automatically
#   bash deploy-local.sh --yes                    # non-interactive, auto-generate credentials
#   bash deploy-local.sh --setup                  # force re-run setup before starting
#   bash deploy-local.sh --skip-setup             # skip all setup checks
#   bash deploy-local.sh --skip-build             # skip npm build (--prod only)
#   bash deploy-local.sh --test                   # run backend + frontend unit tests before starting
#   bash deploy-local.sh --test-e2e               # run full test suite including E2E before starting
#   bash deploy-local.sh --test-only              # run tests and exit without starting servers
#   bash deploy-local.sh --sample-data            # generate sample documents before starting
#   bash deploy-local.sh --sample-topic "Topic"   # same, with a specific topic
#   bash deploy-local.sh --port-backend  <port>   # custom backend port
#   bash deploy-local.sh --port-frontend <port>   # custom frontend port
#   bash deploy-local.sh --host <host>            # bind host (default: 127.0.0.1)
#   bash deploy-local.sh --help                   # show this help
#
# Environment variables (skip interactive prompts):
#   ADMIN_PASSWORD   Admin password (auto-generated if omitted)
#   SECRET_KEY       JWT signing key (auto-generated if omitted)

set -euo pipefail

# ── Cross-platform setsid shim ────────────────────────────────────────────────
# setsid (Linux) detaches a process into a new session so it survives terminal
# close and is isolated from the parent's process group.  macOS ships without
# setsid; backgrounding with & achieves the same isolation for our use case.
if ! command -v setsid > /dev/null 2>&1; then
    setsid() { "$@"; }
fi

# ── Colours ───────────────────────────────────────────────────────────────────
NC='\033[0m'; BOLD='\033[1m'
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BE_COL='\033[0;35m'; FE_COL='\033[0;34m'

info()    { echo -e "${CYAN}[deploy]${NC} $*"; }
success() { echo -e "${GREEN}[deploy] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[deploy] ⚠${NC} $*"; }
error()   { echo -e "${RED}[deploy] ✗${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
SETUP_SCRIPT="$SCRIPT_DIR/scripts/local/setup.sh"
VENV="$BACKEND_DIR/.venv"

# ── Argument parsing ──────────────────────────────────────────────────────────
PROD_MODE=false
OPEN_BROWSER=false
SKIP_BUILD=false
FORCE_SETUP=false
SKIP_SETUP=false
RUN_TESTS=false
RUN_E2E=false
TEST_ONLY=false
GENERATE_SAMPLE_DATA=false
SAMPLE_TOPIC="${SAMPLE_TOPIC:-}"
AUTO_YES=false
BACKEND_PORT=""
FRONTEND_PORT=""
BIND_HOST=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prod|-p)              PROD_MODE=true; shift ;;
        --open|-o)              OPEN_BROWSER=true; shift ;;
        --yes|-y)               AUTO_YES=true; shift ;;
        --setup)                FORCE_SETUP=true; shift ;;
        --skip-setup)           SKIP_SETUP=true; shift ;;
        --skip-build)           SKIP_BUILD=true; shift ;;
        --test)                 RUN_TESTS=true; shift ;;
        --test-e2e)             RUN_TESTS=true; RUN_E2E=true; shift ;;
        --test-only)            RUN_TESTS=true; TEST_ONLY=true; shift ;;
        --sample-data|--generate-sample-data) GENERATE_SAMPLE_DATA=true; shift ;;
        --sample-topic)         SAMPLE_TOPIC="$2"; GENERATE_SAMPLE_DATA=true; shift 2 ;;
        --sample-topic=*)       SAMPLE_TOPIC="${1#*=}"; GENERATE_SAMPLE_DATA=true; shift ;;
        --port-backend)         BACKEND_PORT="$2"; shift 2 ;;
        --port-backend=*)       BACKEND_PORT="${1#*=}"; shift ;;
        --port-frontend)        FRONTEND_PORT="$2"; shift 2 ;;
        --port-frontend=*)      FRONTEND_PORT="${1#*=}"; shift ;;
        --host)                 BIND_HOST="$2"; shift 2 ;;
        --host=*)               BIND_HOST="${1#*=}"; shift ;;
        --help|-h)
            sed -n '2,33p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)
            die "Unknown option: $1 (run with --help for usage)" ;;
    esac
done

# Apply mode-specific port/host defaults
BACKEND_PORT="${BACKEND_PORT:-8000}"
if [[ "$PROD_MODE" == true ]]; then
    FRONTEND_PORT="${FRONTEND_PORT:-4173}"
    BIND_HOST="${BIND_HOST:-0.0.0.0}"
else
    FRONTEND_PORT="${FRONTEND_PORT:-5173}"
    BIND_HOST="${BIND_HOST:-127.0.0.1}"
fi

# ── Setup helpers ─────────────────────────────────────────────────────────────

_needs_setup() {
    [[ ! -f "$VENV/bin/activate" ]] ||
    [[ ! -f "$BACKEND_DIR/.env" ]] ||
    [[ ! -d "$FRONTEND_DIR/node_modules" ]]
}

run_setup() {
    [[ -f "$SETUP_SCRIPT" ]] || die "setup.sh not found at $SETUP_SCRIPT"
    local setup_args=()
    [[ "$AUTO_YES" == true ]] && setup_args+=(--yes)
    bash "$SETUP_SCRIPT" "${setup_args[@]}"
}

# ── Test runner ───────────────────────────────────────────────────────────────
TEST_COL='\033[0;33m'

run_tests() {
    local failed=false

    echo ""
    echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD} Running tests${NC}"
    echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
    echo ""

    # Backend: unit + integration
    info "Backend — unit tests…"
    (
        source "$VENV/bin/activate"
        cd "$BACKEND_DIR"
        pytest tests/unit/ -q --tb=short --no-header 2>&1
    ) | _label "BE-UNIT" "$TEST_COL" || failed=true

    info "Backend — integration tests…"
    (
        source "$VENV/bin/activate"
        cd "$BACKEND_DIR"
        pytest tests/integration/ -q --tb=short --no-header 2>&1
    ) | _label "BE-INTG" "$TEST_COL" || failed=true

    # Frontend: unit tests
    info "Frontend — unit tests…"
    (
        cd "$FRONTEND_DIR"
        npm test -- --run 2>&1
    ) | _label "FE-UNIT" "$TEST_COL" || failed=true

    # E2E tests (optional, requires running stack)
    if [[ "$RUN_E2E" == true ]]; then
        info "Frontend — E2E tests (requires running app on :${BACKEND_PORT}/:${FRONTEND_PORT})…"
        warn "E2E tests run against live servers — start servers first if not already up."
        (
            cd "$FRONTEND_DIR"
            npm run test:e2e 2>&1
        ) | _label "FE-E2E" "$TEST_COL" || failed=true
    fi

    echo ""
    if [[ "$failed" == true ]]; then
        error "One or more test suites failed. Fix before deploying."
        return 1
    fi
    success "All tests passed."
    echo ""
}

# ── Credential helpers ────────────────────────────────────────────────────────

_gen_password() {
    python3 -c "
import secrets, string
chars = string.ascii_letters + string.digits + '!@#%^&*'
print(''.join(secrets.choice(chars) for _ in range(16)))
"
}

_gen_secret_key() {
    if command -v openssl &>/dev/null; then
        openssl rand -hex 32
    else
        python3 -c "import secrets; print(secrets.token_hex(32))"
    fi
}

_write_env_key() {
    local key="$1" value="$2"
    KEY="$key" VALUE="$value" python3 - <<'PYEOF'
import os, re, pathlib
key, value = os.environ['KEY'], os.environ['VALUE']
p = pathlib.Path('backend/.env')
content = p.read_text()
if re.search(rf'^{re.escape(key)}=', content, re.MULTILINE):
    content = re.sub(rf'^{re.escape(key)}=.*$', f'{key}={value}', content, flags=re.MULTILINE)
else:
    content = content.rstrip('\n') + f'\n{key}={value}\n'
p.write_text(content)
PYEOF
}

_wipe_env_key() {
    local key="$1"
    KEY="$key" python3 - <<'PYEOF'
import os, re, pathlib
key = os.environ['KEY']
p = pathlib.Path('backend/.env')
if not p.exists(): exit(0)
content = p.read_text()
content = re.sub(rf'^{re.escape(key)}=.*$', f'{key}=', content, flags=re.MULTILINE)
p.write_text(content)
PYEOF
}

# ── PID tracking + cleanup ────────────────────────────────────────────────────
BE_PID=""
FE_PID=""
_WROTE_EPHEMERAL_CREDS=false

cleanup() {
    echo ""
    if [[ -n "$BE_PID" || -n "$FE_PID" ]]; then
        info "Shutting down…"
        [[ -n "$BE_PID" ]] && kill -- -"$BE_PID" 2>/dev/null || true
        [[ -n "$FE_PID" ]] && kill -- -"$FE_PID" 2>/dev/null || true
        [[ -n "$BE_PID" ]] && wait "$BE_PID" 2>/dev/null || true
        [[ -n "$FE_PID" ]] && wait "$FE_PID" 2>/dev/null || true
        success "Servers stopped."
    fi

    if [[ "$_WROTE_EPHEMERAL_CREDS" == true ]]; then
        echo ""
        info "Wiping ephemeral credentials from backend/.env…"
        (cd "$SCRIPT_DIR" && _wipe_env_key "ADMIN_PASSWORD" && _wipe_env_key "SECRET_KEY") 2>/dev/null || true
        success "Credentials wiped — backend/.env ADMIN_PASSWORD and SECRET_KEY cleared."
        echo ""
        warn "To start again run: bash scripts/local/deploy-local.sh"
    fi
}
trap cleanup INT TERM EXIT

# ── Output labelling ──────────────────────────────────────────────────────────
_label() {
    local tag="$1" color="$2"
    while IFS= read -r line; do
        printf "${color}[%-8s]${NC} %s\n" "$tag" "$line"
    done
}

# ── LAN IP helper ─────────────────────────────────────────────────────────────
_lan_ip() {
    if command -v ip &>/dev/null; then
        ip route get 1.1.1.1 2>/dev/null | awk '/src/{print $7; exit}' || true
    elif command -v ifconfig &>/dev/null; then
        ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | head -1 || true
    fi
}

# ── Open browser helper ───────────────────────────────────────────────────────
open_browser() {
    local url="$1"
    case "$(uname -s)" in
        Darwin)  open "$url" ;;
        Linux)   xdg-open "$url" 2>/dev/null || true ;;
        MINGW*|CYGWIN*|MSYS*) start "$url" ;;
    esac
}

# ── Wait for backend health endpoint ─────────────────────────────────────────
wait_for_backend() {
    local url="http://127.0.0.1:${BACKEND_PORT}/api/health"
    local max_wait=45 elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        if curl -sf "$url" &>/dev/null; then return 0; fi
        sleep 1; ((elapsed++))
    done
    return 1
}

# ── Sample data generator ─────────────────────────────────────────────────────
generate_sample_data() {
    local topic="${1:-Generative AI and Agentic AI}"
    if [[ "$topic" == "Generative AI and Agentic AI" && "$AUTO_YES" == false ]]; then
        read -rp "  Topic for sample documents [$topic]: " _t
        [[ -n "$_t" ]] && topic="$_t"
    fi
    info "Generating sample documents — topic: \"$topic\""
    (
        source "$VENV/bin/activate"
        cd "$SCRIPT_DIR"
        pip install -q reportlab openpyxl 2>/dev/null || true
        python sample-data/generate_samples.py --topic "$topic"
    )
    success "Sample files created in sample-data/"
    info "Upload them at http://localhost:${FRONTEND_PORT} after the app starts."
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
if [[ "$PROD_MODE" == true ]]; then
    echo -e "${BOLD} Agentic RAG — Local Production Preview${NC}"
else
    echo -e "${BOLD} Agentic RAG — Local Development${NC}"
fi
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Step 1: Setup ─────────────────────────────────────────────────────────────
if [[ "$SKIP_SETUP" == false ]]; then
    if [[ "$FORCE_SETUP" == true ]] || _needs_setup; then
        if [[ "$FORCE_SETUP" == true ]]; then
            info "Running setup (--setup flag)…"
        else
            info "First-time setup required…"
        fi
        run_setup
        echo ""
    else
        success "Setup already complete (use --setup to re-run)"
    fi
fi

# Verify prerequisites are now satisfied
[[ -f "$VENV/bin/activate" ]]         || die "Virtual environment missing. Run: bash scripts/local/setup.sh"
[[ -f "$BACKEND_DIR/.env" ]]          || die "backend/.env missing. Run: bash scripts/local/setup.sh"
[[ -d "$FRONTEND_DIR/node_modules" ]] || die "node_modules missing. Run: bash scripts/local/setup.sh"

# ── Step 2: Ephemeral credentials (all modes) ─────────────────────────────────
echo ""
info "Collecting ephemeral credentials for this session…"
echo ""
echo "  Credentials are ephemeral: written to backend/.env for this session"
echo "  only, then wiped automatically when you press Ctrl-C."
echo ""

ADMIN_PW="${ADMIN_PASSWORD:-}"
ADMIN_PW_GENERATED=false

if [[ -z "$ADMIN_PW" && "$AUTO_YES" == false ]]; then
    echo "  Choose a password for the admin account (username: admin)."
    echo "  Press Enter to auto-generate a secure password."
    echo ""
    read -rsp "  ADMIN_PASSWORD (hidden, min 8 chars, Enter to generate): " ADMIN_PW; echo ""; echo ""
fi

if [[ -z "$ADMIN_PW" ]]; then
    ADMIN_PW=$(_gen_password)
    ADMIN_PW_GENERATED=true
    success "Auto-generated ADMIN_PASSWORD"
elif [[ ${#ADMIN_PW} -lt 8 ]]; then
    die "ADMIN_PASSWORD must be at least 8 characters."
fi

SECRET_KEY_VAL="${SECRET_KEY:-$(_gen_secret_key)}"
success "Auto-generated SECRET_KEY"

cd "$SCRIPT_DIR"
_write_env_key "ADMIN_PASSWORD" "$ADMIN_PW"
_write_env_key "SECRET_KEY"     "$SECRET_KEY_VAL"
_WROTE_EPHEMERAL_CREDS=true
success "Credentials written to backend/.env (will be wiped on exit)"

# Warn if OpenAI key looks like a placeholder
if grep -qE 'OPENAI_API_KEY=($|your_|sk-xxx)' "$BACKEND_DIR/.env" 2>/dev/null; then
    warn "OPENAI_API_KEY in backend/.env looks like a placeholder — set a real key before querying."
fi

# ── Step 3: Tests (optional) ──────────────────────────────────────────────────
if [[ "$RUN_TESTS" == true ]]; then
    run_tests || die "Tests failed — fix issues before deploying (or remove --test to skip)."
    if [[ "$TEST_ONLY" == true ]]; then
        success "Tests complete. Exiting (--test-only)."
        exit 0
    fi
fi

# ── Step 4: Sample data (optional) ───────────────────────────────────────────
if [[ "$GENERATE_SAMPLE_DATA" == true ]]; then
    generate_sample_data "$SAMPLE_TOPIC"
elif [[ "$AUTO_YES" == false && "$PROD_MODE" == true ]]; then
    echo ""
    read -rp "  Generate sample documents before starting? [y/N]: " _want; echo ""
    if [[ "$(echo "$_want" | tr '[:upper:]' '[:lower:]')" =~ ^y ]]; then
        generate_sample_data "$SAMPLE_TOPIC"
    fi
fi

# ── Step 5: Build frontend (prod mode only) ───────────────────────────────────
if [[ "$PROD_MODE" == true ]]; then
    if [[ "$SKIP_BUILD" == true ]]; then
        [[ -d "$FRONTEND_DIR/dist" ]] || die "--skip-build set but frontend/dist/ does not exist."
        warn "Skipping frontend build — reusing existing dist/"
    else
        info "Building frontend for production…"
        (cd "$FRONTEND_DIR" && npm run build 2>&1) | _label "BUILD" "$CYAN"
        success "Frontend build complete → frontend/dist/"
    fi
fi

# ── Step 6: Start backend ─────────────────────────────────────────────────────
if [[ "$PROD_MODE" == true ]]; then
    info "Starting backend on :${BACKEND_PORT} (production, no hot reload)…"
    setsid bash -c "
        source '${VENV}/bin/activate'
        cd '${BACKEND_DIR}'
        exec uvicorn app.main:app --host ${BIND_HOST} --port ${BACKEND_PORT} --workers 1
    " 2>&1 | _label "BACKEND" "$BE_COL" &
else
    info "Starting backend on :${BACKEND_PORT} (dev, hot reload)…"
    setsid bash -c "
        source '${VENV}/bin/activate'
        cd '${BACKEND_DIR}'
        exec uvicorn app.main:app --host ${BIND_HOST} --port ${BACKEND_PORT} --reload
    " 2>&1 | _label "BACKEND" "$BE_COL" &
fi
BE_PID=$!

# ── Step 7: Start frontend ────────────────────────────────────────────────────
if [[ "$PROD_MODE" == true ]]; then
    info "Starting frontend preview on :${FRONTEND_PORT}…"
    setsid bash -c "
        cd '${FRONTEND_DIR}'
        exec npm run preview -- --port ${FRONTEND_PORT} --host ${BIND_HOST}
    " 2>&1 | _label "FRONTEND" "$FE_COL" &
else
    info "Starting frontend dev server on :${FRONTEND_PORT}…"
    setsid bash -c "
        cd '${FRONTEND_DIR}'
        exec npm run dev -- --port ${FRONTEND_PORT} --host ${BIND_HOST}
    " 2>&1 | _label "FRONTEND" "$FE_COL" &
fi
FE_PID=$!

# ── Step 8: Wait for backend to be healthy ────────────────────────────────────
info "Waiting for backend to be ready…"
if wait_for_backend; then
    success "Backend is up"
else
    warn "Backend health check timed out — it may still be initialising"
fi

# ── Step 9: Print access info ─────────────────────────────────────────────────
LAN_IP=$(_lan_ip)

echo ""
echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
echo -e "  ${GREEN}Web app           ${NC}  http://localhost:${FRONTEND_PORT}"
if [[ -n "$LAN_IP" && "$BIND_HOST" == "0.0.0.0" ]]; then
echo -e "  ${GREEN}Web app (LAN)     ${NC}  http://${LAN_IP}:${FRONTEND_PORT}"
fi
echo -e "  ${GREEN}API docs          ${NC}  http://localhost:${BACKEND_PORT}/api/docs"
echo -e "  ${GREEN}Health check      ${NC}  http://localhost:${BACKEND_PORT}/api/health"
echo ""
echo -e "  ${YELLOW}Admin login       ${NC}  username: admin"
if [[ "$ADMIN_PW_GENERATED" == true ]]; then
echo -e "  ${YELLOW}                  ${NC}  password: ${ADMIN_PW}   ${RED}← SAVE THIS NOW${NC}"
else
echo -e "  ${YELLOW}                  ${NC}  password: (the password you entered)"
fi
echo ""
if [[ "$PROD_MODE" == true ]]; then
echo -e "  ${CYAN}Mode              ${NC}  Production preview (no hot reload, built frontend)"
else
echo -e "  ${CYAN}Mode              ${NC}  Development (hot reload on both backend and frontend)"
fi
echo -e "  ${CYAN}Credentials       ${NC}  Ephemeral — wiped on Ctrl-C"
echo ""
echo -e "  Press ${BOLD}Ctrl-C${NC} to stop all services and wipe credentials"
echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
echo ""

if [[ "$OPEN_BROWSER" == true ]]; then
    sleep 1
    open_browser "http://localhost:${FRONTEND_PORT}"
fi

# Block until Ctrl-C (trap handles cleanup)
wait
