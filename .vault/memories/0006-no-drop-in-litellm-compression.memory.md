---
type: memory
title: "No drop-in context compression solutions for LiteLLM proxy"
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-06-30T12:00:00Z"
tags: [litellm, compression, research, drop-in, middleware]
see_also:
  - "adrs/0006-abandon-headroom-adopt-claw-compactor.adr.md"
  - "memories/0005-headroom-integration-lessons.memory.md"
---

## Fact

No drop-in context compression solutions exist for LiteLLM proxy. All alternatives require custom ASGI middleware integration.

## Context

### Solutions Evaluated

- **Headroom:** Requires custom ASGI middleware (not purpose-built for LiteLLM)
- **Claw Compactor:** Requires custom ASGI middleware (not purpose-built for LiteLLM)
- **LLMLingua-2:** Requires custom ASGI middleware (not purpose-built for LiteLLM)
- **LangChain ContextCompression:** Requires custom ASGI middleware (not purpose-built for LiteLLM)
- **LlamaIndex Postprocessor:** Requires custom ASGI middleware (not purpose-built for LiteLLM)
- **Trimwire:** Claude-focused, Rust compilation, requires custom integration
- **LongRun Kompress:** Research project, 7% compression, complex ML setup

### Root Cause

Context compression operates at the message level — intercepting requests before they reach the LLM provider. LiteLLM proxy lacks native hooks for request interception (callback hooks fail silently, as confirmed with headroom).

### Implications

- All compression solutions require ASGI middleware layer in better-litellm fork
- No vendor-agnostic solutions — each engine requires custom integration
- Middleware ordering is critical (must be before RequestSizeLimitMiddleware)
