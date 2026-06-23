---
type: adr
id: ADR-0001
title: "Install transformers via individual dependencies"
status: accepted
createdAt: "2026-06-23T22:30:00Z"
updatedAt: "2026-06-23T22:30:00Z"
tags: [headroom, compression, ml, dependencies]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0002-onnx-kompress-inference.adr.md"
  - "memories/0002-headroom-missing-transformers.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0001: Install transformers via individual dependencies

## Context

The BetterLiteLLM container was missing `transformers` and `onnxruntime` packages required for Headroom's ML compression (Kompress). All compression operations failed silently:

```
Compression failed, returning original messages: No module named 'transformers'
```

The `headroom-ai==0.26.0` package is installed but does not include ML compression dependencies in its core — they are opt-in extras.

## Decision

**Add individual dependencies to better-litellm proxy extra** — explicitly list only the two packages needed:

```toml
[project.optional-dependencies]
proxy = [
  ...
  "headroom-ai==0.26.0",
  "onnxruntime>=1.16.0",
  "transformers>=4.30.0,<6.0",
]
```

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Individual packages (Selected)** | Explicit, minimal (~60MB), low conflict risk | Requires knowing exact packages | — |
| **`headroom-ai[proxy]` extra** | Managed by upstream | Pulls in unnecessary deps (fastapi, websockets, watchdog); ~70-80MB | Unnecessary overhead |
| **`headroom-ai[ml]` extra** | Includes torch for full ML stack | ~800MB+ container with PyTorch | Overkill; PyTorch not needed |
| **Cloud mode** | No local deps | Network dependency, latency, cost | User chose local compression |

## Consequences

- **Positive:** Kompress compression fully functional; ONNX INT8 model (~260MB) cached on first use; minimal container size increase (~60MB packages + ~260MB model); no network dependency after initial model download
- **Negative:** Container size increases by ~320MB total; first startup requires HuggingFace access for model download; build time increases slightly
- **Neutral:** Dependency resolution tested clean with `uv sync --frozen --dry-run`
