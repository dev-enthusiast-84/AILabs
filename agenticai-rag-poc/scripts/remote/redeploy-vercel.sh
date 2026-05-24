#!/usr/bin/env bash
# redeploy-vercel.sh — Refresh a running Agentic RAG Vercel deployment.
#
# Usage:
#   bash redeploy-vercel.sh                          # prompt for env vars, then redeploy (default)
#   bash redeploy-vercel.sh --code                   # redeploy code only (skip env prompts)
#   bash redeploy-vercel.sh --env                    # rotate env vars only, then redeploy
#   bash redeploy-vercel.sh --all                    # update env vars AND redeploy code
#   bash redeploy-vercel.sh --preview                # deploy to preview instead of production
#   bash redeploy-vercel.sh --frontend-only \        # redeploy frontend-only Vercel project
#       --backend-url https://my-backend.railway.app
#   bash redeploy-vercel.sh --sample-data            # generate sample docs after redeploy
#   bash redeploy-vercel.sh --sample-topic "Healthcare Policy"
#   bash redeploy-vercel.sh --yes                    # non-interactive / CI (code-only, no prompts)
#   bash redeploy-vercel.sh --project-name my-app   # target a specific project
#
# What it does (by mode):
#   default (all)   Prompts for ADMIN_PASSWORD, SECRET_KEY, ALLOWED_ORIGINS (Enter to skip
#                   each), then redeploys code.  Press Enter through all prompts to leave
#                   everything unchanged and just push new code.
#   --code          Re-runs `vercel --prod` from the current working tree.
#                   Env vars are left untouched.  Use for quick code-only pushes.
#   --env           Rotate env vars only, then redeploy (same prompts as default).
#   --all           Alias for the default interactive behaviour.
#
# Shortcut flags (set a single env var without interactive prompts):
#   --admin-password <pw>    Rotate ADMIN_PASSWORD
#   --secret-key <key>       Rotate SECRET_KEY
#   --allowed-origins <val>  Update ALLOWED_ORIGINS (comma-separated URLs)
#   --openai-key <key>       Deprecated and ignored; use Settings UI
#   --pinecone-key <key>     Deprecated and ignored; use Settings UI
#
# Environment variables (skip interactive prompts in CI):
#   ADMIN_PASSWORD      New admin password
#   SECRET_KEY          New JWT signing key
#   ALLOWED_ORIGINS     New CORS origin list
#   OPENAI_API_KEY      Ignored by this script; enter through Settings UI
#   PINECONE_API_KEY    Ignored by this script; enter through Settings UI
#   PINECONE_INDEX_NAME Pinecone index name (default: agenticai-rag-poc-documents)
#   PINECONE_NAMESPACE  Pinecone namespace (default: agenticai-rag-poc)
#   PINECONE_CLOUD      Pinecone serverless cloud (default: aws)
#   PINECONE_REGION     Pinecone serverless region (default: us-east-1)
#   VERCEL_TOKEN        Vercel auth token
#   VERCEL_ORG_ID       Vercel org/team ID
#   VERCEL_PROJECT_ID   Vercel project ID
#   BACKEND_URL         Backend URL for --frontend-only mode
#   SAMPLE_TOPIC        Topic for generated sample documents

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[redeploy-vercel]${NC} $*"; }
success() { echo -e "${GREEN}[redeploy-vercel] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[redeploy-vercel] ⚠${NC} $*"; }
error()   { echo -e "${RED}[redeploy-vercel] ✗${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VERCEL_JSON_FRONTEND="$FRONTEND_DIR/vercel.json"
VERCEL_JSON_FRONTEND_BAK="$FRONTEND_DIR/vercel.json.bak"

# ── Sample data generator ─────────────────────────────────────────────────────
# Usage: _sample_data_step <auto_yes> [topic]
_sample_data_step() {
    local auto_yes="$1"
    local topic="${2:-${SAMPLE_TOPIC:-}}"
    local sample_dir="$SCRIPT_DIR/sample-data"
    local default_topic="Generative AI and Agentic AI"

    topic="${topic:-$default_topic}"
    if [[ "$auto_yes" == false && "$topic" == "$default_topic" ]]; then
        echo ""
        read -rp "  Topic for sample documents [$default_topic]: " _t
        [[ -n "$_t" ]] && topic="$_t"
    fi

    info "Generating sample documents — topic: \"$topic\""
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

_offer_sample_data() {
    local auto_yes="$1"
    local topic="${2:-${SAMPLE_TOPIC:-}}"

    if [[ "$GENERATE_SAMPLE_DATA" == true ]]; then
        _sample_data_step "$auto_yes" "$topic"
        return
    fi

    if [[ "$auto_yes" == false ]]; then
        echo ""
        read -rp "  Generate sample documents now? [y/N]: " _want_samples; echo ""
        if [[ "$(echo "$_want_samples" | tr '[:upper:]' '[:lower:]')" =~ ^y ]]; then
            _sample_data_step "$auto_yes" "$topic"
        fi
    fi
}

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="all"            # all (default) | code | env
PROD_FLAG="--prod"
AUTO_YES=false
PROJECT_NAME="${PROJECT_NAME:-}"
DEPLOY_MODE="fullstack"
DEPLOY_MODE_SET=false
BACKEND_URL="${BACKEND_URL:-}"
TARGET_DIR="$SCRIPT_DIR"
GENERATE_SAMPLE_DATA=false
SAMPLE_TOPIC="${SAMPLE_TOPIC:-}"

# Shortcut env overrides (empty = not provided via flag)
FLAG_ADMIN_PW=""
FLAG_SECRET_KEY=""
FLAG_ALLOWED_ORIGINS=""
FLAG_OPENAI_KEY=""
FLAG_PINECONE_KEY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --code)                 MODE="code"; shift ;;
        --env)                  MODE="env"; shift ;;
        --all)                  MODE="all"; shift ;;
        --preview)              PROD_FLAG=""; shift ;;
        --frontend-only|--frontonly) DEPLOY_MODE="frontend-only"; DEPLOY_MODE_SET=true; shift ;;
        --fullstack)            DEPLOY_MODE="fullstack"; DEPLOY_MODE_SET=true; shift ;;
        --backend-url)          BACKEND_URL="$2"; DEPLOY_MODE="frontend-only"; DEPLOY_MODE_SET=true; shift 2 ;;
        --backend-url=*)        BACKEND_URL="${1#*=}"; DEPLOY_MODE="frontend-only"; DEPLOY_MODE_SET=true; shift ;;
        --sample-data|--generate-sample-data) GENERATE_SAMPLE_DATA=true; shift ;;
        --sample-topic)         SAMPLE_TOPIC="$2"; GENERATE_SAMPLE_DATA=true; shift 2 ;;
        --sample-topic=*)       SAMPLE_TOPIC="${1#*=}"; GENERATE_SAMPLE_DATA=true; shift ;;
        --yes|-y)               AUTO_YES=true; shift ;;
        --project-name)         PROJECT_NAME="$2"; shift 2 ;;
        --project-name=*)       PROJECT_NAME="${1#*=}"; shift ;;
        --admin-password)       FLAG_ADMIN_PW="$2"; shift 2 ;;
        --admin-password=*)     FLAG_ADMIN_PW="${1#*=}"; shift ;;
        --secret-key)           FLAG_SECRET_KEY="$2"; shift 2 ;;
        --secret-key=*)         FLAG_SECRET_KEY="${1#*=}"; shift ;;
        --allowed-origins)      FLAG_ALLOWED_ORIGINS="$2"; shift 2 ;;
        --allowed-origins=*)    FLAG_ALLOWED_ORIGINS="${1#*=}"; shift ;;
        --openai-key)           FLAG_OPENAI_KEY="$2"; shift 2 ;;
        --openai-key=*)         FLAG_OPENAI_KEY="${1#*=}"; shift ;;
        --pinecone-key)         FLAG_PINECONE_KEY="$2"; shift 2 ;;
        --pinecone-key=*)       FLAG_PINECONE_KEY="${1#*=}"; shift ;;
        --help|-h)
            sed -n '2,47p' "${BASH_SOURCE[0]}" | sed 's/^#[[:space:]]\?//'; exit 0 ;;
        *)
            die "Unknown option: $1 (run with --help for usage)" ;;
    esac
done

# --yes with no explicit mode → code-only (non-interactive CI redeploy)
if [[ "$AUTO_YES" == true && "$MODE" == "all" ]]; then
    MODE="code"
fi

if [[ "$DEPLOY_MODE" == "frontend-only" && "$MODE" == "env" ]]; then
    MODE="all"
fi

# ── 1. Pre-flight checks ──────────────────────────────────────────────────────
if ! command -v vercel &>/dev/null; then
    error "Vercel CLI is not installed."
    echo "  Install: npm install -g vercel"
    exit 1
fi
success "Vercel CLI: $(vercel --version 2>/dev/null | head -1)"

if ! vercel whoami &>/dev/null; then
    die "Not logged in to Vercel. Run: vercel login"
fi
success "Logged in as: $(vercel whoami 2>/dev/null)"

# ── 2. Resolve project name ───────────────────────────────────────────────────
_read_json_field() {
    local file="$1" field="$2"
    # Pass args via argv — never interpolated into the script string (OWASP A03)
    python3 - "$file" "$field" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get(sys.argv[2], ""))
except Exception:
    pass
PYEOF
}

ROOT_LINK="$SCRIPT_DIR/.vercel/project.json"
FRONTEND_LINK="$FRONTEND_DIR/.vercel/project.json"
ROOT_PROJECT=""
FRONTEND_PROJECT=""
[[ -f "$ROOT_LINK" ]] && ROOT_PROJECT=$(_read_json_field "$ROOT_LINK" "projectName")
[[ -f "$FRONTEND_LINK" ]] && FRONTEND_PROJECT=$(_read_json_field "$FRONTEND_LINK" "projectName")

_use_root_project() {
    PROJECT_NAME="$ROOT_PROJECT"
    TARGET_DIR="$SCRIPT_DIR"
    [[ -n "$PROJECT_NAME" ]] && info "Detected full-stack project from root/.vercel: $PROJECT_NAME"
}

_use_frontend_project() {
    PROJECT_NAME="$FRONTEND_PROJECT"
    TARGET_DIR="$FRONTEND_DIR"
    [[ -n "$PROJECT_NAME" ]] && info "Detected frontend-only project from frontend/.vercel: $PROJECT_NAME"
}

if [[ -z "$PROJECT_NAME" ]]; then
    case "$DEPLOY_MODE" in
        frontend-only)
            [[ -z "$FRONTEND_PROJECT" ]] && die "No frontend-only Vercel link found at frontend/.vercel/project.json"
            _use_frontend_project
            ;;
        fullstack)
            if [[ "$DEPLOY_MODE_SET" == true ]]; then
                [[ -z "$ROOT_PROJECT" ]] && die "No full-stack Vercel link found at .vercel/project.json"
                _use_root_project
            elif [[ -n "$ROOT_PROJECT" && -n "$FRONTEND_PROJECT" && "$ROOT_PROJECT" != "$FRONTEND_PROJECT" ]]; then
                if [[ "$AUTO_YES" == true ]]; then
                    die "Both full-stack ('$ROOT_PROJECT') and frontend-only ('$FRONTEND_PROJECT') links exist. Re-run with --fullstack or --frontend-only."
                fi

                echo ""
                warn "Multiple Vercel projects are linked locally."
                echo "  1) Full-stack    : $ROOT_PROJECT"
                echo "  2) Frontend-only : $FRONTEND_PROJECT"
                echo ""
                read -rp "  Which project should be redeployed? [1/2]: " _choice; echo ""
                case "${_choice:-}" in
                    2) DEPLOY_MODE="frontend-only"; _use_frontend_project ;;
                    1) _use_root_project ;;
                    *) die "Invalid selection. Aborting." ;;
                esac
            elif [[ -n "$ROOT_PROJECT" ]]; then
                _use_root_project
            elif [[ -n "$FRONTEND_PROJECT" ]]; then
                DEPLOY_MODE="frontend-only"
                _use_frontend_project
            fi
            ;;
    esac
else
    if [[ "$DEPLOY_MODE" == "frontend-only" ]]; then
        TARGET_DIR="$FRONTEND_DIR"
    fi
fi

if [[ -z "$PROJECT_NAME" ]] && [[ "$AUTO_YES" == false ]]; then
    echo ""
    warn "Could not auto-detect the Vercel project name."
    echo "  Find it at: https://vercel.com/dashboard  or run: vercel ls"
    echo ""
    read -rp "  Enter Vercel project name: " PROJECT_NAME; echo ""
fi

[[ -z "$PROJECT_NAME" ]] && die "No project name resolved. Aborting."
info "Project: $PROJECT_NAME"
info "Deployment mode: $DEPLOY_MODE"

# ── Helper: set or rotate a single env var ───────────────────────────────────
_set_env() {
    local name="$1" value="$2"
    (cd "$TARGET_DIR"
     vercel env rm "$name" production --yes 2>/dev/null || true
     printf '%s' "$value" | vercel env add "$name" production --yes 2>&1 \
         | grep -vE "^Retrieving|^$"
    )
}

_set_env_scope() {
    local name="$1" value="$2" scope="$3"
    (cd "$TARGET_DIR"
     vercel env rm "$name" "$scope" --yes 2>/dev/null || true
     printf '%s' "$value" | vercel env add "$name" "$scope" --yes 2>&1 \
         | grep -vE "^Retrieving|^$"
    )
}

_patch_frontend_vercel_json() {
    local backend_url="$1"
    [[ -f "$VERCEL_JSON_FRONTEND" ]] || die "frontend/vercel.json not found at: $VERCEL_JSON_FRONTEND"
    cp "$VERCEL_JSON_FRONTEND" "$VERCEL_JSON_FRONTEND_BAK"
    python3 - "$VERCEL_JSON_FRONTEND_BAK" "$VERCEL_JSON_FRONTEND" "$backend_url" <<'PYEOF'
import re
import sys

src_path, dst_path, new_url = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src_path) as f:
    text = f.read()

text = text.replace("https://your-backend-url.com", new_url)
text = re.sub(
    r'"destination":\s*"https://[^"]+(/api/\$1)"',
    f'"destination": "{new_url}\\1"',
    text,
)

with open(dst_path, "w") as f:
    f.write(text)
PYEOF
}

redeploy_frontend_only() {
    local backend_url="$1"

    cleanup() { [[ -f "$VERCEL_JSON_FRONTEND_BAK" ]] && mv "$VERCEL_JSON_FRONTEND_BAK" "$VERCEL_JSON_FRONTEND"; }
    trap cleanup EXIT

    if [[ -z "$backend_url" ]] && [[ "$AUTO_YES" == false ]]; then
        echo ""
        warn "BACKEND_URL is required to refresh frontend-only rewrites/env."
        echo "  Enter the base URL of your deployed backend"
        echo "  (e.g. https://my-app.railway.app — no trailing slash, no /api suffix)."
        echo ""
        read -rp "  Enter backend URL: " backend_url; echo ""
    fi

    if [[ -n "$backend_url" ]]; then
        backend_url="${backend_url%/}"
        [[ ! "$backend_url" =~ ^https?:// ]] && die "BACKEND_URL must start with http:// or https://"

        local vite_api_url="${backend_url}/api"
        info "Backend URL: $backend_url"
        info "Patching frontend/vercel.json with backend URL..."
        _patch_frontend_vercel_json "$backend_url"
        success "vercel.json patched (will be restored on exit)"

        info "Setting VITE_API_URL=$vite_api_url ..."
        _set_env_scope "VITE_API_URL" "$vite_api_url" "production"
        _set_env_scope "VITE_API_URL" "$vite_api_url" "preview"
        success "VITE_API_URL configured"
    elif [[ "$AUTO_YES" == true && "$MODE" != "code" ]]; then
        die "BACKEND_URL is required for non-interactive frontend-only env redeploys."
    else
        warn "No BACKEND_URL provided; redeploying frontend code without changing VITE_API_URL or rewrites."
    fi

    deploy_type="production"; [[ -z "$PROD_FLAG" ]] && deploy_type="preview"
    echo ""
    info "Deploying frontend to Vercel ($deploy_type)…"
    echo ""

    # shellcheck disable=SC2086
    deploy_out=$(cd "$FRONTEND_DIR" && vercel $PROD_FLAG --yes 2>&1) || {
        echo "$deploy_out"
        die "Vercel frontend deploy failed (see output above)."
    }
    echo "$deploy_out"

    deployed_url=$(echo "$deploy_out" | grep -oE 'https://[a-zA-Z0-9._-]+\.vercel\.app' | tail -1 || true)

    echo ""
    echo "════════════════════════════════════════════════════════════"
    success "Frontend-only redeploy complete!"
    echo ""
    [[ -n "$deployed_url" ]] && echo "  Frontend URL : $deployed_url"
    [[ -n "$backend_url" ]] && echo "  Backend URL  : $backend_url"
    [[ -n "${vite_api_url:-}" ]] && echo "  API base     : $vite_api_url"
    echo ""
    echo "  To tear down:  bash undeploy-vercel.sh --frontend-only"
    echo "  To redeploy:   bash redeploy-vercel.sh --frontend-only --backend-url <url>"
    echo "════════════════════════════════════════════════════════════"

    _offer_sample_data "$AUTO_YES" "$SAMPLE_TOPIC"
}

if [[ "$DEPLOY_MODE" == "frontend-only" ]]; then
    redeploy_frontend_only "$BACKEND_URL"
    exit 0
fi

# ── 3. Optional env var rotation ─────────────────────────────────────────────
if [[ "$MODE" == "env" || "$MODE" == "all" ]]; then
    echo ""
    info "── Env var rotation ─────────────────────────────────────────────────"

    # ADMIN_PASSWORD
    local_pw="${FLAG_ADMIN_PW:-${ADMIN_PASSWORD:-}}"
    admin_pw_generated=false
    if [[ -z "$local_pw" ]] && [[ "$AUTO_YES" == false ]]; then
        echo ""
        echo "  Rotate ADMIN_PASSWORD? Press Enter to keep existing, 'gen' to auto-generate."
        read -rsp "  New ADMIN_PASSWORD (hidden, Enter to skip, 'gen' to generate): " local_pw; echo ""; echo ""
    fi
    if [[ "$local_pw" == "gen" ]]; then
        local_pw=$(openssl rand -base64 16 | tr -dc 'A-Za-z0-9!@#$%' | head -c 20)
        admin_pw_generated=true
        info "Auto-generated new ADMIN_PASSWORD"
    fi
    if [[ -n "$local_pw" ]]; then
        [[ ${#local_pw} -lt 8 ]] && die "ADMIN_PASSWORD must be at least 8 characters."
        _set_env "ADMIN_PASSWORD" "$local_pw"
        success "ADMIN_PASSWORD updated"
    else
        info "ADMIN_PASSWORD unchanged"
    fi

    # SECRET_KEY
    local_sk="${FLAG_SECRET_KEY:-${SECRET_KEY:-}}"
    if [[ -z "$local_sk" ]] && [[ "$AUTO_YES" == false ]]; then
        echo "  Rotate SECRET_KEY? Press Enter to keep existing (auto-generate new one with 'gen')."
        read -rp "  New SECRET_KEY (Enter to skip, 'gen' to auto-generate): " local_sk; echo ""
    fi
    if [[ "$local_sk" == "gen" ]]; then
        local_sk=$(openssl rand -hex 32)
        info "Auto-generated new SECRET_KEY"
    fi
    if [[ -n "$local_sk" ]]; then
        [[ ${#local_sk} -lt 32 ]] && die "SECRET_KEY must be at least 32 characters."
        _set_env "SECRET_KEY" "$local_sk"
        success "SECRET_KEY updated"
        warn "Rotating SECRET_KEY invalidates all existing JWT sessions."
    else
        info "SECRET_KEY unchanged"
    fi

    # ALLOWED_ORIGINS
    local_origins="${FLAG_ALLOWED_ORIGINS:-${ALLOWED_ORIGINS:-}}"
    if [[ -z "$local_origins" ]] && [[ "$AUTO_YES" == false ]]; then
        echo "  Update ALLOWED_ORIGINS? Press Enter to keep existing."
        read -rp "  New ALLOWED_ORIGINS (comma-separated URLs, Enter to skip): " local_origins; echo ""
    fi
    if [[ -n "$local_origins" ]]; then
        _set_env "ALLOWED_ORIGINS" "$local_origins"
        success "ALLOWED_ORIGINS updated"
    else
        info "ALLOWED_ORIGINS unchanged"
    fi

    # Provider credentials are intentionally not written to Vercel env.
    # Production reads OpenAI/Pinecone/Blob/LangSmith values from Settings UI.
    local_oai="${FLAG_OPENAI_KEY:-${OPENAI_API_KEY:-}}"
    if [[ -n "$local_oai" ]]; then
        warn "OPENAI_API_KEY input ignored; production provider keys must be entered in Settings UI"
    fi

    # Pinecone is the production default vector store. Persist optional Pinecone
    # settings when supplied; otherwise the app Settings UI can collect them.
    _set_env "VECTOR_STORE_TYPE" "pinecone"
    success "VECTOR_STORE_TYPE set to pinecone"
    _set_env "FILE_STORE_TYPE" "blob"
    success "FILE_STORE_TYPE set to blob"

    local_pc="${FLAG_PINECONE_KEY:-${PINECONE_API_KEY:-}}"
    if [[ -n "$local_pc" ]]; then
        warn "PINECONE_API_KEY input ignored; production provider keys must be entered in Settings UI"
    fi
    if [[ -n "${PINECONE_INDEX_NAME:-}" ]]; then
        _set_env "PINECONE_INDEX_NAME" "$PINECONE_INDEX_NAME"
        success "PINECONE_INDEX_NAME updated"
    fi
    if [[ -n "${PINECONE_NAMESPACE:-}" ]]; then
        _set_env "PINECONE_NAMESPACE" "$PINECONE_NAMESPACE"
        success "PINECONE_NAMESPACE updated"
    fi
    if [[ -n "${PINECONE_CLOUD:-}" ]]; then
        _set_env "PINECONE_CLOUD" "$PINECONE_CLOUD"
        success "PINECONE_CLOUD updated"
    fi
    if [[ -n "${PINECONE_REGION:-}" ]]; then
        _set_env "PINECONE_REGION" "$PINECONE_REGION"
        success "PINECONE_REGION updated"
    fi

    echo ""
fi

# ── 4. Code redeploy ──────────────────────────────────────────────────────────
deploy_type="production"; [[ -z "$PROD_FLAG" ]] && deploy_type="preview"
echo ""
info "Deploying to Vercel ($deploy_type)…"
echo ""

# shellcheck disable=SC2086
deploy_out=$(cd "$SCRIPT_DIR" && vercel $PROD_FLAG --yes 2>&1) || {
    echo "$deploy_out"
    die "Vercel deploy failed (see output above)."
}
echo "$deploy_out"

deployed_url=$(echo "$deploy_out" | grep -oE 'https://[a-zA-Z0-9._-]+\.vercel\.app' | tail -1 || true)

# ── 5. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
success "Redeploy complete!"
echo ""
if [[ -n "$deployed_url" ]]; then
    echo "  App URL    : $deployed_url"
    echo "  API health : $deployed_url/api/health"
else
    echo "  App URL    : https://${PROJECT_NAME}.vercel.app"
    echo "  API health : https://${PROJECT_NAME}.vercel.app/api/health"
fi
echo ""

if [[ "$MODE" == "env" || "$MODE" == "all" ]]; then
    if [[ -n "${local_pw:-}" ]]; then
        if [[ "${admin_pw_generated:-false}" == true ]]; then
            echo "  Admin password : $local_pw   ← SAVE THIS NOW (auto-generated)"
        else
            echo "  Admin password : (the password you entered)"
        fi
    fi
    if [[ -n "${local_sk:-}" && "$local_sk" != "gen" ]]; then
        echo "  NOTE: SECRET_KEY rotated — all existing sessions have been invalidated."
    fi
    echo ""
fi

echo "  To set the OpenAI key:"
echo "    1. Sign in as admin"
echo "    2. Click Settings → paste your OpenAI API key → Save"
echo "  To set Pinecone for production storage:"
echo "    Settings → Vector store (Pinecone) → paste Pinecone API key → Save"
echo ""
echo "  To tear down:  bash undeploy-vercel.sh"
echo "  To redeploy:   bash redeploy-vercel.sh"
echo "════════════════════════════════════════════════════════════"

_offer_sample_data "$AUTO_YES" "$SAMPLE_TOPIC"
