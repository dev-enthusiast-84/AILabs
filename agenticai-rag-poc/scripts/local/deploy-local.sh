#!/usr/bin/env bash
# deploy-local.sh — Local production deployment for Agentic RAG.
#
# Differences from dev.sh:
#   • Frontend is built for production (npm run build) and served via Vite preview.
#   • Backend runs without --reload (production uvicorn, no file watcher).
#   • Binds to 0.0.0.0 so the app is reachable from other machines on the LAN.
#
# Use this for demos, presentations, and local production testing.
# Use dev.sh for day-to-day development (hot reload).
#
# Usage:
#   bash deploy-local.sh                          # backend :8000, frontend :4173
#   bash deploy-local.sh --open                   # same, opens browser automatically
#   bash deploy-local.sh --port-backend  <port>   # custom backend port
#   bash deploy-local.sh --port-frontend <port>   # custom frontend port
#   bash deploy-local.sh --host <host>            # bind host (default: 0.0.0.0)
#   bash deploy-local.sh --skip-build             # skip npm build (reuse last build)
#   bash deploy-local.sh --sample-data            # generate sample docs before starting
#   bash deploy-local.sh --sample-topic "Healthcare Policy"
#   bash deploy-local.sh --help                   # show this help

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
NC='\033[0m'
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BE_COL='\033[0;35m'
FE_COL='\033[0;34m'

info()    { echo -e "${CYAN}[deploy-local]${NC} $*"; }
success() { echo -e "${GREEN}[deploy-local] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[deploy-local] ⚠${NC} $*"; }
error()   { echo -e "${RED}[deploy-local] ✗${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"

# ── Sample data generator ─────────────────────────────────────────────────────
generate_sample_data() {
    local topic="$1"
    local default_topic="Generative AI and Agentic AI"

    topic="${topic:-$default_topic}"
    if [[ "$topic" == "$default_topic" ]]; then
        echo ""
        read -rp "  Topic for sample documents [$default_topic]: " _t
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

# ── Argument parsing ──────────────────────────────────────────────────────────
BACKEND_PORT=8000
FRONTEND_PORT=4173
BIND_HOST="0.0.0.0"
OPEN_BROWSER=false
SKIP_BUILD=false
GENERATE_SAMPLE_DATA=false
SAMPLE_TOPIC="${SAMPLE_TOPIC:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --open|-o)              OPEN_BROWSER=true; shift ;;
        --skip-build)           SKIP_BUILD=true;   shift ;;
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
            sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)
            die "Unknown option: $1 (run with --help for usage)" ;;
    esac
done

# ── PID tracking ──────────────────────────────────────────────────────────────
BE_PID=""
FE_PID=""

cleanup() {
    echo ""
    info "Shutting down…"
    [[ -n "$BE_PID" ]] && kill -- -"$BE_PID" 2>/dev/null || true
    [[ -n "$FE_PID" ]] && kill -- -"$FE_PID" 2>/dev/null || true
    [[ -n "$BE_PID" ]] && wait "$BE_PID" 2>/dev/null || true
    [[ -n "$FE_PID" ]] && wait "$FE_PID" 2>/dev/null || true
    success "Servers stopped."
}
trap cleanup INT TERM EXIT

# ── Output labelling ──────────────────────────────────────────────────────────
_label() {
    local tag="$1" color="$2"
    while IFS= read -r line; do
        printf "${color}[%-8s]${NC} %s\n" "$tag" "$line"
    done
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
preflight() {
    if [[ ! -f "$VENV/bin/activate" ]]; then
        error "Python virtual environment not found at $VENV"
        echo "  Run:  bash setup.sh"
        exit 1
    fi
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        error "backend/.env not found."
        echo "  Run:  bash setup.sh"
        exit 1
    fi
    # Warn if OPENAI_API_KEY is still the placeholder
    if grep -q 'OPENAI_API_KEY=$\|OPENAI_API_KEY=your_\|OPENAI_API_KEY=sk-xxx' "$BACKEND_DIR/.env" 2>/dev/null; then
        warn "OPENAI_API_KEY in backend/.env looks like a placeholder — set a real key before querying."
    fi
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        error "Frontend dependencies not installed (node_modules missing)."
        echo "  Run:  cd frontend && npm ci"
        exit 1
    fi
}

# ── Read admin password safely (no shell expansion of special chars) ───────────
_read_admin_pw() {
    python3 - "$BACKEND_DIR/.env" <<'PYEOF' 2>/dev/null || echo "(see backend/.env)"
import sys
env_file = sys.argv[1]
try:
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            if k.strip() == 'ADMIN_PASSWORD':
                print(v.strip())
                break
except Exception:
    print("(see backend/.env)")
PYEOF
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
        if curl -sf "$url" &>/dev/null; then
            return 0
        fi
        sleep 1
        ((elapsed++))
    done
    return 1
}

# ── Detect local LAN IP for display ──────────────────────────────────────────
_lan_ip() {
    # Best-effort: try common approaches across macOS and Linux
    if command -v ip &>/dev/null; then
        ip route get 1.1.1.1 2>/dev/null | awk '/src/{print $7; exit}' || true
    elif command -v ifconfig &>/dev/null; then
        ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | head -1 || true
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Agentic RAG — Local Production Deployment${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""

preflight

if [[ "$GENERATE_SAMPLE_DATA" == true ]]; then
    generate_sample_data "$SAMPLE_TOPIC"
else
    echo ""
    read -rp "  Generate sample documents before starting? [y/N]: " _want_samples; echo ""
    if [[ "$(echo "$_want_samples" | tr '[:upper:]' '[:lower:]')" =~ ^y ]]; then
        generate_sample_data "$SAMPLE_TOPIC"
    fi
fi

# ── Step 1: Build frontend for production ─────────────────────────────────────
if [[ "$SKIP_BUILD" == true ]]; then
    if [[ ! -d "$FRONTEND_DIR/dist" ]]; then
        die "--skip-build was set but frontend/dist/ does not exist. Run without --skip-build first."
    fi
    warn "Skipping frontend build — reusing existing dist/"
else
    info "Building frontend for production (npm run build)…"
    (
        cd "$FRONTEND_DIR"
        npm run build 2>&1
    ) | _label "BUILD" "$CYAN"
    success "Frontend build complete → frontend/dist/"
fi

# ── Step 2: Start backend (no --reload) ───────────────────────────────────────
info "Starting backend (port ${BACKEND_PORT}, production mode — no hot reload)…"

setsid bash -c "
    source '${VENV}/bin/activate'
    cd '${BACKEND_DIR}'
    exec uvicorn app.main:app \
        --host ${BIND_HOST} \
        --port ${BACKEND_PORT} \
        --workers 1
" 2>&1 | _label "BACKEND" "$BE_COL" &
BE_PID=$!

# ── Step 3: Start frontend preview (serves the production build) ───────────────
info "Starting frontend preview server (port ${FRONTEND_PORT})…"

setsid bash -c "
    cd '${FRONTEND_DIR}'
    exec npm run preview -- \
        --port ${FRONTEND_PORT} \
        --host ${BIND_HOST}
" 2>&1 | _label "FRONTEND" "$FE_COL" &
FE_PID=$!

# ── Step 4: Wait for backend to be healthy ────────────────────────────────────
info "Waiting for backend to be ready…"
if wait_for_backend; then
    success "Backend is up"
else
    warn "Backend health check timed out — it may still be initialising"
fi

# ── Step 5: Print access information ─────────────────────────────────────────
ADMIN_PW=$(_read_admin_pw)
LAN_IP=$(_lan_ip)

echo ""
echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
echo -e "  ${GREEN}Web app (local)   ${NC}  http://localhost:${FRONTEND_PORT}"
if [[ -n "$LAN_IP" ]]; then
echo -e "  ${GREEN}Web app (LAN)     ${NC}  http://${LAN_IP}:${FRONTEND_PORT}"
fi
echo -e "  ${GREEN}API docs          ${NC}  http://localhost:${BACKEND_PORT}/api/docs"
echo -e "  ${GREEN}Health check      ${NC}  http://localhost:${BACKEND_PORT}/api/health"
echo ""
echo -e "  ${YELLOW}Admin login       ${NC}  username: admin"
echo -e "  ${YELLOW}                  ${NC}  password: ${ADMIN_PW}"
echo ""
echo -e "  ${CYAN}Mode              ${NC}  Production (no hot reload, built frontend)"
echo -e "  ${CYAN}Frontend          ${NC}  Serving built dist/ via Vite preview"
echo -e "  ${CYAN}Backend           ${NC}  uvicorn --workers 1 (no --reload)"
echo ""
echo -e "  Press ${BOLD}Ctrl-C${NC} to stop all services"
echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
echo ""

# Open browser if requested
if [[ "$OPEN_BROWSER" == true ]]; then
    sleep 1
    open_browser "http://localhost:${FRONTEND_PORT}"
fi

# Block until Ctrl-C (trap handles cleanup)
wait
