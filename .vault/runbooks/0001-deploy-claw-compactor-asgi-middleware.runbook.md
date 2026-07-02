---
type: runbook
title: "Deploy Claw Compactor as ASGI middleware in better-litellm"
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-06-30T12:00:00Z"
tags: [runbook, claw-compactor, asgi, middleware, deployment, litellm]
see_also:
  - "adrs/0007-claw-compactor-asgi-middleware.adr.md"
  - "concepts/0001-claw-compactor-fusion-pipeline.concept.md"
  - "memories/0005-headroom-integration-lessons.memory.md"
---

# Deploy Claw Compactor as ASGI middleware in better-litellm

## Prerequisites

- [ ] `claw-compactor` package added to `pyproject.toml` dependencies
- [ ] Docker image rebuilt with `claw-compactor` installed
- [ ] Environment variable `CLAW_COMPACTOR_ENABLED=true` configured

## Steps

### 1. Add middleware to proxy_server.py

In `litellm/proxy/proxy_server.py`, at approximately line 15940 (before `RequestSizeLimitMiddleware`), add:

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

### 2. Create middleware implementation

Create `litellm/proxy/middleware/claw_compactor_middleware.py`:

```python
import time
from typing import Any
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Send, Scope
from opentelemetry import metrics

meter = metrics.get_meter_provider().get_meter("claw_compactor")
tokens_input = meter.create_counter("claw_compactor.tokens_input")
tokens_compressed = meter.create_counter("claw_compactor.tokens_compressed")
tokens_saved = meter.create_counter("claw_compactor.tokens_saved")
runs = meter.create_counter("claw_compactor.runs")
duration_ms = meter.create_histogram("claw_compactor.duration_ms")
failures = meter.create_counter("claw_compactor.failures")

class ClawCompactorMiddleware:
    def __init__(self, app, enable_rewind: bool = True, min_tokens: int = 500, max_latency_ms: int = 100):
        self.app = app
        self.enable_rewind = enable_rewind
        self.min_tokens = min_tokens
        self.max_latency_ms = max_latency_ms
        self.engine = FusionEngine(rewind_enabled=enable_rewind, min_tokens=min_tokens)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Only compress POST to /chat/completions
        if scope["method"] != "POST" or not scope["path"].endswith("/chat/completions"):
            await self.app(scope, receive, send)
            return

        # Read body
        body = b""
        async def receive_wrapper():
            nonlocal body
            chunk = await receive()
            body = chunk["body"]
            return chunk

        try:
            import json
            data = json.loads(body)
            messages = data.get("messages", [])

            # Compress system, assistant, tool messages — skip user
            for msg in messages:
                role = msg.get("role", "")
                if role in ("system", "assistant", "tool"):
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        start = time.time()
                        try:
                            compressed = self.engine.compress(content)
                            elapsed = (time.time() - start) * 1000

                            # Gate on latency
                            if elapsed > self.max_latency_ms:
                                runs.add(1, {"outcome": "skipped_latency"})
                                continue

                            msg["content"] = compressed
                            runs.add(1, {"outcome": "compressed"})
                            duration_ms.record(elapsed)
                            # TODO: record token metrics when claw_compactor exposes them

                        except Exception:
                            failures.add(1, {"error": "compress"})

            # Write compressed body back
            data["messages"] = messages
            body = json.dumps(data).encode()

        except Exception:
            failures.add(1, {"error": "parse"})

        # Proxy original receive with modified body
        await self.app(scope, receive_wrapper, send)
```

### 3. Configure environment variables

```bash
# In docker-compose.yml or environment
CLAW_COMPACTOR_ENABLED=true
CLAW_COMPACTOR_REWIND=true
CLAW_COMPACTOR_MIN_TOKENS=500
CLAW_COMPACTOR_MAX_LATENCY_MS=100
CLAW_COMPACTOR_MODEL_LIMIT=200000
```

### 4. Build and deploy

```bash
docker build -t better-litellm:compactor .
docker tag better-litellm:compactor registry:5000/better-litellm:compactor
docker push registry:5000/better-litellm:compactor
```

### 5. Restart proxy

```bash
docker service update --image registry:5000/better-litellm:compactor litellm-proxy
```

## Verification

### 1. Check middleware loaded

```bash
# In proxy logs, look for:
# "ClawCompactorMiddleware registered"
# Or check:
curl http://localhost:4000/health | grep claw_compactor
```

### 2. Send test request

```bash
curl -X POST http://localhost:4000/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3.5-sonnet-20241022",
    "messages": [
      {"role": "system", "content": "A very long system prompt with lots of repetitive text that should be compressed..."},
      {"role": "user", "content": "Hello"}
    ]
  }'
```

### 3. Check OTEL metrics

```sql
-- In ClickHouse, verify claw_compactor metrics
SELECT
    sumIf(tokens_input, delta > 0) as total_input,
    sumIf(tokens_saved, delta > 0) as total_saved,
    round(total_saved / total_input * 100, 1) as ratio
FROM otel_metrics
WHERE metric_name IN ('claw_compactor.tokens_input', 'claw_compactor.tokens_saved')
  AND timestamp > now() - interval 1 hour;
```

### 4. Check dashboard

- `claw_compactor.runs` should show compressed > 0
- `claw_compactor.duration_ms` should show sub-100ms p99
- `claw_compactor.failures` should be 0 or very low

## Rollback

If compression causes issues:

1. **Disable via environment variable (no restart needed):**
   ```bash
   CLAW_COMPACTOR_ENABLED=false
   ```

2. **Full rollback — revert Docker image:**
   ```bash
   docker service update --image registry:5000/better-litellm:previous litellm-proxy
   ```
