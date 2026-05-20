#!/usr/bin/env bash
# setup.sh — One-command local development setup for Agentic RAG.
# Usage:  bash setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
cyan()  { printf '\033[0;36m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[0;33m%s\033[0m\n' "$*"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }

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

# Writes $ADMIN_PASS into the ADMIN_PASSWORD line of .env (portable, no sed escaping issues)
_write_admin_password() {
    local pwd="$1"
    ADMIN_PASS="$pwd" "$PYTHON" - <<'PYEOF'
import os, re, pathlib
pwd = os.environ['ADMIN_PASS']
p = pathlib.Path('.env')
content = p.read_text()
if re.search(r'^ADMIN_PASSWORD=', content, re.MULTILINE):
    content = re.sub(r'^ADMIN_PASSWORD=.*$', f'ADMIN_PASSWORD={pwd}', content, flags=re.MULTILINE)
else:
    content = content.rstrip('\n') + f'\nADMIN_PASSWORD={pwd}\n'
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

ADMIN_PASS=""

if [ ! -f ".env" ]; then
    cp .env.example .env
    ADMIN_PASS=$(_gen_password)
    _write_admin_password "$ADMIN_PASS"
    green "  Created backend/.env with a generated admin password"
    echo ""
    yellow "  ⚠  ACTION REQUIRED: open backend/.env and set your OPENAI_API_KEY"
    echo ""
else
    yellow "  backend/.env already exists — skipping"
    # Backfill ADMIN_PASSWORD if missing or empty (e.g. .env was created before this update)
    if ! grep -qE "^ADMIN_PASSWORD=.+" .env 2>/dev/null; then
        ADMIN_PASS=$(_gen_password)
        _write_admin_password "$ADMIN_PASS"
        yellow "  Generated missing ADMIN_PASSWORD in backend/.env"
    else
        ADMIN_PASS=$(grep "^ADMIN_PASSWORD=" .env | cut -d'=' -f2-)
    fi
fi

# ── 4. Frontend dependencies ──────────────────────────────────────────────────
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
echo "     Password: $ADMIN_PASS"
echo "     (also saved in backend/.env as ADMIN_PASSWORD — keep that file private)"
echo ""
echo "  5. Run tests:"
echo "       bash run-tests.sh"
echo ""
echo "  Docker (alternative):"
echo "       docker compose up --build"
echo ""
