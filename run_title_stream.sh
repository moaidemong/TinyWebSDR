#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
TIMEZONE="${TIMEZONE:-Asia/Seoul}"
STATE_FILE="${STATE_FILE:-runtime/band_state.json}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 (or python) not found in PATH." >&2
    exit 1
  fi
fi

cleanup() {
  echo
  echo "Stopping title stream stack..."
  kill "${SCHED_PID:-}" "${GATEWAY_PID:-}" "${CLIENT_PID:-}" 2>/dev/null || true
  wait "${SCHED_PID:-}" "${GATEWAY_PID:-}" "${CLIENT_PID:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting scheduler..."
"$PYTHON_BIN" scheduler.py \
  --timezone "$TIMEZONE" \
  --state-file "$STATE_FILE" \
  --python-bin "$PYTHON_BIN" &
SCHED_PID=$!

echo "Starting websocket gateway..."
"$PYTHON_BIN" ws_server.py --state-file "$STATE_FILE" &
GATEWAY_PID=$!

echo "Starting client static server on http://127.0.0.1:8080 ..."
(
  cd client
  "$PYTHON_BIN" -m http.server 8080
) &
CLIENT_PID=$!

echo "Title stream stack started. Press Ctrl+C to stop."
wait "$SCHED_PID" "$GATEWAY_PID" "$CLIENT_PID"
