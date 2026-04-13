#!/usr/bin/env bash
set -euo pipefail

SOURCE="sim"
CENTER_FREQ="6850000"
SAMPLE_RATE="2400000"
GAIN="38.6"
FPS="60"
IQ_PREFIX="iqproducer"
DB_OFFSET=""
WS_HOST="0.0.0.0"
WS_PORT="8765"
HTTP_PORT="8080"

usage() {
  cat <<'EOF'
Usage: ./script/run_mvp.sh [options]

Options:
  --source sim|rtlsdr|iqproducer
                           IQ source mode (default: sim)
  --center-freq HZ         Center frequency in Hz (default: 6850000)
  --sample-rate HZ         Sample rate in Hz (default: 2400000)
  --gain VALUE             Gain value or "auto" (default: 38.6)
  --fps VALUE              Producer FPS target (default: 60)
  --iq-prefix NAME         IQProducer shared memory prefix (default: iqproducer)
  --db-offset VALUE        Waterfall dB offset. Default: -35, or 0 for iqproducer mode
  --ws-host HOST           WebSocket bind host (default: 0.0.0.0)
  --ws-port PORT           WebSocket bind port (default: 8765)
  --http-port PORT         HTTP static server port (default: 8080)
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
    --iq-prefix)
      IQ_PREFIX="${2:-}"
      shift 2
      ;;
    --db-offset)
      DB_OFFSET="${2:-}"
      shift 2
      ;;
    --ws-host)
      WS_HOST="${2:-}"
      shift 2
      ;;
    --ws-port)
      WS_PORT="${2:-}"
      shift 2
      ;;
    --http-port)
      HTTP_PORT="${2:-}"
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

if [[ "$SOURCE" != "sim" && "$SOURCE" != "rtlsdr" && "$SOURCE" != "iqproducer" ]]; then
  echo "Invalid --source: $SOURCE (use sim, rtlsdr, or iqproducer)" >&2
  exit 1
fi

if [[ -z "$DB_OFFSET" ]]; then
  if [[ "$SOURCE" == "iqproducer" ]]; then
    DB_OFFSET="0"
  else
    DB_OFFSET="-35"
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-python}"
  echo "[INFO] Using active virtualenv: ${VIRTUAL_ENV}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
  echo "[INFO] Using project virtualenv: ${ROOT_DIR}/.venv"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

cleanup() {
  echo
  echo "Stopping MVP stack..."
  kill "${PRODUCER_PID:-}" "${GATEWAY_PID:-}" "${CLIENT_PID:-}" 2>/dev/null || true
  wait "${PRODUCER_PID:-}" "${GATEWAY_PID:-}" "${CLIENT_PID:-}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting producer..."
"$PYTHON_BIN" src/core_producer.py \
  --source "$SOURCE" \
  --center-freq "$CENTER_FREQ" \
  --sample-rate "$SAMPLE_RATE" \
  --gain "$GAIN" \
  --fps "$FPS" \
  --db-offset "$DB_OFFSET" \
  --iq-prefix "$IQ_PREFIX" &
PRODUCER_PID=$!

echo "Starting websocket gateway..."
"$PYTHON_BIN" src/ws_server.py --host "$WS_HOST" --port "$WS_PORT" &
GATEWAY_PID=$!

echo "Starting client static server on http://0.0.0.0:${HTTP_PORT} ..."
(
  cd client
  "$PYTHON_BIN" -m http.server "$HTTP_PORT"
) &
CLIENT_PID=$!

echo "MVP stack started. Press Ctrl+C to stop."
wait "$PRODUCER_PID" "$GATEWAY_PID" "$CLIENT_PID"
