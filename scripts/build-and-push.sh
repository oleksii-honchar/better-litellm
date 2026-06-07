#!/usr/bin/env bash
# build-and-push.sh — Build and push better-litellm Docker image
#
# Builds from the better-litellm fork and pushes to Docker Hub
# under the tuiteraz namespace. Follows hugging-kreuzberg-mcp pattern.
#
# Tag strategy: version-based tags from pyproject.toml
#   e.g. main-v1.87.0-stable (matching upstream convention)
#   plus commit hash tag for traceability
#
# Usage:
#   ./scripts/build-and-push.sh                     # Build + push (auto version tag)
#   ./scripts/build-and-push.sh --extra-tags        # Also tag with commit hash
#   ./scripts/build-and-push.sh --dry-run           # Show commands, don't execute
#   ./scripts/build-and-push.sh --build-only        # Build only, skip push
#   ./scripts/build-and-push.sh --tag main-v1.87.0-stable  # Specific tag
#   ./scripts/build-and-push.sh --platform linux/amd64     # Single platform
#
# Prerequisites:
#   - Docker Desktop with buildx (multi-arch)
#   - Logged in to Docker Hub: docker login
#   - On correct branch: git checkout feat/spec-01

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
REGISTRY="docker.io"
NAMESPACE="tuiteraz"
REPO="better-litellm"
IMAGE_BASE="${REGISTRY}/${NAMESPACE}/${REPO}"
FORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── Defaults ───────────────────────────────────────────────────────────────────
BUILD_ONLY=false
DRY_RUN=false
EXTRA_TAGS=false
VERSION="$(grep '^version' "$FORK_DIR/pyproject.toml" | head -1 | cut -d'"' -f2)"
COMMIT="$(git -C "$FORK_DIR" rev-parse --short HEAD)"
TAG="main-v${VERSION}-stable"
PLATFORM="linux/amd64,linux/arm64"

# ── Parse flags ────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --build-only) BUILD_ONLY=true ;;
    --dry-run)    DRY_RUN=true ;;
    --extra-tags) EXTRA_TAGS=true ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --build-only         Build only, skip push"
      echo "  --dry-run            Show commands without executing"
      echo "  --extra-tags         Also tag with commit hash (e.g. 4b61be3)"
      echo "  --tag TAG            Tag to use (default: main-v<VERSION>-stable)"
      echo "  --platform PLATFORM  Docker platform(s) (default: linux/amd64,linux/arm64)"
      echo ""
      echo "Examples:"
      echo "  $0                                             # Build + push (auto version)"
      echo "  $0 --extra-tags                                # Version + commit hash"
      echo "  $0 --build-only --platform linux/amd64         # AMD64 only, no push"
      echo "  $0 --dry-run                                   # Preview commands"
      echo ""
      echo "Note: Requires docker login to ${REGISTRY}/${NAMESPACE}"
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# ── Pre-flight checks ─────────────────────────────────────────────────────────
echo "=== better-litellm build-and-push ==="
echo ""

docker ps >/dev/null 2>&1 || { echo "ERROR: Docker is not running"; exit 1; }

if ! docker buildx version >/dev/null 2>&1; then
  echo "ERROR: docker buildx not available"
  exit 1
fi

if [ ! -f "$FORK_DIR/Dockerfile" ]; then
  echo "ERROR: Dockerfile not found: $FORK_DIR/Dockerfile"
  exit 1
fi

CURRENT_BRANCH=$(git -C "$FORK_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

echo "Branch:          $CURRENT_BRANCH"
echo "Commit:          $COMMIT"
echo "Version:         $VERSION"
echo "Image base:      ${IMAGE_BASE}"
echo "Tag:             ${TAG}"
echo "Platform:        ${PLATFORM}"
echo ""

# ── Helper ─────────────────────────────────────────────────────────────────────
run_cmd() {
  if [ "$DRY_RUN" = true ]; then
    echo "  [DRY RUN] Would execute: $*"
    return 0
  fi
  "$@"
}

# ── Build phase ────────────────────────────────────────────────────────────────
image_tag="${IMAGE_BASE}:${TAG}"

echo "=== Building: ${image_tag} ==="

if [ "$BUILD_ONLY" = true ]; then
  # Local-only build (no push, no multi-arch — just current platform)
  run_cmd docker buildx build \
    --platform "${PLATFORM}" \
    --tag "${image_tag}" \
    --load \
    --progress=plain \
    -f "$FORK_DIR/Dockerfile" \
    "$FORK_DIR"
else
  # Build + push with buildx
  run_cmd docker buildx build \
    --platform "${PLATFORM}" \
    --tag "${image_tag}" \
    --push \
    --progress=plain \
    -f "$FORK_DIR/Dockerfile" \
    "$FORK_DIR"
fi

echo ""
echo "  ✓ Pushed: ${image_tag}"

# ── Extra tags (commit hash for traceability) ──────────────────────────────────
if [ "$EXTRA_TAGS" = true ]; then
  commit_tag="${IMAGE_BASE}:${COMMIT}"

  echo "=== Tagging with commit: ${commit_tag} ==="

  if [ "$BUILD_ONLY" = true ]; then
    run_cmd docker buildx build \
      --platform "${PLATFORM}" \
      --tag "${commit_tag}" \
      --load \
      --progress=plain \
      -f "$FORK_DIR/Dockerfile" \
      "$FORK_DIR"
  else
    run_cmd docker buildx build \
      --platform "${PLATFORM}" \
      --tag "${commit_tag}" \
      --push \
      --progress=plain \
      -f "$FORK_DIR/Dockerfile" \
      "$FORK_DIR"
  fi

  echo "  ✓ Pushed: ${commit_tag}"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "=== Summary ==="
echo "  Primary tag: ${image_tag}"
if [ "$EXTRA_TAGS" = true ]; then
  echo "  Commit tag:  ${IMAGE_BASE}:${COMMIT}"
fi
echo ""
echo "To use on puma.lan:"
echo "  1. Update docker-compose.yaml:"
echo "     image: ${image_tag}"
echo "  2. Restart: cd ~/puma-lan/lite-llm && ./restart.sh"
echo ""
echo "Done ✓"
