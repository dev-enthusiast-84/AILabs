#!/usr/bin/env bash
# Record the capstone walkthrough video with the frontend Playwright recorder.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"

BASE_URL="${WALKTHROUGH_BASE_URL:-}"
USERNAME="${WALKTHROUGH_USERNAME:-}"
PASSWORD="${WALKTHROUGH_PASSWORD:-}"
UPLOAD_FILE="${WALKTHROUGH_UPLOAD_FILE:-}"
SLOW_MO_MS="${WALKTHROUGH_SLOW_MO_MS:-250}"
INTERACTIVE_SETTINGS="${WALKTHROUGH_INTERACTIVE_SETTINGS:-false}"
INTERACTIVE_TIMEOUT_MS="${WALKTHROUGH_INTERACTIVE_TIMEOUT_MS:-600000}"
HEADED=false
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage:
  scripts/record-walkthrough.sh --url <app-url> [options]

Prerequisites (run once before recording):
  bash scripts/local/setup.sh

  The setup script will:
    • Detect Python 3.11–3.13 and create backend/.venv
    • Install backend Python dependencies (pip install -r requirements-dev.txt)
    • Create backend/.env from .env.example (set OPENAI_API_KEY inside)
    • Install frontend dependencies (npm ci)
    • Optionally generate sample data files for upload

  After setup, start both servers before recording a local URL:
    Terminal 1:  cd backend && source .venv/bin/activate
                 uvicorn app.main:app --reload --port 8000
    Terminal 2:  cd frontend && npm run dev
    App URL:     http://localhost:5173

Options:
  --url <url>                    Local or deployed app URL to record.
  --username <name>              Admin username. When provided with --password,
                                 both guest and admin walkthroughs are recorded.
                                 Omit to record guest mode only.
  --password <password>          Admin password. Never printed.
  --upload-file <path>           Optional file to upload during the walkthrough.
  --slow-mo-ms <number>          Browser action delay in milliseconds. Default: 250.
  --interactive-settings         Pause so the user can update Settings before recording continues.
  --timeout-ms <number>          Interactive settings timeout. Default: 600000.
  --headed                       Show the browser while recording.
  --dry-run                      Validate inputs and print the safe execution summary only.
  --help                         Show this help.

Equivalent environment variables:
  WALKTHROUGH_BASE_URL, WALKTHROUGH_USERNAME, WALKTHROUGH_PASSWORD,
  WALKTHROUGH_UPLOAD_FILE, WALKTHROUGH_SLOW_MO_MS,
  WALKTHROUGH_INTERACTIVE_SETTINGS, WALKTHROUGH_INTERACTIVE_TIMEOUT_MS
EOF
}

die() {
    echo "ERROR: $1" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || die "required file not found: $1"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)
            [[ $# -ge 2 ]] || die "--url requires a value"
            BASE_URL="$2"
            shift 2
            ;;
        --username)
            [[ $# -ge 2 ]] || die "--username requires a value"
            USERNAME="$2"
            shift 2
            ;;
        --password)
            [[ $# -ge 2 ]] || die "--password requires a value"
            PASSWORD="$2"
            shift 2
            ;;
        --upload-file)
            [[ $# -ge 2 ]] || die "--upload-file requires a value"
            UPLOAD_FILE="$2"
            shift 2
            ;;
        --slow-mo-ms)
            [[ $# -ge 2 ]] || die "--slow-mo-ms requires a value"
            SLOW_MO_MS="$2"
            shift 2
            ;;
        --interactive-settings)
            INTERACTIVE_SETTINGS=true
            shift
            ;;
        --timeout-ms)
            [[ $# -ge 2 ]] || die "--timeout-ms requires a value"
            INTERACTIVE_TIMEOUT_MS="$2"
            shift 2
            ;;
        --headed)
            HEADED=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

[[ -n "$BASE_URL" ]] || die "set --url or WALKTHROUGH_BASE_URL"
[[ "$BASE_URL" =~ ^https?:// ]] || die "--url must start with http:// or https://"
[[ "$SLOW_MO_MS" =~ ^[0-9]+$ ]] || die "--slow-mo-ms must be a non-negative integer"
[[ "$INTERACTIVE_TIMEOUT_MS" =~ ^[0-9]+$ ]] || die "--timeout-ms must be a non-negative integer"

# ── Prerequisites pre-flight ──────────────────────────────────────────────────
SETUP_NEEDED=false
if [[ ! -d "${SCRIPT_DIR}/backend/.venv" ]]; then
    echo "MISSING: backend/.venv — Python virtual environment not found." >&2
    SETUP_NEEDED=true
fi
if [[ ! -f "${SCRIPT_DIR}/backend/.env" ]]; then
    echo "MISSING: backend/.env — backend environment file not found." >&2
    SETUP_NEEDED=true
fi
if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "MISSING: frontend/node_modules — frontend dependencies not installed." >&2
    SETUP_NEEDED=true
fi
if [[ "$SETUP_NEEDED" == true ]]; then
    echo "" >&2
    echo "Run the setup script first, then re-run the walkthrough recorder:" >&2
    echo "  bash scripts/local/setup.sh" >&2
    echo "" >&2
    exit 1
fi
# ─────────────────────────────────────────────────────────────────────────────

require_file "${FRONTEND_DIR}/package.json"
require_file "${FRONTEND_DIR}/playwright.walkthrough.config.ts"
require_file "${FRONTEND_DIR}/tests/walkthrough/capstone-walkthrough.spec.ts"

command -v npm >/dev/null 2>&1 || die "npm is required to run the walkthrough recorder"

# --interactive-settings requires a visible browser window.
# Auto-enable --headed and tell the user so there is no silent hang.
if [[ "$INTERACTIVE_SETTINGS" == true && "$HEADED" == false ]]; then
    echo "NOTE: --interactive-settings requires a visible browser. Enabling --headed automatically."
    HEADED=true
fi

MODE="guest only"
if [[ -n "$USERNAME" || -n "$PASSWORD" ]]; then
    [[ -n "$USERNAME" && -n "$PASSWORD" ]] || die "provide both --username and --password for admin mode"
    MODE="guest + admin"
fi

if [[ -n "$UPLOAD_FILE" ]]; then
    [[ -f "$UPLOAD_FILE" ]] || die "upload file not found: $UPLOAD_FILE"
    UPLOAD_FILE="$(cd "$(dirname "$UPLOAD_FILE")" && pwd)/$(basename "$UPLOAD_FILE")"
fi

echo "Walkthrough recorder"
echo "  URL        : ${BASE_URL}"
echo "  Mode       : ${MODE}"
echo "  Browser    : $([[ "$HEADED" == true ]] && echo headed || echo headless)"
echo "  Settings   : $([[ "$INTERACTIVE_SETTINGS" == true ]] && echo interactive || echo automatic)"
echo "  Artifacts  : artifacts/walkthrough/"
if [[ -n "$UPLOAD_FILE" ]]; then
    echo "  Upload file: ${UPLOAD_FILE}"
fi
echo ""

CMD=(npm run walkthrough:record)
if [[ "$HEADED" == true ]]; then
    CMD+=(-- --headed)
fi

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run only. Would run from frontend/: ${CMD[*]}"
    exit 0
fi

cd "$FRONTEND_DIR"

export WALKTHROUGH_BASE_URL="$BASE_URL"
export WALKTHROUGH_SLOW_MO_MS="$SLOW_MO_MS"
export WALKTHROUGH_INTERACTIVE_SETTINGS="$INTERACTIVE_SETTINGS"
export WALKTHROUGH_INTERACTIVE_TIMEOUT_MS="$INTERACTIVE_TIMEOUT_MS"

# Export credentials when provided; guest test ignores them, admin test uses them.
if [[ -n "$USERNAME" ]]; then
    export WALKTHROUGH_USERNAME="$USERNAME"
    export WALKTHROUGH_PASSWORD="$PASSWORD"
else
    unset WALKTHROUGH_USERNAME
    unset WALKTHROUGH_PASSWORD
fi

if [[ -n "$UPLOAD_FILE" ]]; then
    export WALKTHROUGH_UPLOAD_FILE="$UPLOAD_FILE"
else
    unset WALKTHROUGH_UPLOAD_FILE
fi

"${CMD[@]}"
