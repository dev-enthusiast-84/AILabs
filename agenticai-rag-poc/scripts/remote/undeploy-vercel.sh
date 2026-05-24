#!/usr/bin/env bash
# undeploy-vercel.sh — PERMANENTLY remove the Agentic RAG Vercel deployment.
#
# Usage:
#   bash undeploy-vercel.sh                               # auto-detect project
#   bash undeploy-vercel.sh --frontend-only               # remove frontend-only Vercel project
#   bash undeploy-vercel.sh --fullstack                   # remove full-stack Vercel project
#   bash undeploy-vercel.sh --project-name my-rag-app    # specify project name
#   bash undeploy-vercel.sh --yes                         # skip confirmation
#
# What this script does:
#   1. Resolves the Vercel project name from .vercel/project.json,
#      frontend/.vercel/project.json, or --project-name.
#   2. Asks for confirmation (skip with --yes).
#   3. Removes all environment variables set by deploy-vercel.sh.
#   4. Runs `vercel remove <project>` to delete all deployments and aliases.
#   5. Cleans up the local .vercel/ link directories.
#
# What it does NOT remove:
#   - Backend running on Railway / Render / ECS — shut that down separately.
#   - ChromaDB data on the backend host.

set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[undeploy-vercel]${NC} $*"; }
success() { echo -e "${GREEN}[undeploy-vercel] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[undeploy-vercel] ⚠${NC} $*"; }
error()   { echo -e "${RED}[undeploy-vercel] ✗${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# ── Argument parsing ──────────────────────────────────────────────────────────
PROJECT_NAME=""
AUTO_YES=false
DEPLOY_MODE="auto"
TARGET_DIR=""
TARGET_LINK_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-name)       PROJECT_NAME="$2"; shift 2 ;;
        --project-name=*)     PROJECT_NAME="${1#*=}"; shift ;;
        --frontend-only|--frontonly) DEPLOY_MODE="frontend-only"; shift ;;
        --fullstack)          DEPLOY_MODE="fullstack"; shift ;;
        --yes|-y)             AUTO_YES=true; shift ;;
        --help|-h)
            sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)
            die "Unknown option: $1 (run with --help for usage)" ;;
    esac
done

# ── 1. Check Vercel CLI ───────────────────────────────────────────────────────
if ! command -v vercel &>/dev/null; then
    die "Vercel CLI is not installed. Install: npm install -g vercel"
fi
success "Vercel CLI: $(vercel --version 2>/dev/null | head -1)"

# ── 2. Resolve project name ───────────────────────────────────────────────────
# Full-stack deploys link the repo root. Frontend-only deploys link frontend/.
_read_project_name() {
    local link_file="$1"
    # Pass path as argv to avoid shell-string injection (OWASP A03)
    python3 - "$link_file" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("projectName", ""))
except Exception:
    pass
PYEOF
}

ROOT_LINK="$SCRIPT_DIR/.vercel/project.json"
FRONTEND_LINK="$FRONTEND_DIR/.vercel/project.json"
ROOT_PROJECT=""
FRONTEND_PROJECT=""

[[ -f "$ROOT_LINK" ]] && ROOT_PROJECT=$(_read_project_name "$ROOT_LINK")
[[ -f "$FRONTEND_LINK" ]] && FRONTEND_PROJECT=$(_read_project_name "$FRONTEND_LINK")

_use_root_project() {
    PROJECT_NAME="$ROOT_PROJECT"
    TARGET_DIR="$SCRIPT_DIR"
    TARGET_LINK_DIR="$SCRIPT_DIR/.vercel"
    [[ -n "$PROJECT_NAME" ]] && info "Detected full-stack project from root/.vercel: $PROJECT_NAME"
}

_use_frontend_project() {
    PROJECT_NAME="$FRONTEND_PROJECT"
    TARGET_DIR="$FRONTEND_DIR"
    TARGET_LINK_DIR="$FRONTEND_DIR/.vercel"
    [[ -n "$PROJECT_NAME" ]] && info "Detected frontend-only project from frontend/.vercel: $PROJECT_NAME"
}

if [[ -z "$PROJECT_NAME" ]]; then
    case "$DEPLOY_MODE" in
        frontend-only)
            [[ -z "$FRONTEND_PROJECT" ]] && die "No frontend-only Vercel link found at frontend/.vercel/project.json"
            _use_frontend_project
            ;;
        fullstack)
            [[ -z "$ROOT_PROJECT" ]] && die "No full-stack Vercel link found at .vercel/project.json"
            _use_root_project
            ;;
        auto)
            if [[ -n "$ROOT_PROJECT" && -n "$FRONTEND_PROJECT" && "$ROOT_PROJECT" != "$FRONTEND_PROJECT" ]]; then
                if [[ "$AUTO_YES" == true ]]; then
                    die "Both full-stack ('$ROOT_PROJECT') and frontend-only ('$FRONTEND_PROJECT') links exist. Re-run with --fullstack or --frontend-only."
                fi

                echo ""
                warn "Multiple Vercel projects are linked locally."
                echo "  1) Full-stack    : $ROOT_PROJECT"
                echo "  2) Frontend-only : $FRONTEND_PROJECT"
                echo ""
                read -rp "  Which project should be removed? [1/2]: " _choice; echo ""
                case "${_choice:-}" in
                    2) _use_frontend_project ;;
                    1) _use_root_project ;;
                    *) die "Invalid selection. Aborting." ;;
                esac
            elif [[ -n "$FRONTEND_PROJECT" ]]; then
                _use_frontend_project
            elif [[ -n "$ROOT_PROJECT" ]]; then
                _use_root_project
            fi
            ;;
    esac
else
    case "$DEPLOY_MODE" in
        frontend-only)
            TARGET_DIR="$FRONTEND_DIR"
            TARGET_LINK_DIR="$FRONTEND_DIR/.vercel"
            ;;
        fullstack|auto)
            TARGET_DIR="$SCRIPT_DIR"
            TARGET_LINK_DIR="$SCRIPT_DIR/.vercel"
            ;;
    esac
fi

if [[ -z "$PROJECT_NAME" ]] && [[ "$AUTO_YES" == false ]]; then
    echo ""
    warn "Could not auto-detect the Vercel project name."
    echo "  Find it at: https://vercel.com/dashboard"
    echo "  Or run: vercel ls"
    echo ""
    read -rp "  Enter Vercel project name to remove: " PROJECT_NAME; echo ""
fi

[[ -z "$PROJECT_NAME" ]] && die "No project name provided. Aborting."
TARGET_DIR="${TARGET_DIR:-$SCRIPT_DIR}"

# ── 3. Confirm ────────────────────────────────────────────────────────────────
echo ""
warn "You are about to PERMANENTLY remove Vercel project: $PROJECT_NAME"
warn "This deletes ALL deployments and aliases for this project."
warn "The backend (Railway/Render/ECS) is NOT affected — shut it down separately."
echo ""

if [[ "$AUTO_YES" == false ]]; then
    read -rp "  Type 'yes' to confirm: " CONFIRM; echo ""
    [[ "$CONFIRM" != "yes" ]] && { info "Aborted — no changes made."; exit 0; }
fi

# ── 4. Remove environment variables ──────────────────────────────────────────
info "Removing environment variables from Vercel..."

_rm_env() {
    local name="$1"
    (cd "$TARGET_DIR" && vercel env rm "$name" production --yes 2>/dev/null) && success "Removed $name" || true
}

# Remove all vars set by deploy-vercel.sh (full-stack mode)
# Note: OPENAI_API_KEY is not removed — it is not set by the deploy script
# (admin enters it via the Settings UI after deployment).
for var in SECRET_KEY ADMIN_PASSWORD ADMIN_USERNAME \
           VECTOR_STORE_TYPE FILE_STORE_TYPE APP_ENV ALLOWED_ORIGINS; do
    _rm_env "$var"
done

# Remove vars set by deploy-vercel.sh (frontend-only mode)
for var in VITE_API_URL; do
    (cd "$TARGET_DIR" && vercel env rm "$var" production --yes 2>/dev/null) || true
    (cd "$TARGET_DIR" && vercel env rm "$var" preview    --yes 2>/dev/null) || true
done

success "Environment variables removed"

# ── 5. Remove the Vercel project ──────────────────────────────────────────────
info "Removing Vercel project: $PROJECT_NAME ..."
PROJECT_REMOVED=true
if ! remove_out=$(cd "$TARGET_DIR" && vercel remove "$PROJECT_NAME" --yes 2>&1); then
    echo "$remove_out"
    PROJECT_REMOVED=false
    warn "Could not remove project '$PROJECT_NAME' from Vercel (it may already be deleted, or the selected scope may be wrong)."
else
    echo "$remove_out"
    success "Project '$PROJECT_NAME' removed from Vercel"
fi

# ── 6. Clean up local .vercel directories ────────────────────────────────────
link_dirs=()
if [[ -n "$TARGET_LINK_DIR" ]]; then
    link_dirs+=("$TARGET_LINK_DIR")
else
    link_dirs+=("$SCRIPT_DIR/.vercel" "$FRONTEND_DIR/.vercel")
fi
[[ -n "$ROOT_PROJECT" && "$ROOT_PROJECT" == "$PROJECT_NAME" ]] && link_dirs+=("$SCRIPT_DIR/.vercel")
[[ -n "$FRONTEND_PROJECT" && "$FRONTEND_PROJECT" == "$PROJECT_NAME" ]] && link_dirs+=("$FRONTEND_DIR/.vercel")

for link_dir in "${link_dirs[@]}"; do
    if [[ -d "$link_dir" ]]; then
        rm -rf "$link_dir"
        success "Removed local link: $link_dir"
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
success "Undeploy complete!"
echo ""
echo "  Removed:"
if [[ "$PROJECT_REMOVED" == true ]]; then
echo "  • All Vercel deployments for project '$PROJECT_NAME'"
else
echo "  • Vercel project removal was attempted but did not complete"
fi
echo "  • All environment variables"
echo "  • Local .vercel/ link directories"
echo ""
echo "  Not removed:"
echo "  • Backend server (Railway/Render/ECS) — shut it down separately"
echo "  • Source code — deploy again with: bash deploy-vercel.sh"
echo "════════════════════════════════════════════════════════════"
