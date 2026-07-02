---
type: adr
id: ADR-0007
title: "Claw Compactor integration via ASGI middleware"
status: accepted
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-06-30T12:00:00Z"
tags: [compression, claw-compactor, middleware, asgi, fusion-pipeline]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0006-abandon-headroom-adopt-claw-compactor.adr.md"
  - "concepts/0001-claw-compactor-fusion-pipeline.concept.md"
  - "memories/0005-headroom-integration-lessons.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0007: Claw Compactor integration via ASGI middleware

## Context

Claw Compactor must intercept chat completion requests to compress messages before they reach the LLM provider. The previous headroom integration confirmed ASGI middleware is the reliable pattern (callback hooks failed silently).

## Decision

**Integrate Claw Compactor as ASGI middleware** in better-litellm fork, following the headroom ASGI pattern with improvements based on lessons learned.

### Integration Point

Register in `litellm/proxy/proxy_server.py` at approximately line 15940, before `RequestSizeLimitMiddleware`:

```python
# Claw Compactor compression middleware — optional
try:
    from claw_compactor import FusionEngine
    _CLAW_COMPACTOR_AVAILABLE = True
except ImportError:
    _CLAW_COMPACTOR_AVAILABLE = False

if _CLAW_COMPACTOR_AVAILABLE and os.environ.get("CLAW_COMPACTOR_ENABLED"):
    from .middleware.claw_compactor_middleware import ClawCompactorMiddleware
    app.add_middleware(
        ClawCompactorMiddleware,
        enable_rewind=True,
        min_tokens=500,
        max_latency_ms=100,
    )
```

### Content Routing

**Compress:** system, assistant, tool messages
**Skip:** user messages (intent preservation — same as headroom's successful pattern)

### Rewind Store

Enable reversible compression by default with in-memory LRU store:
- `max_memory_mb`: 100
- `ttl_seconds`: 3600 (1 hour)
- `eviction_policy`: LRU

### Error Handling

**Transparent fallback** — compression failures pass through original content without blocking. Compression is optimization, not core functionality.

### Metrics

Use `claw_compactor.*` prefix (new — avoids confusion with headroom metrics):
- `claw_compactor.tokens_input` (counter)
- `claw_compactor.tokens_compressed` (counter)
- `claw_compactor.tokens_saved` (counter)
- `claw_compactor.runs` (counter)
- `claw_compactor.duration_ms` (histogram)
- `claw_compactor.failures` (counter)

Dashboard queries must use `sumIf(delta > 0)` pattern (lesson from headroom OTEL metrics).

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CLAW_COMPACTOR_ENABLED` | `false` | Enable middleware |
| `CLAW_COMPACTOR_REWIND` | `true` | Enable reversible compression |
| `CLAW_COMPACTOR_MIN_TOKENS` | `500` | Minimum tokens to trigger |
| `CLAW_COMPACTOR_MAX_LATENCY_MS` | `100` | Maximum compression time |
| `CLAW_COMPACTOR_MODEL_LIMIT` | `200000` | Maximum context size |

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| **Pre-request callback** | Headroom callback failed silently — unreliable |
| **Sidecar proxy service** | Added infrastructure complexity, additional network hop |

## Consequences

- **Positive:** Proven ASGI middleware pattern; independent of LiteLLM callback system; early request interception
- **Positive:** No tiktoken encoding issues — Claw Compactor uses own heuristic estimation with optional tiktoken fallback
- **Negative:** Adds latency to all requests (even uncompressed ones for gate evaluation)
- **Negative:** Requires careful middleware stack ordering (before RequestSizeLimitMiddleware)
