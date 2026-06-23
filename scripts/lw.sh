#!/bin/bash
# lw.sh — better-litellm workflow helper
#
# Wraps the manual commands from docs/GOVERNANCE.md so you don't
# have to type them out every time.
#
#   ./scripts/lw.sh help              # Show this help
#   ./scripts/lw.sh setup             # One-time venv setup + install
#   ./scripts/lw.sh rebuild           # Recreate venv from scratch
#   ./scripts/lw.sh build             # Install/update in active venv
#   ./scripts/lw.sh sync              # Pull upstream + rebase patched/main
#   ./scripts/lw.sh sync --theirs     # Pull upstream, accept theirs on conflicts
#   ./scripts/lw.sh start             # Start dev proxy (delegates to start-dev.sh)
#   ./scripts/lw.sh stop              # Stop dev proxy
#   ./scripts/lw.sh startuv           # Start via uv (no venv activation needed)
#   ./scripts/lw.sh push              # Push patched/main to origin
#   ./scripts/lw.sh sbr               # Full cycle: sync → build → start
#   ./scripts/lw.sh docker-build      # Build Docker image (delegates to build-and-push.sh)
#   ./scripts/lw.sh start-prod        # Start proxy with prod env (Infisical + puma-lan config)
#
# All commands auto-detect the repo root from this script's location.
# Override with BETTER_LITELLM_DIR env var.

set -euo pipefail

# Auto-detect repo root
REPO_DIR="${BETTER_LITELLM_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<EOF
better-litellm workflow helper

Usage: $0 <command> [options]

Commands:
  setup             One-time venv setup + editable install + verify
  rebuild           Recreate venv from scratch (resolves dependency conflicts)
  build             Install/update editable deps in current venv
  sync              Fetch upstream main, rebase patched/main onto it
  sync --theirs     Same as sync but accepts upstream for non-patch conflicts
  start             Start dev proxy (uses scripts/start-dev.sh)
  stop              Stop dev proxy
  startuv           Start dev proxy via uv (no venv activation needed)
  push              Push patched/main to origin (regular push, not force)
  sbr               Full cycle: sync → build → start
  docker-build      Build + push Docker image (delegates to build-and-push.sh)
  start-prod        Start source-code proxy with prod config + Infisical secrets
  help              Show this help message

Environment:
  BETTER_LITELLM_DIR   Override repo root (default: auto-detected)
  LITELLM_PORT         Override proxy port (default: 4000)
  PUMA_LAN_DIR         Path to puma-lan repo (default: ~/puma-lan)
  CONFIG_FILE          Override config path (default: \$PUMA_LAN_DIR/lite-llm/config.yaml)

Examples:
  $0 setup                    # First time: create venv + install
  $0 sync                     # Pull upstream changes, rebase
  $0 build                    # Reinstall after changes
  $0 sbr                      # Sync + build + start proxy
  $0 sync --theirs            # Force-upstream on conflicts
  $0 start-prod               # Start proxy with prod Infisical secrets + config
EOF
}

# --- Utility functions ---

assert_in_repo() {
  if [[ "$(pwd)" != "$REPO_DIR" ]]; then
    echo "Running from $REPO_DIR"
    cd "$REPO_DIR"
  fi
}

assert_upstream() {
  if ! git remote | grep -q '^upstream$'; then
    echo "No 'upstream' remote. Adding BerriAI/litellm as upstream..."
    git remote add upstream https://github.com/BerriAI/litellm.git
    echo "Added upstream. To change: git remote set-url upstream <URL>"
  fi
}

assert_venv() {
  if [[ ! -d "$REPO_DIR/.venv" ]]; then
    echo "No .venv directory found. Run '$0 setup' or '$0 rebuild' first."
    exit 1
  fi
  if [[ ! -f "$REPO_DIR/.venv/bin/activate" ]]; then
    echo ".venv directory exists but activation script is missing — venv is corrupted."
    echo "Run '$0 rebuild' to recreate it from scratch."
    exit 1
  fi
}

ensure_venv_active() {
  assert_venv
  # Check if we're already in the venv
  if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    echo "Venv not activated — activating now."
    source "$REPO_DIR/.venv/bin/activate"
  fi
}

choose_installer() {
  # Prefer uv if available, fall back to pip
  if command -v uv &> /dev/null; then
    echo "uv"
  else
    echo "pip"
  fi
}

choose_python() {
  # litellm[proxy] requires Python >=3.10, <3.14
  # Try known good versions in order of preference
  for py in python3.12 python3.11 python3.10 python3; do
    if command -v "$py" &> /dev/null; then
      local ver
      ver=$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
      if [[ "$ver" =~ ^3\.(1[0-3])(\.[0-9]+)?$ ]]; then
        echo "$py"
        return
      fi
    fi
  done
  echo ""
  echo "ERROR: No suitable Python found. litellm[proxy] requires Python >=3.10, <3.14." >&2
  echo "  Install one of: python3.10, python3.11, python3.12" >&2
  return 1
}

# --- Commands ---

cmd_setup() {
  assert_in_repo
  local python_bin
  python_bin=$(choose_python) || exit 1
  echo "Setting up better-litellm venv (using $python_bin)..."

  if [[ -d "$REPO_DIR/.venv" ]]; then
    if [[ -f "$REPO_DIR/.venv/bin/activate" ]]; then
      echo "Venv already exists — running build instead. Use 'rebuild' to recreate."
      cmd_build
      return
    else
      echo "Existing .venv directory is corrupted (missing activate script). Recreating..."
      rm -rf "$REPO_DIR/.venv"
    fi
  fi

  "$python_bin" -m venv "$REPO_DIR/.venv"
  source "$REPO_DIR/.venv/bin/activate"

  local installer
  installer=$(choose_installer)
  echo "Installing editable with $installer..."
  if [[ "$installer" == "uv" ]]; then
    uv pip install -e ".[proxy,dev]"
  else
    pip install -e ".[proxy,dev]"
  fi

  echo ""
  echo "Verifying install..."
  litellm --version
  echo ""
  echo "Setup complete. To activate later:"
  echo "  source $REPO_DIR/.venv/bin/activate"
}

cmd_rebuild() {
  assert_in_repo
  local python_bin
  python_bin=$(choose_python) || exit 1
  echo "Recreating venv from scratch (using $python_bin)..."
  rm -rf "$REPO_DIR/.venv"
  "$python_bin" -m venv "$REPO_DIR/.venv"
  source "$REPO_DIR/.venv/bin/activate"

  local installer
  installer=$(choose_installer)
  echo "Installing editable with $installer..."
  if [[ "$installer" == "uv" ]]; then
    uv pip install -e ".[proxy,dev]"
  else
    pip install -e ".[proxy,dev]"
  fi

  litellm --version
  echo "Rebuild complete."
}

cmd_build() {
  assert_in_repo
  ensure_venv_active

  local installer
  installer=$(choose_installer)
  echo "Reinstalling editable with $installer..."
  if [[ "$installer" == "uv" ]]; then
    uv pip install -e ".[proxy,dev]"
  else
    pip install -e ".[proxy,dev]"
  fi
  echo "Build complete."
}

cmd_sync() {
  assert_in_repo
  assert_upstream
  local accept_theirs=false
  if [[ "${1:-}" == "--theirs" ]]; then
    accept_theirs=true
  fi

  echo "Fetching upstream..."
  git fetch upstream main:upstream-main

  echo "Switching to patched/main..."
  git switch patched/main

  if [[ "$accept_theirs" == true ]]; then
    echo "Rebasing with -X theirs (accepts upstream on non-patch conflicts)..."
    git rebase -i upstream-main -X theirs
  else
    echo "Rebasing onto upstream-main..."
    git rebase -i upstream-main
  fi

  echo ""
  echo "Sync complete. Push with: $0 push"
}

cmd_start() {
  assert_in_repo
  exec "$SCRIPT_DIR/start-dev.sh" "$@"
}

cmd_stop() {
  assert_in_repo
  exec "$SCRIPT_DIR/start-dev.sh" --stop
}

cmd_startuv() {
  assert_in_repo

  if ! command -v uv &> /dev/null; then
    echo "uv not found. Install it: pip install uv"
    exit 1
  fi

  local port="${LITELLM_PORT:-4000}"
  local config="${CONFIG_FILE:-$REPO_DIR/config.yaml}"

  if [[ ! -f "$config" ]]; then
    echo "Config not found: $config"
    exit 1
  fi

  echo "Starting proxy via uv on port $port..."
  uv run --directory "$REPO_DIR" litellm --port "$port" --config "$config"
}

cmd_start_prod() {
  assert_in_repo

  # Check prerequisites
  if ! command -v infisical &> /dev/null; then
    echo "ERROR: infisical CLI not found — required for prod secrets."
    echo "  Install: npm install -g @infisical/cli"
    echo "  Login:   infisical login"
    echo "  Docs:    https://infisical.com/docs/cli/install"
    exit 1
  fi

  if ! command -v uv &> /dev/null; then
    echo "ERROR: uv not found. Install: pip install uv"
    exit 1
  fi

  local port="${LITELLM_PORT:-4000}"
  local puma_lan_dir="${PUMA_LAN_DIR:-$HOME/puma-lan}"
  local config="${CONFIG_FILE:-$puma_lan_dir/lite-llm/config.yaml}"

  if [[ ! -f "$config" ]]; then
    echo "ERROR: Prod config not found: $config"
    echo ""
    echo "  start-prod uses the puma-lan/lite-llm config.yaml (not the dev config)"
    echo "  Set PUMA_LAN_DIR or CONFIG_FILE to point to your puma-lan checkout."
    echo ""
    echo "  Expected: \$PUMA_LAN_DIR/lite-llm/config.yaml"
    echo "  Current:  PUMA_LAN_DIR=$puma_lan_dir"
    exit 1
  fi

  # Check / start litellm-db (Postgres) — required for prod mode.
  # When running from source (not Docker), we need:
  #   (a) Container running
  #   (b) Port 5432 exposed on host (config.yaml uses "litellm-db:5432" — Docker DNS)
  #   (c) DATABASE_URL overridden to localhost
  local db_port_exposed=false
  if docker container inspect lite-llm-db &>/dev/null; then
    # Container exists
    if docker ps --format '{{.Names}}' | grep -q '^lite-llm-db$'; then
      echo "  lite-llm-db: ✓ running"
      docker port lite-llm-db 5432 &>/dev/null && db_port_exposed=true
    else
      echo "  lite-llm-db: container exists but stopped — starting..."
      docker start lite-llm-db
      echo "  Waiting for Postgres..."
      sleep 3
    fi
  fi

  if [[ "$db_port_exposed" != true ]]; then
    if docker container inspect lite-llm-db &>/dev/null; then
      echo "  lite-llm-db: port 5432 not exposed — recreating with host port..."
      docker rm -f lite-llm-db
    fi
    if [[ -f "$puma_lan_dir/lite-llm/docker-compose.yaml" ]]; then
      echo "  lite-llm-db: starting from compose with port 5432 exposed..."
      docker compose -f "$puma_lan_dir/lite-llm/docker-compose.yaml" \
        run -d --publish 5432:5432 --name lite-llm-db litellm-db
      echo "  Waiting for Postgres health check..."
      sleep 5
    else
      echo "  lite-llm-db: starting with default params..."
      docker run -d --name lite-llm-db \
        --network puma-net \
        -p 5432:5432 \
        -e POSTGRES_USER=litellm \
        -e POSTGRES_PASSWORD=litellm_db_password \
        -e POSTGRES_DB=litellm \
        -v litellm-db-data:/var/lib/postgresql/data \
        postgres:16-alpine
      echo "  Waiting for Postgres..."
      sleep 5
    fi
    db_port_exposed=true
  fi

  # Verify DB is reachable via localhost
  echo "  lite-llm-db: verifying host access..."
  if python3 -c "
import socket
s = socket.create_connection(('localhost', 5432), timeout=5)
s.close()
" 2>/dev/null; then
    echo "  lite-llm-db: ✓ accessible at localhost:5432"
  else
    echo "  lite-llm-db: ⚠ not reachable at localhost:5432 — check container logs"
  fi

  # Prisma client generation — required for STORE_MODEL_IN_DB=True
  # Note: `import prisma` succeeds even without generation (the package is installed).
  # We must check for generated model files specifically.
  echo "  prisma:   checking generated client..."
  local prisma_models_marker
  prisma_models_marker=$("$REPO_DIR/.venv/bin/python" -c "
import prisma, os
m = os.path.join(prisma.__path__[0], 'models.py')
print(m)
" 2>/dev/null)

  if [[ -n "$prisma_models_marker" && -f "$prisma_models_marker" ]]; then
    echo "  prisma:   ✓ generated"
  elif [[ ! -f "$REPO_DIR/.venv/bin/python" ]]; then
    echo "  prisma:   ✗ no venv at $REPO_DIR/.venv — run '$0 setup' or '$0 rebuild' first"
    exit 1
  else
    echo "  prisma:   installing matching version..."
    # Use the version range from pyproject.toml (>=0.11.0,<1.0)
    "$REPO_DIR/.venv/bin/pip" install "prisma>=0.11.0,<1.0" 2>&1 | sed 's/^/           /'
    echo "  prisma:   generating client..."
    # Add venv bin to PATH so prisma-client-py generator is found by the prisma CLI
    PATH="$REPO_DIR/.venv/bin:$PATH" \
      "$REPO_DIR/.venv/bin/prisma" generate --schema="$REPO_DIR/schema.prisma" 2>&1 | sed 's/^/           /'
    echo "  prisma:   ✓ ready"
  fi

  echo ""
  echo "Starting litellm proxy (prod mode) from source..."
  echo "  Mode:     infisical run --env=prod --path=/lite-llm"
  echo "  Config:   $config"
  echo "  Port:     $port"
  echo "  Source:   $REPO_DIR"
  echo ""

  # NOTE: Some docker-compose.yaml env vars reference Docker-internal DNS names
  # (e.g. clickstack-otel-collector:4317) which won't resolve on the host.
  # If the OTel collector port is not exposed to the host, override via:
  #   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
  #   HEADROOM_OTEL_METRICS_ENDPOINT=http://localhost:4318 \
  #   ./scripts/lw.sh start-prod
  #
  # How Infisical is used:
  # 1. `infisical run --env=prod --path=/lite-llm` fetches ALL secrets from the
  #    `/lite-llm` path in Infisical's `prod` environment (LITELLM_MASTER_KEY,
  #    UI_USERNAME, UI_PASSWORD, ANTHROPIC_API_KEY, OPENAI_API_KEY,
  #    MOONSHOT_API_KEY, MINIMAX_API_KEY, DEEPSEEK_API_KEY, HYPERDX_API_KEY, ...).
  # 2. Those secrets become environment variables for the `bash -c '...'` child process.
  # 3. Inside that child, we set the non-secret hardcoded env vars (TZ, OTEL endpoints,
  #    Headroom config) and compose OTEL_EXPORTER_OTLP_HEADERS from HYPERDX_API_KEY.
  # 4. All expansion happens AFTER Infisical injects its secrets, so HYPERDX_API_KEY
  #    is available when constructing OTEL_EXPORTER_OTLP_HEADERS.
  #
  # Required setup on the remote host:
  #   npm install -g @infisical/cli && infisical login

  # Export these so they're available inside the `bash -c` subprocess
  export REPO_DIR
  export port
  export config

  infisical run --env=prod --path=/lite-llm -- \
    bash -c '
      set -euo pipefail

      # === Secrets from Infisical (injected by `infisical run`) ===
      # LITELLM_MASTER_KEY, UI_USERNAME, UI_PASSWORD, ANTHROPIC_API_KEY,
      # OPENAI_API_KEY, MOONSHOT_API_KEY, MINIMAX_API_KEY, DEEPSEEK_API_KEY,
      # HYPERDX_API_KEY, ... — already in env at this point.

      # === Overrides for source-code mode (host, not Docker) ===
      # Postgres: config.yaml uses `litellm-db:5432` (Docker DNS).
      # When running from source on the host, DB port is now published to localhost.
      export DATABASE_URL="postgresql://litellm:litellm_db_password@localhost:5432/litellm"

      # OTel: Docker DNS names (clickstack-otel-collector) wont resolve on host.
      # Default to localhost — Override via OTEL_EXPORTER_OTLP_ENDPOINT env var
      # if the collector port is on a different host.
      export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4317}"
      export HEADROOM_OTEL_METRICS_ENDPOINT="${HEADROOM_OTEL_METRICS_ENDPOINT:-http://localhost:4318/v1/metrics}"

      # === Non-secret env vars (hardcoded in docker-compose.yaml) ===
      export TZ=Europe/Madrid
      export DOCS_URL="${DOCS_URL:-/docs}"
      export ROOT_REDIRECT_URL="${ROOT_REDIRECT_URL:-/ui}"
      export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
      # Composed from Infisical-provided HYPERDX_API_KEY (resolved inside this context)
      export OTEL_EXPORTER_OTLP_HEADERS="authorization=${HYPERDX_API_KEY}"
      export OTEL_SERVICE_NAME=litellm
      export OTEL_TRACES_EXPORTER=otlp
      export OTEL_METRICS_EXPORTER=none
      export STORE_MODEL_IN_DB=True
      export HEADROOM_OTEL_METRICS_ENABLED=true
      export HEADROOM_OTEL_METRICS_EXPORTER=otlp_http
      export HEADROOM_OTEL_SERVICE_NAME=headroom-proxy

      # REPO_DIR, port, config are exported from the outer script — available as env vars
      exec uv run --directory "$REPO_DIR" litellm \
        --port "$port" \
        --config "$config"
    '
}

cmd_push() {
  assert_in_repo
  echo "Pushing patched/main to origin..."
  git push origin patched/main
}

cmd_sbr() {
  # sync → build → start (full cycle)
  cmd_sync
  cmd_build
  cmd_start
}

cmd_docker_build() {
  assert_in_repo

  if [[ ! -f "$SCRIPT_DIR/build-and-push.sh" ]]; then
    echo "build-and-push.sh not found at $SCRIPT_DIR/build-and-push.sh"
    exit 1
  fi

  exec "$SCRIPT_DIR/build-and-push.sh" "$@"
}

# --- Main dispatch ---

case "${1:-help}" in
  setup)      cmd_setup ;;
  rebuild)    cmd_rebuild ;;
  build)      cmd_build ;;
  sync)       shift; cmd_sync "$@" ;;
  start)      shift; cmd_start "$@" ;;
  stop)       cmd_stop ;;
  startuv)    cmd_startuv ;;
  push)       cmd_push ;;
  sbr)        cmd_sbr ;;
  start-prod) cmd_start_prod ;;
  docker-build) shift; cmd_docker_build "$@" ;;
  help|-h|--help)  usage ;;
  *)          echo "Unknown command: $1"; echo; usage; exit 1 ;;
esac
