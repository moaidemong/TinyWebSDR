#!/usr/bin/env bash
set -euo pipefail

SOURCE="sim"
CENTER_FREQ="6850000"
SAMPLE_RATE="2400000"
GAIN="38.6"
FPS="60"

usage() {
  cat <<'EOF'
Usage: ./run_mvp.sh [options]

Options:
  --source sim|rtlsdr      IQ source mode (default: sim)
  --center-freq HZ         Center frequency in Hz (default: 6850000)
  --sample-rate HZ         Sample rate in Hz (default: 2400000)
  --gain VALUE             Gain value or "auto" (default: 38.6)
  --fps VALUE              Producer FPS target (default: 60)
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE="${2:-}"
      shift 2
      ;;
    --center-freq)
      CENTER_FREQ="${2:-}"
      shift 2
      ;;
    --sample-rate)
      SAMPLE_RATE="${2:-}"
      shift 2
      ;;
    --gain)
      GAIN="${2:-}"
      shift 2
      ;;
    --fps)
      FPS="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$SOURCE" != "sim" && "$SOURCE" != "rtlsdr" ]]; then
  echo "Invalid --source: $SOURCE (use sim or rtlsdr)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
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
  echo "Stopping MVP stack..."
  kill "${PRODUCER_PID:-}" "${GATEWAY_PID:-}" "${CLIENT_PID:-}" 2>/dev/null || true
  wait "${PRODUCER_PID:-}" "${GATEWAY_PID:-}" "${CLIENT_PID:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting producer..."
"$PYTHON_BIN" core_producer.py \
  --source "$SOURCE" \
  --center-freq "$CENTER_FREQ" \
  --sample-rate "$SAMPLE_RATE" \
  --gain "$GAIN" \
  --fps "$FPS" &
PRODUCER_PID=$!

echo "Starting websocket gateway..."
"$PYTHON_BIN" ws_server.py &
GATEWAY_PID=$!

echo "Starting client static server on http://127.0.0.1:8080 ..."
(
  cd client
  "$PYTHON_BIN" -m http.server 8080
) &
CLIENT_PID=$!

echo "MVP stack started. Press Ctrl+C to stop."
wait "$PRODUCER_PID" "$GATEWAY_PID" "$CLIENT_PID"
