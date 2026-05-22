#!/bin/bash
# start-dev.sh — better-litellm local dev proxy
#
# Starts the LiteLLM proxy with the mammoth config (mammoth.lan:8014/v1).
#
#   ./scripts/start-dev.sh              # Start proxy on port 4000
#   ./scripts/start-dev.sh --stop       # Stop the proxy
#   ./scripts/start-dev.sh --port 4001  # Start on different port
#   ./scripts/start-dev.sh --help       # Show usage
#
# Requirements:
#   - better-litellm at ~/www/misc/better-litellm
#   - uv or python + pip installed
#   - mammoth.lan must resolve (see /etc/hosts or MAMMOTH_LAN_IP)

set -euo pipefail

# Auto-detect repo root from script location; override via BETTER_LITELLM_DIR env var
BETTER_LITELLM_DIR="${BETTER_LITELLM_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
LITELLM_PORT="${LITELLM_PORT:-4000}"
CONFIG_FILE="${CONFIG_FILE:-$BETTER_LITELLM_DIR/config.yaml}"

# Parse arguments
STOP=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --stop|-s)
      STOP=true
      shift
      ;;
    --port)
      LITELLM_PORT="$2"
      shift 2
      ;;
    --config)
      CONFIG_FILE="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --stop, -s    Stop the better-litellm proxy"
      echo "  --port NUM    Port for proxy (default: 4000)"
      echo "  --config PATH Path to config.yaml (default: ./config.yaml in repo root)"
      echo "  --help, -h    Show this help message"
      echo ""
      echo "Environment variables:"
      echo "  BETTER_LITELLM_DIR   Path to better-litellm (default: ~/www/misc/better-litellm)"
      echo "  LITELLM_PORT         Port for proxy (default: 4000)"
      echo "  CONFIG_FILE          Path to config.yaml (default: <repo>/config.yaml)"
      echo "  MAMMOTH_LAN_IP       IP of mammoth host (used to update /etc/hosts if needed)"
      echo ""
      echo "Mammoth hostname resolution:"
      echo "  mammoth.lan must resolve to the llama-swap host. Either:"
      echo "  - Add an entry to /etc/hosts: <MAMMOTH_IP> mammoth.lan"
      echo "  - Or export MAMMOTH_LAN_IP (script attempts to update /etc/hosts)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

if [ "$STOP" = true ]; then
  echo "Stopping listener(s) on port $LITELLM_PORT..."
  if command -v lsof &> /dev/null; then
    if lsof -nP -iTCP:"$LITELLM_PORT" -sTCP:LISTEN &> /dev/null; then
      lsof -ti :"$LITELLM_PORT" | xargs kill 2>/dev/null || true
      echo "  Sent SIGTERM to process(es) on :$LITELLM_PORT"
    else
      echo "  Nothing listening on :$LITELLM_PORT"
    fi
  else
    echo "  Install lsof to kill by port, or stop the proxy with Ctrl+C."
  fi
  echo "Done."
  exit 0
fi

# --- Check prerequisites ---
if [ ! -d "$BETTER_LITELLM_DIR" ]; then
  echo "ERROR: better-litellm directory not found: $BETTER_LITELLM_DIR"
  echo "Set BETTER_LITELLM_DIR"
  exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: Config file not found: $CONFIG_FILE"
  echo "Set CONFIG_FILE or create config.yaml in the repo root"
  exit 1
fi

# Check for uv (preferred) or python
if command -v uv &> /dev/null; then
  RUN_CMD="uv run --directory $BETTER_LITELLM_DIR litellm"
elif command -v python3 &> /dev/null; then
  RUN_CMD="python3 -m litellm.proxy.proxy_server"
else
  echo "ERROR: Neither uv nor python3 found on PATH"
  exit 1
fi

# Check if mammoth.lan resolves
check_mammoth_resolves() {
  if command -v getent &> /dev/null; then
    getent hosts mammoth.lan &> /dev/null
  else
    # Fallback: try ping
    ping -c 1 -W 2 mammoth.lan &> /dev/null
  fi
}

if ! check_mammoth_resolves; then
  echo "WARNING: mammoth.lan does not resolve."
  if [ -n "${MAMMOTH_LAN_IP:-}" ]; then
    echo "  MAMMOTH_LAN_IP is set to $MAMMOTH_LAN_IP — adding temporary /etc/hosts entry."
    if ! grep -q "mammoth.lan" /etc/hosts 2>/dev/null; then
      echo "  Adding: $MAMMOTH_LAN_IP mammoth.lan"
      # This requires sudo — the script will fail here if not running as root
      # We just warn and let the proxy fail with a clear error
      echo "  Run: sudo sh -c \"echo '$MAMMOTH_LAN_IP mammoth.lan' >> /etc/hosts\""
    else
      echo "  mammoth.lan already in /etc/hosts (but didn't resolve — check the entry)"
    fi
  fi
  echo "  The proxy will start but may fail to connect to mammoth."
  echo ""
fi

if command -v lsof &> /dev/null; then
  if lsof -nP -iTCP:"$LITELLM_PORT" -sTCP:LISTEN &> /dev/null; then
    echo "ERROR: port $LITELLM_PORT is already in use."
    echo "Stop it: $0 --stop   or use --port <other>"
    exit 1
  fi
fi

SCRIPT_HINT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
echo "better-litellm proxy (foreground) — leave this tab open; Ctrl+C stops."
echo "Stop: \"$SCRIPT_HINT\" --stop"
echo ""
echo "  Proxy:    http://127.0.0.1:$LITELLM_PORT"
echo "  Config:   $CONFIG_FILE"
echo "  Health:   http://127.0.0.1:$LITELLM_PORT/health"
echo ""

# --- Health check function ---
check_health() {
  curl -sf "http://127.0.0.1:${LITELLM_PORT}/health" | head -c 512 2>/dev/null
}

echo "Starting proxy..."
echo "Waiting for health check..."

# Start the proxy in background, wait for health
cd "$BETTER_LITELLM_DIR"
$RUN_CMD --port "$LITELLM_PORT" --config "$CONFIG_FILE" --detailed_messages &
PROXY_PID=$!

# Wait for health (up to 15 seconds)
HEALTHY=false
for i in $(seq 1 30); do
  if check_health > /dev/null 2>&1; then
    HEALTHY=true
    break
  fi
  sleep 0.5
done

if [ "$HEALTHY" = true ]; then
  echo ""
  echo "Proxy is healthy ✓"
  echo "  $LITELLM_PORT — litellm proxy running (PID $PROXY_PID)"
  echo ""
  echo "Available models (via /v1/models):"
  curl -sf "http://127.0.0.1:${LITELLM_PORT}/v1/models" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('data', []):
    print(f'  - {m[\"id\"]}')" 2>/dev/null || echo "  (could not list models)"
  echo ""
else
  # Bring proxy to foreground immediately so user can see errors
  echo "WARNING: Health check did not pass within 15s. Bringing proxy to foreground."
  echo "If mammoth.lan cannot resolve, the proxy may fail to start."
  wait "$PROXY_PID"
  exit $?
fi

# Bring proxy to foreground so Ctrl+C works
wait "$PROXY_PID"
exit $?
