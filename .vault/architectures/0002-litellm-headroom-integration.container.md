---
type: architecture
c4_level: 1
c4_type: container
title: "LiteLLM Proxy + Headroom — Integration Container Map"
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-06-30T12:00:00Z"
tags: [architecture, C4, container, litellm, headroom, middleware]
see_also:
  - "architectures/0001-litellm-proxy-component.component.md"
  - "architectures/0003-litellm-proxy-code.code.md"
  - "memories/0004-litellm-proxy-cors-workaround.memory.md"
  - "memories/0003-litellm-proxy-health-endpoints.memory.md"
---

# LiteLLM Proxy + Headroom — Integration Container Map

## Description

Container-level view of better-litellm proxy with headroom compression middleware deployed on puma.lan. The middleware intercepts requests before they reach LiteLLM, compressing messages through the headroom pipeline.

## Diagram

```mermaid
C4Container
    title LiteLLM Proxy + Headroom — Container Map

    Person(user, "End User", "ChatGPT user making API requests")
    Person(admin, "Admin", "Manages proxy, views dashboard")

    System_Ext(chatgpt, "ChatGPT", "gpt-5.5, gpt-5.4-mini, codex-auto-review — Tiktoken does NOT recognize these models")
    System_Ext(claude, "Claude API", "claude-3.5-sonnet — Tiktoken recognizes this model")
    System_Ext(clickhouse, "ClickHouse + Grafana", "OTEL metrics storage and visualization")

    Boundary(litellm_boundary, "better-litellm (puma.lan:4000)") {
        Container(middleware, "Headroom ASGI Middleware", "Python/Starlette\nCompressionMiddleware\nRegistered at ~line 15940", "Compresses assistant/system/tool messages in POST /chat/completions")
        Container(proxy, "LiteLLM Proxy", "Python/FastAPI\nChatCompletionsAPI\nProxyLLMHTTPHandler", "Routes requests to LLM providers, handles authentication")
        ContainerDb(redis, "Redis", "Cache/Queue\nSession data, rate limiting")
    }

    Boundary(headroom_boundary, "headroom (SDK)") {
        Container(compressor, "Compression Engine", "Python\nPipeline + KompressCompressor\n14-stage compression", "Multi-strategy compression pipeline")
    }

    Rel(user, middleware, "POST /chat/completions", "HTTP")
    Rel(middleware, compressor, "compress()", "in-process")
    Rel(middleware, proxy, "Modified request", "ASGI")
    Rel(proxy, chatgpt, "Forward request", "HTTP")
    Rel(proxy, claude, "Forward request", "HTTP")
    Rel(proxy, clickhouse, "OTEL metrics", "gRPC")
    Rel(proxy, redis, "Cache/Queue", "TCP")
    Rel(admin, clickhouse, "View dashboard", "HTTP")
```

## Elements

| Element | Type | Technology | Description |
|---------|------|-----------|-------------|
| End User | Person | — | ChatGPT user making API requests |
| Admin | Person | — | Manages proxy, views Grafana dashboard |
| ChatGPT | System_Ext | — | gpt-5.5, gpt-5.4-mini, codex-auto-review — **Tiktoken does NOT recognize these** |
| Claude API | System_Ext | — | claude-3.5-sonnet — Tiktoken recognizes this model |
| ClickHouse + Grafana | System_Ext | — | OTEL metrics storage and Grafana visualization |
| Headroom ASGI Middleware | Container | Python/Starlette | CompressionMiddleware registered at ~line 15940 |
| LiteLLM Proxy | Container | Python/FastAPI | Routes requests to LLM providers, handles authentication |
| Redis | ContainerDb | — | Cache, session data, rate limiting |
| Compression Engine | Container | Python | Multi-strategy compression pipeline |

## Key Relationships

1. **ASGI middleware executes BEFORE LiteLLM proxy** — requests intercepted at middleware layer
2. **Compression is in-process** — middleware calls headroom pipeline directly (no network hop)
3. **Only assistant/system/tool messages are compressed** — user messages skipped by design
4. **Tiktoken encoding mismatch** — gpt-5.x models produce zero compression tokens
5. **OTEL metrics flow through ClickHouse** — DELTA temporality, requires `sumIf(delta > 0)` queries

## Notes

- Middleware registered at approximately line 15940 in `proxy_server.py`
- Executes in ASGI reverse order — before `RequestSizeLimitMiddleware`
- Tiktoken encoding mismatch affects ChatGPT models (gpt-5.x) — zero compression tokens recorded
- OTEL metrics use DELTA temporality — ClickHouse converts to cumulative
