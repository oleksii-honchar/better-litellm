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
  help              Show this help message

Environment:
  BETTER_LITELLM_DIR   Override repo root (default: auto-detected)
  LITELLM_PORT         Override proxy port (default: 4000)

Examples:
  $0 setup                    # First time: create venv + install
  $0 sync                     # Pull upstream changes, rebase
  $0 build                    # Reinstall after changes
  $0 sbr                      # Sync + build + start proxy
  $0 sync --theirs            # Force-upstream on conflicts
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
    echo "No .venv found. Run '$0 setup' first."
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

# --- Commands ---

cmd_setup() {
  assert_in_repo
  echo "Setting up better-litellm venv..."

  if [[ -d "$REPO_DIR/.venv" ]]; then
    echo "Venv already exists — running build instead. Use 'rebuild' to recreate."
    cmd_build
    return
  fi

  python3 -m venv "$REPO_DIR/.venv"
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
  echo "Recreating venv from scratch..."
  rm -rf "$REPO_DIR/.venv"
  python3 -m venv "$REPO_DIR/.venv"
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
  help|-h|--help)  usage ;;
  *)          echo "Unknown command: $1"; echo; usage; exit 1 ;;
esac
