#!/usr/bin/env bash
# deploy-vercel.sh — Deploy the Agentic RAG app to Vercel.
#
# Usage:
#   bash deploy-vercel.sh                                   # interactive mode selector
#   bash deploy-vercel.sh --fullstack                       # full-stack (frontend + backend serverless)
#   bash deploy-vercel.sh --frontend-only \                 # frontend only + separate backend
#       --backend-url https://my-backend.railway.app
#   bash deploy-vercel.sh --project-name my-rag-app        # custom project/CNAME
#   bash deploy-vercel.sh --preview                         # preview deployment
#   bash deploy-vercel.sh --yes                             # non-interactive (uses env vars)
#
# Environment variables (skip interactive prompts in CI / cloned repos):
#   ADMIN_PASSWORD      Admin login password
#   SECRET_KEY          JWT signing key (auto-generated if omitted)
#   PROJECT_NAME        Vercel project name / deployment CNAME
#   VERCEL_TOKEN        Vercel auth token (skip `vercel login`)
#   VERCEL_ORG_ID       Vercel org/team ID (skip `vercel link` prompts)
#   VERCEL_PROJECT_ID   Vercel project ID  (skip `vercel link` prompts)
#   BACKEND_URL         Backend URL for --frontend-only mode

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[deploy-vercel]${NC} $*"; }
success() { echo -e "${GREEN}[deploy-vercel] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[deploy-vercel] ⚠${NC} $*"; }
error()   { echo -e "${RED}[deploy-vercel] ✗${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VERCEL_JSON_FRONTEND="$FRONTEND_DIR/vercel.json"
VERCEL_JSON_FRONTEND_BAK="$FRONTEND_DIR/vercel.json.bak"

# ── Sample data generator ─────────────────────────────────────────────────────
# Usage: _sample_data_step <auto_yes>
_sample_data_step() {
    local auto_yes="$1"
    local sample_dir="$SCRIPT_DIR/sample-data"
    local default_topic="Generative AI and Agentic AI"

    # Prompt for topic
    local topic="$default_topic"
    if [[ "$auto_yes" == false ]]; then
        echo ""
        read -rp "  Topic for sample documents [$default_topic]: " _t
        [[ -n "$_t" ]] && topic="$_t"
    fi

    info "Generating sample documents — topic: \"$topic\""

    # Install optional deps quietly, then generate
    (
        [[ -f "$SCRIPT_DIR/backend/.venv/bin/activate" ]] && \
            source "$SCRIPT_DIR/backend/.venv/bin/activate" && \
            pip install -q reportlab openpyxl 2>/dev/null
    ) || true
    python3 "$sample_dir/generate_samples.py" --topic "$topic" 2>/dev/null || {
        warn "Could not generate sample files — check python3 is in PATH"
        return
    }

    echo ""
    info "Files generated in sample-data/. Upload them manually via the app UI."
}

# ── Full-stack deployment helper ──────────────────────────────────────────────
deploy_fullstack() {
    local prod_flag="$1" auto_yes="$2" project_name="$3"

    # Resolve project name
    if [[ -z "$project_name" ]]; then
        local root_link="$SCRIPT_DIR/.vercel/project.json"
        if [[ -f "$root_link" ]]; then
            project_name=$(python3 - "$root_link" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("projectName", ""))
except Exception:
    pass
PYEOF
) || true
        fi
    fi

    if [[ -z "$project_name" ]] && [[ "$auto_yes" == false ]]; then
        local default_name; default_name=$(basename "$SCRIPT_DIR")
        echo ""
        echo "  Enter a Vercel project name (letters, numbers, hyphens)."
        echo "  This becomes part of your deployment URL: <name>.vercel.app"
        echo ""
        read -rp "  Project name [$default_name]: " project_name
        project_name="${project_name:-$default_name}"
        echo ""
    fi
    project_name="${project_name:-$(basename "$SCRIPT_DIR")}"
    info "Project name: $project_name"

    # Collect required env vars
    # Note: OPENAI_API_KEY is intentionally NOT collected here.
    # Set it after first login via Settings → OpenAI API Key in the app UI.
    # This keeps the key out of the deployment pipeline and Vercel env var storage.
    # Production ignores billing-bearing provider env vars by design.
    echo ""
    info "Collecting required environment variables..."
    echo ""

    local admin_pw="${ADMIN_PASSWORD:-}"
    local admin_pw_generated=false
    if [[ -z "$admin_pw" ]] && [[ "$auto_yes" == false ]]; then
        echo "  Choose a password for the admin account (username: admin)."
        echo "  Press Enter to auto-generate a secure password."
        echo ""
        read -rsp "  ADMIN_PASSWORD (hidden, min 8 chars, Enter to generate): " admin_pw; echo ""; echo ""
    fi
    if [[ -z "$admin_pw" ]]; then
        admin_pw=$(openssl rand -base64 16 | tr -dc 'A-Za-z0-9!@#$%' | head -c 20)
        admin_pw_generated=true
        info "Auto-generated ADMIN_PASSWORD"
    fi
    [[ ${#admin_pw} -lt 8 ]] && die "ADMIN_PASSWORD must be at least 8 characters."

    local secret_key="${SECRET_KEY:-}"
    if [[ -z "$secret_key" ]]; then
        secret_key=$(openssl rand -hex 32)
        info "Auto-generated SECRET_KEY (stored encrypted in Vercel)"
    fi

    # Link project
    local root_link="$SCRIPT_DIR/.vercel/project.json"
    if [[ ! -f "$root_link" ]]; then
        info "Linking project to Vercel..."
        (cd "$SCRIPT_DIR" && vercel link --project "$project_name" --yes 2>&1) || \
        (cd "$SCRIPT_DIR" && vercel link --yes 2>&1)
    else
        local linked_name; linked_name=$(python3 - "$root_link" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("projectName", "?"))
except Exception:
    print("?")
PYEOF
) || linked_name="?"
        info "Project already linked: $linked_name"
    fi

    # Helper to set an env var
    set_env() {
        local name="$1" value="$2"
        (cd "$SCRIPT_DIR"
         vercel env rm "$name" production --yes 2>/dev/null || true
         printf '%s' "$value" | vercel env add "$name" production --yes 2>&1 | grep -vE "^Retrieving|^$"
        )
    }

    info "Setting environment variables..."
    set_env "SECRET_KEY"        "$secret_key"
    set_env "ADMIN_PASSWORD"    "$admin_pw"
    set_env "VECTOR_STORE_TYPE" "pinecone"
    set_env "FILE_STORE_TYPE"   "blob"
    set_env "APP_ENV"           "production"
    set_env "ADMIN_USERNAME"    "admin"
    success "Environment variables configured"
    warn "Production retrieval defaults to Pinecone. Add Pinecone settings in the app Settings UI or Vercel env vars before upload."

    # Deploy
    local deploy_type="production"; [[ -z "$prod_flag" ]] && deploy_type="preview"
    info "Deploying to Vercel ($deploy_type)..."
    echo ""

    # shellcheck disable=SC2086
    local deploy_out
    if ! deploy_out=$(cd "$SCRIPT_DIR" && vercel $prod_flag --yes 2>&1); then
        echo "$deploy_out"
        die "Vercel deploy failed (see output above)."
    fi
    echo "$deploy_out"

    local deployed_url
    deployed_url=$(echo "$deploy_out" | grep -oE 'https://[a-zA-Z0-9._-]+\.vercel\.app' | tail -1 || true)

    # Update ALLOWED_ORIGINS and redeploy
    if [[ -n "$deployed_url" ]]; then
        info "Updating ALLOWED_ORIGINS to: $deployed_url ..."
        set_env "ALLOWED_ORIGINS" "${deployed_url},http://localhost:5173,http://localhost:3000"
        info "Final redeploy to apply CORS settings..."
        # shellcheck disable=SC2086
        local redeploy_out
        if ! redeploy_out=$(cd "$SCRIPT_DIR" && vercel $prod_flag --yes 2>&1); then
            echo "$redeploy_out"
            die "Final Vercel redeploy failed after updating ALLOWED_ORIGINS (see output above)."
        fi
        echo "$redeploy_out" | tail -5
    fi

    echo ""
    echo "════════════════════════════════════════════════════════════"
    success "Full-stack deployment complete!"
    echo ""
    echo "  App URL         : ${deployed_url:-https://${project_name}.vercel.app}"
    echo "  API health      : ${deployed_url:-https://${project_name}.vercel.app}/api/health"
    echo "  Admin username  : admin"
    if [[ "$admin_pw_generated" == true ]]; then
    echo "  Admin password  : $admin_pw   ← SAVE THIS NOW"
    else
    echo "  Admin password  : (the password you entered)"
    fi
    echo ""
    echo "  ── Next step: set runtime keys ──────────────────────────"
    echo "  1. Open the app URL and sign in as admin."
    echo "  2. Click Settings (top-right) → paste your OpenAI API key."
    echo "  3. In Vector store (Pinecone), paste your Pinecone API key."
    echo "  4. Select the LLM model / Pinecone index, then Save."
    echo ""
    echo "  Provider keys and model/token cost controls are not read from"
    echo "  production environment variables. Use Settings UI after login."
    echo "  ─────────────────────────────────────────────────────────"
    echo ""
    echo "  NOTE: Pinecone stores vectors/chunks durably. For durable original"
    echo "  file previews/downloads, connect Vercel Blob and set FILE_STORE_TYPE=blob."
    echo ""
    echo "  To tear down this deployment:"
    echo "    bash undeploy-vercel.sh"
    echo "════════════════════════════════════════════════════════════"

    # Offer to generate sample documents
    if [[ "$auto_yes" == false ]]; then
        echo ""
        read -rp "  Generate sample documents now? [y/N]: " _want_samples; echo ""
        if [[ "$(echo "$_want_samples" | tr '[:upper:]' '[:lower:]')" =~ ^y ]]; then
            _sample_data_step "$auto_yes"
        fi
    fi
}

# ── Frontend-only deployment helper ──────────────────────────────────────────
deploy_frontend_only() {
    local prod_flag="$1" backend_url="$2"

    # Cleanup trap restores vercel.json
    cleanup() { [[ -f "$VERCEL_JSON_FRONTEND_BAK" ]] && mv "$VERCEL_JSON_FRONTEND_BAK" "$VERCEL_JSON_FRONTEND"; }
    trap cleanup EXIT

    if [[ -z "$backend_url" ]]; then
        echo ""
        warn "BACKEND_URL is required for --frontend-only mode."
        echo "  Enter the base URL of your deployed backend"
        echo "  (e.g. https://my-app.railway.app — no trailing slash, no /api suffix)."
        echo ""
        read -rp "  Enter backend URL: " backend_url; echo ""
    fi
    backend_url="${backend_url%/}"
    [[ ! "$backend_url" =~ ^https?:// ]] && die "BACKEND_URL must start with http:// or https://"

    info "Backend URL: $backend_url"
    local vite_api_url="${backend_url}/api"

    info "Patching frontend/vercel.json with backend URL..."
    [[ ! -f "$VERCEL_JSON_FRONTEND" ]] && die "frontend/vercel.json not found at: $VERCEL_JSON_FRONTEND"
    cp "$VERCEL_JSON_FRONTEND" "$VERCEL_JSON_FRONTEND_BAK"
    # Use Python to safely substitute the backend URL — avoids sed delimiter injection
    # when the URL contains special characters (OWASP A03).
    python3 - "$VERCEL_JSON_FRONTEND_BAK" "$VERCEL_JSON_FRONTEND" "$backend_url" <<'PYEOF'
import json, sys, re

src_path, dst_path, new_url = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src_path) as f:
    text = f.read()

# Replace the placeholder and any existing backend destination in rewrites
text = text.replace("https://your-backend-url.com", new_url)
text = re.sub(
    r'"destination":\s*"https://[^"]+(/api/\$1)"',
    f'"destination": "{new_url}\\1"',
    text,
)

with open(dst_path, "w") as f:
    f.write(text)
PYEOF
    success "vercel.json patched (will be restored on exit)"

    info "Setting VITE_API_URL=$vite_api_url ..."
    (
        cd "$FRONTEND_DIR"
        vercel env rm VITE_API_URL production --yes 2>/dev/null || true
        vercel env rm VITE_API_URL preview    --yes 2>/dev/null || true
        echo "$vite_api_url" | vercel env add VITE_API_URL production
        echo "$vite_api_url" | vercel env add VITE_API_URL preview
    )
    success "VITE_API_URL configured"

    local deploy_type="production"; [[ -z "$prod_flag" ]] && deploy_type="preview"
    info "Deploying frontend to Vercel ($deploy_type)..."
    echo ""

    # shellcheck disable=SC2086
    local deploy_out
    if ! deploy_out=$(cd "$FRONTEND_DIR" && vercel $prod_flag --yes 2>&1); then
        echo "$deploy_out"
        die "Vercel frontend deploy failed (see output above)."
    fi
    echo "$deploy_out"

    local deployed_url
    deployed_url=$(echo "$deploy_out" | grep -oE 'https://[a-zA-Z0-9._-]+\.vercel\.app' | tail -1 || true)

    echo ""
    echo "════════════════════════════════════════════════════════════"
    success "Frontend-only deployment complete!"
    echo ""
    [[ -n "$deployed_url" ]] && echo "  Frontend URL : $deployed_url"
    echo "  Backend URL  : $backend_url"
    echo "  API base     : $vite_api_url"
    echo ""
    echo "  To tear down:"
    echo "    bash undeploy-vercel.sh"
    echo "════════════════════════════════════════════════════════════"

    # Offer to generate sample documents
    echo ""
    read -rp "  Generate sample documents? [y/N]: " _want_samples; echo ""
    if [[ "$(echo "$_want_samples" | tr '[:upper:]' '[:lower:]')" =~ ^y ]]; then
        _sample_data_step false
    fi
}

# ═════════════════════════════════════════════════════════════════════════════
# ── Main ─────────────────────────────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════

# Parse arguments
PROD_FLAG="--prod"
DEPLOY_MODE="fullstack"
DEPLOY_MODE_SET=false   # true when the user supplied --fullstack or --frontend-only
BACKEND_URL="${BACKEND_URL:-}"
AUTO_YES=false
PROJECT_NAME="${PROJECT_NAME:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-name)     PROJECT_NAME="$2"; shift 2 ;;
        --project-name=*)   PROJECT_NAME="${1#*=}"; shift ;;
        --backend-url)      BACKEND_URL="$2"; DEPLOY_MODE="frontend-only"; DEPLOY_MODE_SET=true; shift 2 ;;
        --backend-url=*)    BACKEND_URL="${1#*=}"; DEPLOY_MODE="frontend-only"; DEPLOY_MODE_SET=true; shift ;;
        --frontend-only)    DEPLOY_MODE="frontend-only"; DEPLOY_MODE_SET=true; shift ;;
        --fullstack)        DEPLOY_MODE="fullstack";     DEPLOY_MODE_SET=true; shift ;;
        --preview)          PROD_FLAG=""; shift ;;
        --yes|-y)           AUTO_YES=true; shift ;;
        --help|-h)
            sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)
            die "Unknown option: $1 (run with --help for usage)" ;;
    esac
done

# ── Interactive mode selector ─────────────────────────────────────────────────
# Only shown when the user has not specified --fullstack or --frontend-only
# and has not passed --yes (non-interactive / CI mode).
if [[ "$DEPLOY_MODE_SET" == false ]] && [[ "$AUTO_YES" == false ]]; then
    echo ""
    echo -e "  Select a deployment mode:"
    echo ""
    echo "  1) Full-stack on Vercel (default)"
    echo "     • Frontend + FastAPI backend in one Vercel project"
    echo "     • In-memory vector store — documents lost on cold start"
    echo "     • 4 MB upload cap (Vercel serverless body limit)"
    echo "     • Best for: demos, sharing, quick evaluations"
    echo ""
    echo "  2) Frontend only on Vercel  (backend hosted separately)"
    echo "     • Static React build on Vercel CDN"
    echo "     • FastAPI backend on Railway / Render / Docker (persistent ChromaDB)"
    echo "     • Full 20 MB upload limit, documents survive restarts"
    echo "     • Best for: production, heavy document workloads"
    echo ""
    read -rp "  Choose [1/2] (default: 1): " _mode_choice; echo ""
    case "${_mode_choice:-1}" in
        2) DEPLOY_MODE="frontend-only" ;;
        *) DEPLOY_MODE="fullstack" ;;
    esac
fi

# ── Prerequisite checks ───────────────────────────────────────────────────────
echo ""
info "Checking prerequisites..."
echo ""

# 1. Git — needed to clone / identify project root
if ! command -v git &>/dev/null; then
    warn "git is not installed — you may need it to manage the project source."
    echo "  Install: https://git-scm.com/downloads"
fi

# 2. Python 3.11–3.13 — used for vercel.json patching and sample-data generation
PYTHON_OK=false
for py in python3.13 python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        PY_VER=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        PY_MAJ=${PY_VER%%.*}; PY_MIN=${PY_VER##*.}
        if [[ "$PY_MAJ" -eq 3 && "$PY_MIN" -ge 11 && "$PY_MIN" -le 13 ]]; then
            PYTHON3="$py"
            PYTHON_OK=true
            success "Python $PY_VER ($py)"
            break
        fi
    fi
done
if [[ "$PYTHON_OK" == false ]]; then
    warn "Python 3.11–3.13 not found (used for vercel.json patching and sample data)."
    echo "  Install from https://www.python.org/downloads/"
    echo "  macOS:   brew install python@3.13"
    echo "  Ubuntu:  sudo apt install python3.13"
    PYTHON3="python3"   # fall back; patching may fail gracefully
fi

# 3. Node.js 20+
if ! command -v node &>/dev/null; then
    echo ""
    error "Node.js is not installed."
    echo "  Install from https://nodejs.org/ (v20+ recommended)"
    echo "  macOS:   brew install node"
    echo "  Ubuntu:  sudo apt install nodejs npm"
    echo ""
    exit 1
fi
NODE_VER=$(node --version 2>/dev/null | tr -d 'v')
NODE_MAJOR="${NODE_VER%%.*}"
if [[ "$NODE_MAJOR" -lt 20 ]]; then
    warn "Node.js $NODE_VER is installed — v20+ recommended."
    echo "  Upgrade: https://nodejs.org/"
else
    success "Node.js v$NODE_VER"
fi

# 4. npm
if ! command -v npm &>/dev/null; then
    die "npm is not installed. It ships with Node.js — reinstall Node.js from https://nodejs.org/"
fi
success "npm $(npm --version 2>/dev/null)"

# 5. Vercel CLI — install automatically if Node ≥ 20 and user consents
if ! command -v vercel &>/dev/null; then
    echo ""
    warn "Vercel CLI is not installed."
    echo ""
    echo "  The Vercel CLI is required to deploy. It can be installed globally with npm:"
    echo "    npm install -g vercel"
    echo ""
    echo "  Alternatively (macOS with Homebrew):"
    echo "    brew install vercel-cli"
    echo ""
    if [[ "$AUTO_YES" == false ]]; then
        read -rp "  Install Vercel CLI now with 'npm install -g vercel'? [Y/n]: " _install_vercel; echo ""
        if [[ "$(echo "$_install_vercel" | tr '[:upper:]' '[:lower:]')" != "n" ]]; then
            npm install -g vercel
        else
            die "Vercel CLI required. Install it and re-run: npm install -g vercel"
        fi
    else
        # CI / non-interactive — auto-install
        npm install -g vercel
    fi
fi
success "Vercel CLI: $(vercel --version 2>/dev/null | head -1)"

# 6. Vercel authentication
if ! vercel whoami &>/dev/null; then
    echo ""
    warn "Not logged in to Vercel."
    echo ""
    echo "  You need a free Vercel account: https://vercel.com/signup"
    echo "  Then log in with:"
    echo "    vercel login"
    echo ""
    echo "  For CI deployments without browser login, set VERCEL_TOKEN:"
    echo "    export VERCEL_TOKEN=<your-token>   # from vercel.com → Settings → Tokens"
    echo ""
    if [[ "$AUTO_YES" == false ]]; then
        read -rp "  Run 'vercel login' now? [Y/n]: " _do_login; echo ""
        if [[ "$(echo "$_do_login" | tr '[:upper:]' '[:lower:]')" != "n" ]]; then
            vercel login
        else
            die "Login required. Run: vercel login"
        fi
    else
        die "VERCEL_TOKEN env var is required for non-interactive deploys. Set it and re-run."
    fi
fi
success "Logged in as: $(vercel whoami 2>/dev/null)"

# Route to the correct deployment function
echo ""
info "Deployment mode: $DEPLOY_MODE"
echo ""

if [[ "$DEPLOY_MODE" == "fullstack" ]]; then
    deploy_fullstack "$PROD_FLAG" "$AUTO_YES" "$PROJECT_NAME"
else
    deploy_frontend_only "$PROD_FLAG" "$BACKEND_URL"
fi
