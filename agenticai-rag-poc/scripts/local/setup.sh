#!/usr/bin/env bash
# setup.sh — One-command local development setup for Agentic RAG.
#
# Usage:
#   bash setup.sh            # interactive (prompts for admin password)
#   bash setup.sh --yes      # non-interactive (auto-generate all secrets)
#
# Environment variables (skip interactive prompts in CI):
#   ADMIN_PASSWORD   Admin login password (auto-generated if omitted)
#   SECRET_KEY       JWT signing key (auto-generated if omitted)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
bold()    { printf '\033[1m%s\033[0m\n' "$*"; }
cyan()    { printf '\033[0;36m%s\033[0m\n' "$*"; }
green()   { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow()  { printf '\033[0;33m%s\033[0m\n' "$*"; }
red()     { printf '\033[0;31m%s\033[0m\n' "$*"; }

# ── Argument parsing ──────────────────────────────────────────────────────────
AUTO_YES=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)   AUTO_YES=true; shift ;;
        --help|-h)
            sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        *)
            red "Unknown option: $1 (use --yes for non-interactive mode)"; exit 1 ;;
    esac
done

bold "============================================================"
bold " Agentic RAG — Local Setup"
bold "============================================================"
echo ""

# ── 1. Python version detection (requires 3.11–3.13) ─────────────────────────
#
# Python 3.14+ does not yet have pre-built wheels for several dependencies
# (pydantic-core, bcrypt, etc.).  The script tries python3.13, python3.12,
# python3.11, then falls back to whatever `python3` is — stopping with a
# clear error if the resolved version is outside the supported range.
# ─────────────────────────────────────────────────────────────────────────────

find_python() {
    for cmd in python3.13 python3.12 python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            local major="${ver%%.*}"
            local minor="${ver##*.}"
            if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ] && [ "$minor" -le 13 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

cyan "Detecting Python version (required: 3.11 – 3.13)..."
if ! PYTHON=$(find_python); then
    echo ""
    red  "  ERROR: No compatible Python found (3.11–3.13 required)."
    echo ""
    echo "  Python 3.14+ does not yet have pre-built binary wheels for"
    echo "  several dependencies used by this project (pydantic-core,"
    echo "  bcrypt, etc.)."
    echo ""
    echo "  Install Python 3.13 and re-run:"
    echo "    macOS (Homebrew):  brew install python@3.13"
    echo "    Ubuntu/Debian:     sudo apt install python3.13 python3.13-venv"
    echo "    Windows:           https://www.python.org/downloads/release/python-3130/"
    echo ""
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1)
green "  Using: $PY_VER  ($PYTHON)"
echo ""

# ── 2. Backend virtual environment ───────────────────────────────────────────
cyan "Setting up Python virtual environment..."
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
    "$PYTHON" -m venv .venv
    green "  Created .venv ($(${PYTHON} --version 2>&1))"
else
    yellow "  .venv already exists — skipping (delete it to rebuild)"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

cyan "Installing backend dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements-dev.txt
green "  Backend dependencies installed"

# ── 3. Backend .env ───────────────────────────────────────────────────────────

# Write a single key=value into .env (preserves all other lines)
_write_env_key() {
    local key="$1" value="$2"
    KEY="$key" VALUE="$value" "$PYTHON" - <<'PYEOF'
import os, re, pathlib
key, value = os.environ['KEY'], os.environ['VALUE']
p = pathlib.Path('.env')
content = p.read_text()
if re.search(rf'^{re.escape(key)}=', content, re.MULTILINE):
    content = re.sub(rf'^{re.escape(key)}=.*$', f'{key}={value}', content, flags=re.MULTILINE)
else:
    content = content.rstrip('\n') + f'\n{key}={value}\n'
p.write_text(content)
PYEOF
}

# Generates a 16-char cryptographically random password
_gen_password() {
    "$PYTHON" -c "
import secrets, string
chars = string.ascii_letters + string.digits + '!@#%^&*'
print(''.join(secrets.choice(chars) for _ in range(16)))
"
}

# Generate a 64-hex-char secret key (equivalent to openssl rand -hex 32)
_gen_secret_key() {
    if command -v openssl &>/dev/null; then
        openssl rand -hex 32
    else
        "$PYTHON" -c "import secrets; print(secrets.token_hex(32))"
    fi
}

# ── Interactive credential collection (mirrors deploy-vercel.sh) ──────────────
echo ""
bold "------------------------------------------------------------"
bold " Credentials"
bold "------------------------------------------------------------"
echo ""

ADMIN_PASS="${ADMIN_PASSWORD:-}"
ADMIN_PASS_GENERATED=false
SECRET_KEY_VAL="${SECRET_KEY:-}"
NEW_ENV=false

if [ ! -f ".env" ]; then
    cp .env.example .env
    NEW_ENV=true
fi

# --- ADMIN_PASSWORD ---
if [ -z "$ADMIN_PASS" ]; then
    # Check if already set in an existing .env
    EXISTING_PW=$(grep -E "^ADMIN_PASSWORD=.+" .env 2>/dev/null | cut -d'=' -f2- || true)
    if [ -n "$EXISTING_PW" ]; then
        ADMIN_PASS="$EXISTING_PW"
        yellow "  ADMIN_PASSWORD already set in backend/.env — keeping existing value."
    elif [ "$AUTO_YES" == false ]; then
        echo "  Choose a password for the admin account (username: admin)."
        echo "  Press Enter to auto-generate a secure password."
        echo ""
        read -rsp "  ADMIN_PASSWORD (hidden, min 8 chars, Enter to generate): " ADMIN_PASS; echo ""; echo ""
    fi
fi

if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$(_gen_password)
    ADMIN_PASS_GENERATED=true
    green "  Auto-generated ADMIN_PASSWORD"
elif [ ${#ADMIN_PASS} -lt 8 ]; then
    red "  ERROR: ADMIN_PASSWORD must be at least 8 characters."; exit 1
fi
_write_env_key "ADMIN_PASSWORD" "$ADMIN_PASS"

# --- SECRET_KEY ---
# Check if a real key already exists (not the placeholder and not empty)
EXISTING_SK=$(grep -E "^SECRET_KEY=" .env 2>/dev/null | cut -d'=' -f2- || true)
PLACEHOLDER="<generate with: openssl rand -hex 32>"
if [ -z "$SECRET_KEY_VAL" ]; then
    if [ -n "$EXISTING_SK" ] && [ "$EXISTING_SK" != "$PLACEHOLDER" ] && [ ${#EXISTING_SK} -ge 32 ]; then
        SECRET_KEY_VAL="$EXISTING_SK"
        yellow "  SECRET_KEY already configured in backend/.env — keeping existing value."
    fi
fi
if [ -z "$SECRET_KEY_VAL" ] || [ "$SECRET_KEY_VAL" == "$PLACEHOLDER" ] || [ ${#SECRET_KEY_VAL} -lt 32 ]; then
    SECRET_KEY_VAL=$(_gen_secret_key)
    _write_env_key "SECRET_KEY" "$SECRET_KEY_VAL"
    green "  Generated SECRET_KEY (stored in backend/.env)"
fi

if [ "$NEW_ENV" == true ]; then
    green "  Created backend/.env"
    echo ""
    yellow "  ⚠  ACTION REQUIRED: open backend/.env and set your OPENAI_API_KEY"
fi

# ── 4. Git pre-commit hook — strict secrets audit ────────────────────────────
# Install the comprehensive pre-commit scanner from scripts/pre-commit.
# The hook blocks .env files, real API keys, hardcoded secret keys, and other
# sensitive data patterns from being committed (OWASP A02 — secret management).
_install_git_hook() {
    local git_dir; git_dir=$(git -C "$ROOT" rev-parse --git-dir 2>/dev/null) || return 0
    local hook="$git_dir/hooks/pre-commit"
    local hook_script="$ROOT/scripts/pre-commit"

    if [ ! -f "$hook_script" ]; then
        yellow "  scripts/pre-commit not found — skipping hook installation."
        return 0
    fi

    # Write a thin wrapper that delegates to the versioned script in the repo.
    # This way updates to scripts/pre-commit are picked up without reinstalling.
    # Overwrite if the wrapper is ours or if no hook exists yet.
    if [ ! -f "$hook" ] || grep -q "AGENTIC_RAG_SECRETS_HOOK" "$hook" 2>/dev/null; then
        cat > "$hook" <<HOOK
#!/usr/bin/env bash
# AGENTIC_RAG_SECRETS_HOOK — auto-installed by setup.sh
# Delegates to the versioned scanner in the repository.
exec python3 "\$(git rev-parse --show-toplevel)/scripts/pre-commit"
HOOK
        chmod +x "$hook"
        green "  Installed pre-commit secrets hook → $hook"
    else
        yellow "  A custom pre-commit hook already exists — not overwriting."
        yellow "  To enable secrets scanning, add to it:"
        yellow "    python3 \"\$(git rev-parse --show-toplevel)/scripts/pre-commit\""
    fi
}

if [ -d "$ROOT/.git" ]; then
    _install_git_hook
else
    yellow "  Not a git repo — skipping pre-commit hook installation."
fi

# ── 5. Frontend dependencies ──────────────────────────────────────────────────
cd "$ROOT/frontend"
cyan "Installing frontend dependencies (npm ci)..."

# Resolve npm — search PATH including common nvm/fnm/volta locations
NPM_CMD=""
for candidate in npm \
    "$HOME/.nvm/versions/node/$(ls "$HOME/.nvm/versions/node" 2>/dev/null | sort -V | tail -1)/bin/npm" \
    "$HOME/.volta/bin/npm" \
    "$HOME/.fnm/aliases/default/bin/npm" \
    /usr/local/bin/npm \
    /opt/homebrew/bin/npm; do
    if command -v "$candidate" &>/dev/null 2>&1; then
        NPM_CMD="$candidate"
        break
    fi
done

if [ -z "$NPM_CMD" ]; then
    echo ""
    red  "  ERROR: npm (Node.js) not found."
    echo ""
    echo "  Install Node.js 18+ and re-run this script:"
    echo "    macOS (Homebrew):  brew install node"
    echo "    nvm (any OS):      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash"
    echo "                       nvm install --lts"
    echo "    Official installer: https://nodejs.org/en/download"
    echo ""
    echo "  After installing, open a NEW terminal (so PATH is updated) and re-run:"
    echo "    bash setup.sh"
    echo ""
    exit 1
fi

"$NPM_CMD" ci --silent
green "  Frontend dependencies installed"

# ── 5. Sample data (optional, prompted) ──────────────────────────────────────
if [ "$AUTO_YES" == false ]; then
    echo ""
    bold "------------------------------------------------------------"
    bold " Sample Data"
    bold "------------------------------------------------------------"
    echo ""
    echo "  The app supports PDF, TXT, CSV, and Excel uploads."
    echo "  You can either:"
    echo "    [1] Generate provided sample files (HR policy, employee data,"
    echo "        financial data, technology report) — recommended for first run"
    echo "    [2] Skip and upload your own files through the UI"
    echo ""

    while true; do
        read -rp "  Generate sample data? [1/2]: " choice
        case "$choice" in
            1)
                cyan "  Installing sample-data dependencies..."
                pip install -q reportlab openpyxl 2>/dev/null || true
                cd "$ROOT"
                "$PYTHON" sample-data/generate_samples.py
                green "  Sample files created in sample-data/"
                echo ""
                cyan "  Upload these files via the UI after logging in:"
                echo "    sample-data/sample.txt   — HR & Employee Handbook"
                echo "    sample-data/sample.csv   — Employee roster & salaries"
                echo "    sample-data/sample.xlsx  — Financial & headcount data"
                echo "    sample-data/sample.pdf   — Annual Technology Report"
                break
                ;;
            2)
                yellow "  Skipped. Upload your own PDF/TXT/CSV/XLSX files through the UI."
                break
                ;;
            *)
                echo "  Please enter 1 or 2."
                ;;
        esac
    done
fi

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo ""
bold "============================================================"
green " Setup complete!"
bold "============================================================"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Set your OpenAI key (if not done yet):"
echo "       nano backend/.env   # or your preferred editor"
echo ""
echo "  2. Start the backend (Terminal 1):"
echo "       cd backend && source .venv/bin/activate"
echo "       uvicorn app.main:app --reload --port 8000"
echo ""
echo "  3. Start the frontend (Terminal 2):"
echo "       cd frontend && npm run dev"
echo ""
echo "  4. Open: http://localhost:5173"
echo "     Username: admin"
if [ "$ADMIN_PASS_GENERATED" == true ]; then
echo "     Password: $ADMIN_PASS   ← SAVE THIS NOW"
else
echo "     Password: (the password you entered)"
fi
echo "     (also saved in backend/.env as ADMIN_PASSWORD — keep that file private)"
echo ""
echo "  5. Run tests:"
echo "       bash run-tests.sh"
echo ""
echo "  Docker (alternative):"
echo "       docker compose up --build"
echo ""
