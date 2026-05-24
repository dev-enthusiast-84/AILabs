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
#     all       — all suites in order (set RUN_RAGAS_EVAL=false to skip Ragas)
#
# KEY ENVIRONMENT VARIABLES
#   OPENAI_API_KEY          (required) your real OpenAI key
#   LIVE_SESSION_TIMEOUT    seconds before the whole session is killed (default 300)
#   LIVE_STAGE_TIMEOUT      seconds to wait for each interactive prompt  (default 30)
#   LIVE_TEST_TIMEOUT       pytest per-test timeout in seconds (default 90; must exceed LIVE_STAGE_TIMEOUT)
#   LIVE_QUESTION           pre-set question so stage prompts are skipped (applies to both agentic and simple RAG stages)
#   LIVE_BACKEND_URL        URL of a running backend (default http://localhost:8000)
#   LIVE_AUTO_START_BACKEND set to 'false' to skip auto-starting localhost backend (default true)
#   RUN_API_TESTS           set to 'false' to skip API tests (default true — requires running backend)
#   RUN_RAGAS_EVAL          set to 'false' to skip Ragas evaluation (default true — consumes OpenAI tokens)
#
# EXAMPLES
#   export OPENAI_API_KEY=<your-openai-api-key>
#   bash run-live-tests.sh
#
#   LIVE_QUESTION="What is Retrieval-Augmented Generation and how does it work?" bash run-live-tests.sh agent
#
#   LIVE_SESSION_TIMEOUT=600 RUN_API_TESTS=false bash run-live-tests.sh
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
  yellow "! Created backend/.env from backend/.env.example"
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
  yellow "! Auto-generated ADMIN_PASSWORD written to backend/.env"
  yellow "   Password will be cleared from backend/.env when this script exits."
fi

# 2b. SECRET_KEY: load from env/.env or generate once (persisted, never cleared —
#     rotating would invalidate JWTs but tests generate fresh ones each run).
if [[ -z "${SECRET_KEY:-}" ]] && [[ -f "$_ENV_FILE" ]]; then
  _existing_sk="$(grep -m1 '^SECRET_KEY=' "$_ENV_FILE" | cut -d= -f2- || true)"
  if [[ -n "$_existing_sk" ]]; then
    export SECRET_KEY="$_existing_sk"
    green "✓ SECRET_KEY loaded from backend/.env"
  fi
fi
if [[ -z "${SECRET_KEY:-}" ]]; then
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  export SECRET_KEY
  replace_or_append_env "$_ENV_FILE" "SECRET_KEY" "$SECRET_KEY"
  yellow "! Auto-generated SECRET_KEY written to backend/.env (persisted for future runs)"
fi

# 3. Python venv
cd "$ROOT/backend"
_VENV_FRESH=false
if [[ ! -d ".venv" ]]; then
  cyan "Creating Python virtual environment..."
  python3 -m venv .venv
  _VENV_FRESH=true
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# 4. Dependencies — skip install when requirements are unchanged (avoids hanging
#    on repeated runs when everything is already installed).
_HASH_FILE=".venv/.requirements-dev.hash"
_CUR_HASH=$(md5 -q requirements-dev.txt 2>/dev/null \
  || md5sum requirements-dev.txt 2>/dev/null | cut -d' ' -f1 \
  || echo "unknown")
_OLD_HASH=$(cat "$_HASH_FILE" 2>/dev/null || echo "")

if [[ "$_VENV_FRESH" == "true" || "$_CUR_HASH" != "$_OLD_HASH" || "${REINSTALL_DEPS:-false}" == "true" ]]; then
  cyan "Installing backend dependencies..."
  pip install -q -r requirements-dev.txt
  echo "$_CUR_HASH" > "$_HASH_FILE"
  green "✓ Backend dependencies installed"
else
  green "✓ Backend dependencies up to date (requirements unchanged)"
fi

# 5. Backend server check (needed for 'api' suite or when RUN_API_TESTS=true)
#    API tests run by default; set RUN_API_TESTS=false to skip them.
BACKEND_URL="${LIVE_BACKEND_URL:-http://localhost:8000}"
RUN_API="${RUN_API_TESTS:-true}"
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
  # Hard timeouts prevent hanging when a stale process holds the port half-open.
  curl -sf --connect-timeout 3 --max-time 5 "$BACKEND_URL/api/health" > /dev/null 2>&1
}

_backend_reachable_with_retry() {
  # Retry up to ~10s to absorb a transient reload triggered by .env writes.
  local i
  for i in 1 2 3 4 5; do
    if _backend_reachable; then return 0; fi
    sleep 2
  done
  return 1
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

  # If the port is already occupied the server is likely mid-reload after we
  # wrote ADMIN_PASSWORD/SECRET_KEY to backend/.env.  Wait for it to recover
  # rather than spawning a competing uvicorn that will fail to bind.
  if lsof -ti tcp:"$port" > /dev/null 2>&1; then
    yellow "  Port $port already in use — waiting up to 15s for existing server to recover..."
    local wait_elapsed=0
    while [[ $wait_elapsed -lt 15 ]]; do
      if _backend_reachable; then
        green "✓ Backend reachable at $BACKEND_URL (recovered after reload)"
        return 0
      fi
      sleep 1
      ((wait_elapsed++)) || true
    done
    red "✗ Port $port in use but backend not reachable after ${wait_elapsed}s"
    return 1
  fi

  log_file="$REPORTS/live-backend.log"
  mkdir -p "$REPORTS"
  cyan "Auto-starting backend at $BACKEND_URL (log: $log_file) ..."
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
  printf "  Waiting for backend"
  while [[ $elapsed -lt $max_wait ]]; do
    if _backend_reachable; then
      printf "\n"
      green "✓ Backend reachable at $BACKEND_URL"
      return 0
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      printf "\n"
      red "✗ Backend exited early — check $log_file"
      BACKEND_PID=""
      return 1
    fi
    printf "."
    sleep 1
    ((elapsed++))
  done

  printf "\n"
  red "✗ Backend not reachable after ${max_wait}s — check $log_file"
  cleanup_backend
  return 1
}

_kill_port_process() {
  # Kill whatever process is bound to the backend port so we can restart clean.
  local port
  port="$(_backend_url_port)"
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    yellow "  Stopping existing process(es) on port $port (pid(s): $pids)..."
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    sleep 2
    # Force-kill anything still lingering
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    [[ -n "$pids" ]] && echo "$pids" | xargs kill -9 2>/dev/null || true
  fi
  BACKEND_PID=""
}

if [[ "$SUITE" == "api" || "$SUITE" == "all" ]] && [[ "$RUN_API" == "true" ]]; then
  # Use the retry variant: a .env write can trigger uvicorn --reload, causing a
  # brief (~2s) window where the server is down even though the port is held.
  if _backend_reachable_with_retry; then
    if [[ "$AUTO_START_BACKEND" == "true" ]]; then
      # Always restart when we manage the backend — ensures ADMIN_PASSWORD,
      # SECRET_KEY, and other .env values the script just wrote are picked up.
      yellow "  Restarting backend to synchronise with current .env (ADMIN_PASSWORD, SECRET_KEY)..."
      _kill_port_process
      _start_local_backend || true
    else
      green "✓ Backend reachable at $BACKEND_URL"
    fi
  elif [[ "$AUTO_START_BACKEND" == "true" ]] && _start_local_backend; then
    :
  else
    yellow "⚠  Backend not reachable at $BACKEND_URL and auto-start failed."
    yellow "   API tests will be auto-skipped by the test fixture."
    yellow "   Start it manually with: cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000"
    yellow "   Set RUN_API_TESTS=false to suppress this warning and skip the API suite."
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
       --timeout="${LIVE_TEST_TIMEOUT:-90}" \
       -W "ignore::PendingDeprecationWarning" \
       -W "ignore::DeprecationWarning" \
       -W "ignore:.*allowed_objects.*" \
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
# Suppress deprecation noise before Python starts (PYTHONWARNINGS is processed by
# the C runtime, before any conftest or -W flag, so it catches warnings that fire
# during the very first module imports — including langgraph's allowed_objects
# PendingDeprecationWarning which consistently slips through later filters).
export PYTHONWARNINGS="ignore::DeprecationWarning,ignore::PendingDeprecationWarning"
export LIVE_TESTS=1
# ChromaDB product telemetry — enabled by default so live tests run under real-world
# conditions (same as production). Set ANONYMIZED_TELEMETRY=false to opt out.
export ANONYMIZED_TELEMETRY="${ANONYMIZED_TELEMETRY:-true}"
export LIVE_SESSION_TIMEOUT="${LIVE_SESSION_TIMEOUT:-300}"
export LIVE_STAGE_TIMEOUT="${LIVE_STAGE_TIMEOUT:-30}"
export LIVE_TEST_TIMEOUT="${LIVE_TEST_TIMEOUT:-90}"
export LIVE_BACKEND_URL="$BACKEND_URL"
# Disable Ragas telemetry to t.explodinggradients.com — intermittent DNS
# failures against that domain caused spurious test failures.
export RAGAS_DO_NOT_TRACK=true
# LIVE_QUESTION is passed through if already set

sep
bold "Session timeout : ${LIVE_SESSION_TIMEOUT}s"
bold "Stage timeout   : ${LIVE_STAGE_TIMEOUT}s  (per interactive prompt)"
bold "Test timeout    : ${LIVE_TEST_TIMEOUT}s  (per test, incl. stage gate)"
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
    if [[ "$RUN_API" != "true" ]]; then
      yellow "! API suite skipped (set RUN_API_TESTS=true to enable)"
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
    if [[ "$RUN_API" != "true" ]]; then
      yellow "! API suite skipped (set RUN_API_TESTS=true to enable)"
    else
      run_suite "End-to-End API"    "tests/live/test_live_api.py"     "live-api"
    fi
    # Ragas consumes OpenAI tokens (100-500 per run); set RUN_RAGAS_EVAL=false to skip.
    if [[ "${RUN_RAGAS_EVAL:-true}" == "true" ]]; then
      run_suite "Ragas Evaluation" "tests/live/test_live_ragas.py" "live-ragas"
    else
      yellow "! Ragas evaluation skipped (set RUN_RAGAS_EVAL=true to enable)"
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
