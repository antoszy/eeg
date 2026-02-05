#!/usr/bin/env bash
# Muse 2 EEG Dashboard — one-shot launcher.
#
# Connects to the Muse headband, starts the server, and opens the browser.
#
# Usage:
#   ./start.sh              # Live mode (connect to Muse 2)
#   ./start.sh --synthetic  # Synthetic mode (no hardware needed)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="127.0.0.1"
PORT=8080
URL="http://${HOST}:${PORT}"
SYNTHETIC=false
SERVER_PID=""

for arg in "$@"; do
    case "$arg" in
        --synthetic) SYNTHETIC=true ;;
    esac
done

cleanup() {
    echo ""
    echo "Shutting down..."
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    echo "Done."
}
trap cleanup EXIT INT TERM

# Kill any existing server on our port
if lsof -ti:"$PORT" >/dev/null 2>&1; then
    echo "Killing existing process on port $PORT..."
    lsof -ti:"$PORT" | xargs kill 2>/dev/null || true
    sleep 1
fi

# Connect to Muse (skip in synthetic mode)
if [[ "$SYNTHETIC" == false ]]; then
    echo "=== Connecting to Muse 2 ==="
    bash "$SCRIPT_DIR/connect-muse.sh" || {
        echo "Muse connection failed — BrainFlow will attempt its own BLE connection."
    }
    echo ""
fi

# Start the server
echo "=== Starting EEG Dashboard ==="
if [[ "$SYNTHETIC" == true ]]; then
    python "$SCRIPT_DIR/main.py" --synthetic --host "$HOST" --port "$PORT" &
else
    python "$SCRIPT_DIR/main.py" --host "$HOST" --port "$PORT" &
fi
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for server..."
for i in $(seq 1 30); do
    if curl -s "$URL/api/info" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -s "$URL/api/info" >/dev/null 2>&1; then
    echo "ERROR: Server failed to start. Check logs."
    exit 1
fi

# Show mode
MODE=$(curl -s "$URL/api/info" | python -c "import sys,json; print('LIVE' if not json.load(sys.stdin)['is_synthetic'] else 'SYNTHETIC')")
echo "Dashboard running at $URL (mode: $MODE)"

# Open browser
echo "Opening browser..."
xdg-open "$URL" 2>/dev/null &

# Keep running until Ctrl+C
echo "Press Ctrl+C to stop."
wait "$SERVER_PID"
