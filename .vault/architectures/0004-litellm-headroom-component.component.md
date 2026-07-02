---
type: architecture
c4_level: 2
c4_type: component
title: "LiteLLM Proxy + Headroom — Component Map"
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-06-30T12:00:00Z"
tags: [architecture, C4, component, litellm, headroom, middleware]
see_also:
  - "architectures/0001-litellm-proxy-component.component.md"
  - "architectures/0002-litellm-headroom-integration.container.md"
  - "architectures/0003-litellm-proxy-code.code.md"
---

# LiteLLM Proxy + Headroom — Component Map

## Description

Component-level view inside the LiteLLM proxy container showing how headroom ASGI middleware integrates with LiteLLM's request handling pipeline. Focus on the middleware chain, request flow, and compression integration.

## Diagram

```mermaid
C4Component
    title LiteLLM Proxy + Headroom — Component Map

    ContainerB(litellm_proxy, "better-litellm Proxy", "Python/FastAPI")

    Component(asgi_chain, "ASGI Middleware Chain", "Starlette\nMiddleware stack\nExecutes in reverse registration order", "Reverse order: last registered = first executed")
    Component(request_size, "RequestSizeLimitMiddleware", "Starlette\nSize limit check", "Limits request body size")
    Component(headroom_mw, "HeadroomCompressionMiddleware", "Starlette\nCompresses messages in POST /chat/completions", "Intercepts and compresses assistant/system/tool messages")
    Component(proxy_handler, "ProxyLLMHTTPHandler", "FastAPI\nChatCompletionsAPI\nRoute: POST /chat/completions", "Routes to LLM providers, handles auth")
    Component(model_router, "Model Router", "LiteLLM\nModel selection and routing", "Selects provider based on model name")
    Component(provider_router, "Provider Router", "LiteLLM\nHTTP client to provider", "Sends request to OpenAI/Anthropic/etc.")
    Component(session_manager, "Session Manager", "LiteLLM\nSession state, caching", "Manages Redis sessions, rate limits")

    ComponentB(headroom_sdk, "Headroom SDK", "Python")

    Component(compression_middleware, "CompressionMiddleware", "Python\n287 lines\nasgi.py", "ASGI middleware — intercepts request body, calls pipeline")
    Component(tokenizer_router, "TokenizerRouter", "Python\nregistry.py\nMODEL_PATTERNS", "Maps model names to tiktoken encodings")
    Component(compression_pipeline, "CompressionPipeline", "Python\n1304 lines\npipeline.py", "Core compression pipeline — orchestrates 14-stage compression")
    Component(kompress_compressor, "KompressCompressor", "Python\n1424 lines\nkompress_compressor.py", "14-stage ML-based compression pipeline")

    Rel(asgi_chain, headroom_mw, "Executes first\n(reverse order)", "ASGI")
    Rel(asgi_chain, request_size, "Executes second", "ASGI")
    Rel(headroom_mw, proxy_handler, "Modified request", "ASGI")
    Rel(proxy_handler, model_router, "Route request", "in-process")
    Rel(model_router, provider_router, "Selected provider", "in-process")
    Rel(model_router, session_manager, "Session check", "in-process")
    Rel(headroom_mw, compression_middleware, "create_compress_middleware()", "import")
    Rel(compression_middleware, compression_pipeline, "compress()", "in-process")
    Rel(compression_pipeline, tokenizer_router, "encoding_for_model()", "in-process")
    Rel(compression_pipeline, kompress_compressor, "compress()", "in-process")
```

## Elements

| Element | Type | Description |
|---------|------|-------------|
| ASGI Middleware Chain | Component | Starlette middleware stack — executes in reverse registration order |
| RequestSizeLimitMiddleware | Component | Limits request body size — executes AFTER headroom (reverse order) |
| HeadroomCompressionMiddleware | Component | Compresses messages in POST /chat/completions — executes BEFORE RequestSizeLimitMiddleware |
| ProxyLLMHTTPHandler | Component | FastAPI handler for chat completions route |
| Model Router | Component | Selects provider based on model name |
| Provider Router | Component | HTTP client to LLM providers |
| Session Manager | Component | Redis sessions, rate limiting |
| CompressionMiddleware | Component | 287 lines — ASGI middleware, intercepts request body |
| TokenizerRouter | Component | MODEL_PATTERNS regex — maps model names to tiktoken encodings |
| CompressionPipeline | Component | 1304 lines — orchestrates 14-stage compression |
| KompressCompressor | Component | 1424 lines — 14-stage ML-based compression |

## Key Relationships

1. **Reverse ASGI order** — `HeadroomCompressionMiddleware` executes BEFORE `RequestSizeLimitMiddleware` (middleware registered after size limit)
2. **In-process compression** — `CompressionMiddleware` calls `CompressionPipeline` directly (no network)
3. **Tiktoken mapping** — `TokenizerRouter` uses `MODEL_PATTERNS` regex to find tiktoken encodings
4. **14-stage pipeline** — `KompressCompressor` runs through 14 compression stages
5. **No compression for user messages** — pipeline only processes assistant/system/tool messages

## Notes

- Middleware registered at ~line 15940 in `proxy_server.py`
- ASGI reverse order: last registered = first executed
- `RequestSizeLimitMiddleware` checks size AFTER compression (beneficial — compressed bodies smaller)
- Tiktoken encoding mismatch: gpt-5.x models not recognized → `cl100k_base` fallback → zero compression
