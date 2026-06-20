#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${TEACH_HOST:-127.0.0.1}"
PORT="${TEACH_PORT:-8000}"
OPEN_BROWSER="${TEACH_OPEN_BROWSER:-1}"
PYTHON_BIN="${PYTHON:-python3}"
LOG_DIR="$ROOT_DIR/outputs/logs"
PID_FILE="$ROOT_DIR/.teach_assistant.pid"

usage() {
  cat <<'EOF'
Usage:
  ./start_teach_assistant.sh [options]

Options:
  --host HOST     Host to bind. Default: 127.0.0.1
  --port PORT     Port to bind. Default: 8000
  --no-open       Do not open the browser after startup.
  -h, --help      Show this help.

Environment:
  TEACH_HOST, TEACH_PORT, TEACH_OPEN_BROWSER, PYTHON
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?Missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?Missing value for --port}"
      shift 2
      ;;
    --no-open)
      OPEN_BROWSER=0
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

URL="http://$HOST:$PORT"
CONFIG_URL="$URL/api/config-status"
LOG_FILE="$LOG_DIR/server-$PORT.log"

open_browser() {
  if [[ "$OPEN_BROWSER" == "1" ]] && command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  fi
}

if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "$CONFIG_URL" >/dev/null 2>&1; then
  echo "Teaching Assistant is already running: $URL"
  open_browser
  exit 0
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use, but $CONFIG_URL did not respond." >&2
  echo "Use --port PORT to start on another port, or stop the process using that port." >&2
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2 || true
  exit 1
fi

mkdir -p "$LOG_DIR"
cd "$ROOT_DIR"

echo "Starting Teaching Assistant at $URL ..."
echo "Log: $LOG_FILE"
"$PYTHON_BIN" -m app.server --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

for _ in $(seq 1 60); do
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "$CONFIG_URL" >/dev/null 2>&1; then
    echo "Teaching Assistant is ready: $URL"
    open_browser
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "Server exited before it became ready." >&2
    echo "Last log lines:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "Server did not become ready within 60 seconds." >&2
echo "PID: $SERVER_PID" >&2
echo "Last log lines:" >&2
tail -n 40 "$LOG_FILE" >&2 || true
exit 1
