#!/usr/bin/env bash
# Serve the Docsify documentation site locally.
#
# Usage:
#   bash scripts/local/deploy-docs-local.sh
#   bash scripts/local/deploy-docs-local.sh --open
#   bash scripts/local/deploy-docs-local.sh --port 8090 --host 0.0.0.0

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCS_DIR="$ROOT_DIR/docs"
HOST="${DOCS_HOST:-127.0.0.1}"
PORT="${DOCS_PORT:-8088}"
OPEN_BROWSER=false
DRY_RUN=false

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
  cat <<USAGE

Options:
  --host <host>   Bind host (default: ${HOST})
  --port <port>   Port (default: ${PORT})
  --open          Open the docs URL in the default browser
  --no-open       Do not open the browser
  --dry-run       Print what would run without starting the server
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
    --open)
      OPEN_BROWSER=true
      shift
      ;;
    --no-open)
      OPEN_BROWSER=false
      shift
      ;;
    --dry-run)
      DRY_RUN=true
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

if [[ ! -f "$DOCS_DIR/index.html" ]]; then
  echo "Docs index not found: $DOCS_DIR/index.html" >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to serve docs locally." >&2
  exit 1
}

URL="http://localhost:${PORT}/"

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

echo "Docs local deployment"
echo "  Directory : $DOCS_DIR"
echo "  URL       : $URL"
echo "  Bind      : ${HOST}:${PORT}"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run only. Command:"
  echo "  cd \"$DOCS_DIR\" && python3 -m http.server \"$PORT\" --bind \"$HOST\""
  exit 0
fi

if [[ "$OPEN_BROWSER" == "true" ]]; then
  (sleep 1; open_url "$URL") &
fi

cd "$DOCS_DIR"
exec python3 -m http.server "$PORT" --bind "$HOST"
