# 02 — Docker Build Infrastructure

**Date:** 2026-05-30
**Status:** Implemented (Phase: Completed)
**Branch:** `feat/spec-01`

---

## Description

Add Docker build scripts and local test compose to the better-litellm fork so the patched LiteLLM image can be built (cross-platform, MacBook arm64 → puma amd64) and pushed to Docker Hub for deployment on puma.lan.

---

## Problem

- **Current state:** puma.lan runs `ghcr.io/berriai/litellm:main-v1.83.14-stable` — upstream image without the 6 Qwen tool call patches
- **Need:** A Docker image with the patches, pullable by puma (amd64)
- **Constraint:** MacBook (arm64) builds for puma (amd64) — requires `docker buildx` cross-platform build
- **`lw.sh` cannot help:** it's a Python venv tool, not a Docker builder

---

## Solution

### Build Scripts

Two scripts in `scripts/`, following the `hugging-kreuzberg-mcp` pattern:

| Script | Purpose | Flags |
|--------|---------|-------|
| `build.sh` | Local build (current platform) | Custom tag as `$1` |
| `build-and-push.sh` | Multi-arch build + Docker Hub push | `--extra-tags`, `--dry-run`, `--build-only`, `--tag`, `--platform` |

Both auto-detect version from `pyproject.toml` → tag as `main-v{version}-stable` (e.g., `main-v1.87.0-stable`).

### `lw.sh` Integration

Added `docker-build` command to `lw.sh` that delegates to `build-and-push.sh`, keeping the unified workflow helper pattern:

```bash
./scripts/lw.sh docker-build              # Build + push (auto version)
./scripts/lw.sh docker-build --extra-tags # Also tag with commit hash
./scripts/lw.sh docker-build --dry-run    # Preview commands
```

### Local Test Compose

`docker-compose.test.yaml` + `test-config.yaml` in the fork root for local validation on MacBook before deploying to puma. Minimal setup: LiteLLM + Postgres, port 4000.

### puma-lan Compose Update

Changed `image:` in `puma-lan/lite-llm/docker-compose.yaml` from upstream to the Docker Hub image.

---

## Architecture Decisions

1. **Tag strategy:** `main-v{version}-stable` — matches upstream convention, version from `pyproject.toml`
2. **Registry:** Docker Hub (`tuiteraz/better-litellm`) — matches existing homelab pattern
3. **Multi-arch:** Both amd64 and arm64 by default; `--platform linux/amd64` for faster builds
4. **Dockerfile:** Fork's existing Dockerfile used as-is (no modifications)
5. **Script location:** `scripts/` directory, alongside `lw.sh`

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `scripts/build.sh` | Created | Local Docker build script |
| `scripts/build-and-push.sh` | Created | Multi-arch build + Docker Hub push |
| `scripts/lw.sh` | Modified | Added `docker-build` command |
| `docker-compose.test.yaml` | Created | Local test compose (LiteLLM + Postgres) |
| `test-config.yaml` | Created | Minimal test config (one fake model) |
| `docs/BETTER-LITELLM.md` | Modified | Added Docker Build section |
| `docs/spec/02-docker-build-infrastructure.md` | Created | This spec |
| `puma-lan/lite-llm/docker-compose.yaml` | Modified | Changed `image:` to Docker Hub |

---

## Rollback

Revert `puma-lan/lite-llm/docker-compose.yaml` to:

```yaml
image: ghcr.io/berriai/litellm:main-v1.83.14-stable
```

Then restart on puma.
