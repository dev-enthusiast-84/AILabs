#!/usr/bin/env bash
# dev.sh — One-command local development with hot reload.
#
# Usage:
#   bash dev.sh                            # backend (8000) + frontend (5173) with hot reload
#   bash dev.sh --backend-only             # backend only
#   bash dev.sh --frontend-only            # frontend only
#   bash dev.sh --open                     # open browser when servers are ready
#   bash dev.sh --port-backend  <port>     # custom backend port  (default: 8000)
#   bash dev.sh --port-frontend <port>     # custom frontend port (default: 5173)
#   bash dev.sh --help                     # show this help
#
# Hot-reload behaviour:
#   Backend  — uvicorn --reload watches every *.py file under backend/app/.
#              The server restarts automatically when you save a Python file.
#   Frontend — Vite HMR (Hot Module Replacement).  React components, CSS, and
#              TypeScript files update in the browser without a full-page reload.
#
# Press Ctrl-C once to stop both services cleanly.

set -euo pipefail

# ── Cross-platform setsid shim ────────────────────────────────────────────────
# setsid is Linux-only; on macOS, backgrounding with & provides equivalent
# process-group isolation for our use case.
if ! command -v setsid > /dev/null 2>&1; then
    setsid() { "$@"; }
fi

# ── Colours ───────────────────────────────────────────────────────────────────
NC='\033[0m'
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BE_COL='\033[0;35m'   # magenta — backend lines
FE_COL='\033[0;34m'   # blue    — frontend lines

info()    { echo -e "${CYAN}[dev]${NC} $*"; }
success() { echo -e "${GREEN}[dev] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[dev] ⚠${NC} $*"; }
error()   { echo -e "${RED}[dev] ✗${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="both"          # both | backend | frontend
BACKEND_PORT=8000
FRONTEND_PORT=5173
OPEN_BROWSER=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend-only)         MODE="backend";  shift ;;
        --frontend-only)        MODE="frontend"; shift ;;
        --open|-o)              OPEN_BROWSER=true; shift ;;
        --port-backend)         BACKEND_PORT="$2";  shift 2 ;;
        --port-backend=*)       BACKEND_PORT="${1#*=}"; shift ;;
        --port-frontend)        FRONTEND_PORT="$2"; shift 2 ;;
        --port-frontend=*)      FRONTEND_PORT="${1#*=}"; shift ;;
        --help|-h)
            sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)
            die "Unknown option: $1 (run with --help for usage)" ;;
    esac
done

# ── PID tracking (used by cleanup) ───────────────────────────────────────────
BE_PID=""
FE_PID=""

cleanup() {
    echo ""
    info "Shutting down…"
    # Kill both process groups so child processes (uvicorn reloader, vite) also die
    [[ -n "$BE_PID" ]] && kill -- -"$BE_PID" 2>/dev/null || true
    [[ -n "$FE_PID" ]] && kill -- -"$FE_PID" 2>/dev/null || true
    [[ -n "$BE_PID" ]] && wait "$BE_PID" 2>/dev/null || true
    [[ -n "$FE_PID" ]] && wait "$FE_PID" 2>/dev/null || true
    success "Servers stopped. Bye!"
}
trap cleanup INT TERM EXIT

# ── Output labelling helper ───────────────────────────────────────────────────
# Prefixes every line with a colour-coded [BACKEND] or [FRONTEND] tag.
_label() {
    local tag="$1" color="$2"
    while IFS= read -r line; do
        printf "${color}[%-8s]${NC} %s\n" "$tag" "$line"
    done
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
preflight_backend() {
    if [[ ! -f "$VENV/bin/activate" ]]; then
        error "Python virtual environment not found at $VENV"
        echo "  Run:  bash setup.sh"
        exit 1
    fi
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        error "backend/.env not found."
        echo "  Run:  bash setup.sh   (creates it from .env.example)"
        exit 1
    fi
}

preflight_frontend() {
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        error "Frontend dependencies not installed (node_modules missing)."
        echo "  Run:  cd frontend && npm ci"
        exit 1
    fi
}

# ── Read admin password safely for the startup banner ─────────────────────────
_read_admin_pw() {
    # Read via Python to avoid shell expansion of special characters (OWASP A03)
    python3 - "$BACKEND_DIR/.env" <<'PYEOF' 2>/dev/null || echo "(see backend/.env)"
import sys, re
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
    local max_wait=30 elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        if curl -sf "$url" &>/dev/null; then
            return 0
        fi
        sleep 1
        ((elapsed++))
    done
    return 1
}

# ── Start backend ─────────────────────────────────────────────────────────────
start_backend() {
    preflight_backend
    info "Starting backend (port ${BACKEND_PORT}, hot reload enabled)…"

    # setsid creates a new process group so kill -- -$PID reaches uvicorn's
    # child reloader process as well.
    PYTHONUNBUFFERED=1 setsid bash -c "
        source '${VENV}/bin/activate'
        cd '${BACKEND_DIR}'
        exec uvicorn app.main:app \
            --reload \
            --reload-dir app \
            --port ${BACKEND_PORT} \
            --host 127.0.0.1
    " 2>&1 | _label "BACKEND" "$BE_COL" &
    BE_PID=$!
}

# ── Start frontend ────────────────────────────────────────────────────────────
start_frontend() {
    preflight_frontend
    info "Starting frontend (port ${FRONTEND_PORT}, Vite HMR enabled)…"

    setsid bash -c "
        cd '${FRONTEND_DIR}'
        exec npm run dev -- --port ${FRONTEND_PORT} --host 127.0.0.1
    " 2>&1 | _label "FRONTEND" "$FE_COL" &
    FE_PID=$!
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Agentic RAG — Local Development Server${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""
info "Mode: $MODE"
echo ""

# Start the requested services
case "$MODE" in
    both)
        start_backend
        start_frontend
        ;;
    backend)
        start_frontend() { :; }   # no-op
        start_backend
        ;;
    frontend)
        start_backend() { :; }    # no-op
        start_frontend
        ;;
esac

# Wait for backend to be ready before printing the access table
if [[ "$MODE" == "both" || "$MODE" == "backend" ]]; then
    info "Waiting for backend to be ready…"
    if wait_for_backend; then
        success "Backend is up"
    else
        warn "Backend health check timed out — it may still be starting"
    fi
fi

# ── Print access URLs and credentials ────────────────────────────────────────
ADMIN_PW=$(_read_admin_pw)

echo ""
echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
if [[ "$MODE" == "both" || "$MODE" == "frontend" ]]; then
echo -e "  ${GREEN}Web app    ${NC}  http://localhost:${FRONTEND_PORT}"
fi
if [[ "$MODE" == "both" || "$MODE" == "backend" ]]; then
echo -e "  ${GREEN}API docs   ${NC}  http://localhost:${BACKEND_PORT}/api/docs"
echo -e "  ${GREEN}Health     ${NC}  http://localhost:${BACKEND_PORT}/api/health"
fi
echo ""
echo -e "  ${YELLOW}Admin login${NC}  username: admin"
echo -e "  ${YELLOW}           ${NC}  password: ${ADMIN_PW}"
echo ""
echo -e "  Hot reload  Backend — save any .py file to trigger restart"
echo -e "              Frontend — save any .tsx/.ts/.css for instant HMR"
echo ""
echo -e "  Press ${BOLD}Ctrl-C${NC} to stop all services"
echo -e "${BOLD}────────────────────────────────────────────────────────────${NC}"
echo ""

# Open browser if requested
if [[ "$OPEN_BROWSER" == true ]]; then
    if [[ "$MODE" == "both" || "$MODE" == "frontend" ]]; then
        sleep 1   # give Vite a moment to fully initialise
        open_browser "http://localhost:${FRONTEND_PORT}"
    elif [[ "$MODE" == "backend" ]]; then
        open_browser "http://localhost:${BACKEND_PORT}/api/docs"
    fi
fi

# Block until Ctrl-C (trap handles cleanup)
wait
