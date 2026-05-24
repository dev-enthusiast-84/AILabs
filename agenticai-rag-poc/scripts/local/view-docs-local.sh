#!/usr/bin/env bash
# Open the local documentation site, optionally starting the docs server first.
#
# Usage:
#   bash scripts/local/view-docs-local.sh
#   bash scripts/local/view-docs-local.sh --start
#   bash scripts/local/view-docs-local.sh --port 8090

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${DOCS_HOST:-127.0.0.1}"
PORT="${DOCS_PORT:-8088}"
START_SERVER=false

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  cat <<USAGE

Options:
  --host <host>   Host to check/open (default: ${HOST})
  --port <port>   Port to check/open (default: ${PORT})
  --start         Start the local docs server in the background if needed
  -h, --help      Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --start)
      START_SERVER=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$PORT" =~ ^[0-9]+$ ]]; then
  echo "Port must be numeric: $PORT" >&2
  exit 2
fi

URL="http://localhost:${PORT}/"

docs_server_ready() {
  python3 - "$URL" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
        raise SystemExit(0 if response.status < 500 else 1)
except Exception:
    raise SystemExit(1)
PY
}

open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "$url" >/dev/null 2>&1 || true
  else
    echo "Open this URL in your browser: $url"
  fi
}

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to check or start the docs server." >&2
  exit 1
}

if ! docs_server_ready; then
  if [[ "$START_SERVER" != "true" ]]; then
    echo "Docs server is not responding at $URL"
    echo "Start it with:"
    echo "  bash scripts/local/deploy-docs-local.sh --open"
    echo ""
    echo "Or start and open in one step:"
    echo "  bash scripts/local/view-docs-local.sh --start"
    exit 1
  fi

  mkdir -p "$ROOT_DIR/artifacts/docs-local"
  LOG_FILE="$ROOT_DIR/artifacts/docs-local/server.log"
  PID_FILE="$ROOT_DIR/artifacts/docs-local/server.pid"
  nohup bash "$ROOT_DIR/scripts/local/deploy-docs-local.sh" \
    --host "$HOST" \
    --port "$PORT" \
    --no-open \
    >"$LOG_FILE" 2>&1 &
  echo "$!" > "$PID_FILE"
  echo "Started docs server: $URL"
  echo "  PID : $(cat "$PID_FILE")"
  echo "  Log : $LOG_FILE"
  sleep 1
fi

open_url "$URL"
echo "Docs URL: $URL"
