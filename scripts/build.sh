#!/usr/bin/env bash
# build.sh — Build better-litellm Docker image locally (current platform only)
#
# Auto-detects version from pyproject.toml and tags as main-v{version}-stable.
# Uses current platform only — no buildx, no cross-compile.
#
# Usage:
#   ./scripts/build.sh                    # Build with auto-detected version tag
#   ./scripts/build.sh latest             # Build with custom tag

set -euo pipefail

FORK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(grep '^version' "$FORK_DIR/pyproject.toml" | head -1 | cut -d'"' -f2)"
TAG="${1:-main-v${VERSION}-stable}"
IMAGE="tuiteraz/better-litellm:${TAG}"

echo "=== better-litellm local build ==="
echo "Version:   $VERSION"
echo "Tag:       $TAG"
echo "Image:     $IMAGE"
echo ""

docker build -t "$IMAGE" -f "$FORK_DIR/Dockerfile" "$FORK_DIR"

echo ""
echo "Built $IMAGE (version: $VERSION, tag: $TAG)"
echo ""
echo "To test locally (port 4000):"
echo "  docker run -p 4000:4000 $IMAGE"
echo ""
echo "To test with docker-compose:"
echo "  docker compose -f docker-compose.test.yaml up -d"
