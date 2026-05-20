#!/usr/bin/env bash
# run-live-tests.sh — Initiate live dependency tests against real OpenAI + ChromaDB.
#
# USAGE
#   bash run-live-tests.sh [SUITE]
#   bash run-live-tests.sh --help
#
#   SUITE (optional, default: all)
#     openai    — connectivity + embedding + LLM completion
#     chromadb  — real vector-store CRUD with embeddings
#     agent     — agentic pipeline (planner/retriever/generator/validator) + simple RAG (6 stages total)
#     api       — end-to-end HTTP tests (requires a running backend)
#     ragas     — Ragas quality metrics (faithfulness, answer relevancy, context precision, recall)
#     all       — all suites in order (ragas skipped unless SKIP_RAGAS_EVAL=false)
#
# KEY ENVIRONMENT VARIABLES
#   OPENAI_API_KEY          (required) your real OpenAI key
#   LIVE_SESSION_TIMEOUT    seconds before the whole session is killed (default 300)
#   LIVE_STAGE_TIMEOUT      seconds to wait for each interactive prompt  (default 30)
#   LIVE_QUESTION           pre-set question so stage prompts are skipped (applies to both agentic and simple RAG stages)
#   LIVE_BACKEND_URL        URL of a running backend (default http://localhost:8000)
#   LIVE_AUTO_START_BACKEND set to 'false' to avoid auto-starting localhost backend (default true)
#   SKIP_API_TESTS          set to 'true' to skip tests that need a live server
#
# EXAMPLES
#   export OPENAI_API_KEY=<your-openai-api-key>
#   bash run-live-tests.sh
#
#   LIVE_QUESTION="What is Retrieval-Augmented Generation and how does it work?" bash run-live-tests.sh agent
#
#   LIVE_SESSION_TIMEOUT=600 SKIP_API_TESTS=true bash run-live-tests.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUITE="${1:-all}"
REPORTS="$ROOT/test-reports"
EXIT_CODE=0
VALID_SUITES="openai chromadb agent api ragas all"
BACKEND_PID=""

# ── Colour helpers ─────────────────────────────────────────────────────────────
bold()   { printf '\033[1m%s\033[0m\n'    "$*"; }
cyan()   { printf '\033[0;36m%s\033[0m\n' "$*"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
sep()    { printf '%s\n' "$(printf '─%.0s' {1..64})"; }

cleanup_backend() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    yellow "Stopping auto-started backend (pid $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    BACKEND_PID=""
  fi
}

usage() {
  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

replace_or_append_env() {
  local file="$1" key="$2" value="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  python3 - "$file" "$key" "$value" <<'PYEOF'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
prefix = f"{key}="
lines = path.read_text().splitlines() if path.exists() else []
updated = False
out = []
for line in lines:
    if line.startswith(prefix):
        out.append(f"{key}={value}")
        updated = True
    else:
        out.append(line)
if not updated:
    if out and out[-1] != "":
        out.append("")
    out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PYEOF
}

if [[ "$SUITE" == "--help" || "$SUITE" == "-h" ]]; then
  usage
  exit 0
fi

if [[ " $VALID_SUITES " != *" $SUITE "* ]]; then
  red "Unknown suite: '$SUITE'"
  echo "  Valid values: openai | chromadb | agent | api | ragas | all"
  echo ""
  usage
  exit 2
fi

# ── Pre-flight checks ──────────────────────────────────────────────────────────
bold "=== LIVE DEPENDENCY TESTS ==="
sep

# 1. OpenAI key
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  red "✗ OPENAI_API_KEY is not set."
  echo "  Export a real key before running:"
  echo "    export OPENAI_API_KEY=<your-openai-api-key>"
  exit 1
fi
if [[ "$OPENAI_API_KEY" == sk-test* ]] || [[ "$OPENAI_API_KEY" == "test-key" ]] || [[ "$OPENAI_API_KEY" == "sk-fake" ]]; then
  red "✗ OPENAI_API_KEY looks like a test placeholder."
  echo "  Live tests require a real OpenAI key."
  exit 1
fi
green "✓ OPENAI_API_KEY is set (${#OPENAI_API_KEY} chars)"

# 2. Admin password: load from env/.env, generate if absent, clear on exit
_ENV_FILE="$ROOT/backend/.env"
_PWD_INJECTED=false

if [[ ! -f "$_ENV_FILE" && -f "$ROOT/backend/.env.example" ]]; then
  cp "$ROOT/backend/.env.example" "$_ENV_FILE"
  yellow "⚡ Created backend/.env from backend/.env.example"
fi

_clear_admin_password() {
  cleanup_backend
  if [[ "$_PWD_INJECTED" == "true" ]] && [[ -f "$_ENV_FILE" ]]; then
    replace_or_append_env "$_ENV_FILE" "ADMIN_PASSWORD" ""
    green "✓ ADMIN_PASSWORD cleared from backend/.env"
  fi
}
trap _clear_admin_password EXIT

if [[ -z "${ADMIN_PASSWORD:-}" ]] && [[ -f "$_ENV_FILE" ]]; then
  _existing="$(grep -m1 '^ADMIN_PASSWORD=' "$_ENV_FILE" | cut -d= -f2- || true)"
  if [[ -n "$_existing" ]]; then
    export ADMIN_PASSWORD="$_existing"
    green "✓ ADMIN_PASSWORD loaded from backend/.env"
  fi
fi

if [[ -z "${ADMIN_PASSWORD:-}" ]]; then
  ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')"
  export ADMIN_PASSWORD
  replace_or_append_env "$_ENV_FILE" "ADMIN_PASSWORD" "$ADMIN_PASSWORD"
  _PWD_INJECTED=true
  yellow "⚡ Auto-generated ADMIN_PASSWORD written to backend/.env"
  yellow "   (Re)start the backend server before running API live tests."
  yellow "   Password will be cleared from backend/.env when this script exits."
fi

# 3. Python venv
cd "$ROOT/backend"
if [[ ! -d ".venv" ]]; then
  cyan "Creating Python virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# 4. Dependencies (including pytest-timeout added for live tests)
cyan "Installing/verifying backend dependencies..."
pip install -q -r requirements-dev.txt

# 5. Backend server check (only needed for 'api' or 'all' suites)
BACKEND_URL="${LIVE_BACKEND_URL:-http://localhost:8000}"
SKIP_API="${SKIP_API_TESTS:-false}"
AUTO_START_BACKEND="${LIVE_AUTO_START_BACKEND:-true}"

_backend_url_host() {
  python3 - "$BACKEND_URL" <<'PYEOF'
from urllib.parse import urlparse
import sys
print(urlparse(sys.argv[1]).hostname or "")
PYEOF
}

_backend_url_port() {
  python3 - "$BACKEND_URL" <<'PYEOF'
from urllib.parse import urlparse
import sys
u = urlparse(sys.argv[1])
print(u.port or (443 if u.scheme == "https" else 80))
PYEOF
}

_backend_reachable() {
  curl -sf "$BACKEND_URL/api/health" > /dev/null 2>&1
}

_start_local_backend() {
  local host port log_file elapsed max_wait
  host="$(_backend_url_host)"
  port="$(_backend_url_port)"

  case "$host" in
    localhost|127.0.0.1|::1) ;;
    *)
      return 1
      ;;
  esac

  log_file="$REPORTS/live-backend.log"
  cyan "Auto-starting backend for API live tests at $BACKEND_URL ..."
  (
    cd "$ROOT/backend"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    export PYTHONUNBUFFERED=1
    exec uvicorn app.main:app --host 127.0.0.1 --port "$port"
  ) > "$log_file" 2>&1 &
  BACKEND_PID=$!

  max_wait=30
  elapsed=0
  while [[ $elapsed -lt $max_wait ]]; do
    if _backend_reachable; then
      green "✓ Auto-started backend reachable at $BACKEND_URL"
      return 0
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      red "✗ Auto-started backend exited early. Log: $log_file"
      BACKEND_PID=""
      return 1
    fi
    sleep 1
    ((elapsed++))
  done

  red "✗ Backend did not become reachable within ${max_wait}s. Log: $log_file"
  cleanup_backend
  return 1
}

if [[ "$SUITE" == "api" || "$SUITE" == "all" ]] && [[ "$SKIP_API" != "true" ]]; then
  if _backend_reachable; then
    green "✓ Backend reachable at $BACKEND_URL"
  elif [[ "$AUTO_START_BACKEND" == "true" ]] && _start_local_backend; then
    :
  else
    yellow "⚠  Backend not reachable at $BACKEND_URL"
    yellow "   API tests will be auto-skipped."
    yellow "   Start it manually with: cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000"
    yellow "   Or set LIVE_AUTO_START_BACKEND=true for localhost URLs."
    yellow "   Set SKIP_API_TESTS=true to suppress this warning and skip the API suite."
  fi
fi

mkdir -p "$REPORTS"

# ── Helper: run one pytest suite ──────────────────────────────────────────────
run_suite() {
  local name="$1"
  local path="$2"
  local report_stem="$3"

  sep
  cyan "▶  $name"
  sep

  local extra_args=()
  # -s keeps stdin attached so interactive prompts reach the terminal
  # --timeout from pytest-timeout caps each individual test
  if python -m pytest \
       "$path" \
       -v -s \
       -o addopts= \
       --no-header \
       --tb=short \
       --timeout="${LIVE_STAGE_TIMEOUT:-30}" \
       --html="$REPORTS/${report_stem}.html" \
       --self-contained-html \
       -p no:cacheprovider \
       ${extra_args[@]+"${extra_args[@]}"}; then
    green "✓ $name PASSED"
  else
    red   "✗ $name FAILED"
    EXIT_CODE=1
  fi
  echo ""
}

# ── Export env for child pytest processes ─────────────────────────────────────
export LIVE_TESTS=1
export LIVE_SESSION_TIMEOUT="${LIVE_SESSION_TIMEOUT:-300}"
export LIVE_STAGE_TIMEOUT="${LIVE_STAGE_TIMEOUT:-30}"
export LIVE_BACKEND_URL="$BACKEND_URL"
# LIVE_QUESTION is passed through if already set

sep
bold "Session timeout : ${LIVE_SESSION_TIMEOUT}s"
bold "Stage timeout   : ${LIVE_STAGE_TIMEOUT}s  (per interactive prompt)"
[[ -n "${LIVE_QUESTION:-}" ]] && bold "Question preset : $LIVE_QUESTION"
sep
echo ""

# ── Run suites ────────────────────────────────────────────────────────────────
case "$SUITE" in
  openai)
    run_suite "OpenAI Connectivity" "tests/live/test_live_openai.py" "live-openai"
    ;;
  chromadb)
    run_suite "ChromaDB Live"       "tests/live/test_live_chromadb.py" "live-chromadb"
    ;;
  agent)
    run_suite "Agent Pipeline"      "tests/live/test_live_agent.py"   "live-agent"
    ;;
  api)
    if [[ "$SKIP_API" == "true" ]]; then
      yellow "⚡ API suite skipped (SKIP_API_TESTS=true)"
    else
      run_suite "End-to-End API"    "tests/live/test_live_api.py"     "live-api"
    fi
    ;;
  ragas)
    run_suite "Ragas Evaluation" "tests/live/test_live_ragas.py" "live-ragas"
    ;;
  all)
    run_suite "OpenAI Connectivity" "tests/live/test_live_openai.py"  "live-openai"
    run_suite "ChromaDB Live"       "tests/live/test_live_chromadb.py" "live-chromadb"
    run_suite "Agent Pipeline"      "tests/live/test_live_agent.py"   "live-agent"
    if [[ "$SKIP_API" == "true" ]]; then
      yellow "⚡ API suite skipped (SKIP_API_TESTS=true)"
    else
      run_suite "End-to-End API"    "tests/live/test_live_api.py"     "live-api"
    fi
    # Ragas evaluation is opt-in in the 'all' path because it consumes OpenAI
    # tokens (100–500 per run). Set SKIP_RAGAS_EVAL=false to include it.
    if [[ "${SKIP_RAGAS_EVAL:-true}" != "true" ]]; then
      run_suite "Ragas Evaluation" "tests/live/test_live_ragas.py" "live-ragas"
    else
      yellow "⚡ Ragas evaluation skipped (set SKIP_RAGAS_EVAL=false to enable)"
    fi
    ;;
  *)
    # Suite validation happens before pre-flight checks; this is defensive only.
    red "Unknown suite: '$SUITE'"
    exit 2
    ;;
esac

deactivate 2>/dev/null || true

# ── Summary ───────────────────────────────────────────────────────────────────
sep
bold "=== LIVE TEST SUMMARY ==="
if [[ "$EXIT_CODE" -eq 0 ]]; then
  green "All live suites passed."
else
  red   "One or more live suites failed — check output above."
fi
echo ""
cyan "HTML reports written to: $REPORTS/"
cyan "Open: open $REPORTS/live-agent.html"

exit "$EXIT_CODE"
