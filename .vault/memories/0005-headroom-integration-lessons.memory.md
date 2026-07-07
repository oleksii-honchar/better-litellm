---
type: memory
title: "Headroom ASGI integration deployed to puma.lan — lessons learned"
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-07-07T00:00:00Z"
tags: [litellm, headroom, asgi, middleware, deployment, puma]
see_also:
  - "adrs/0006-abandon-headroom-adopt-claw-compactor.adr.md"
  - "memories/0006-no-drop-in-litellm-compression.memory.md"
deprecated:
  date: "2026-07-07"
  reason: "Headroom integration removed per ADR-0006"
  superseded_by: "adrs/0006-abandon-headroom-adopt-claw-compactor.adr.md"
---

> **⚠️ DEPRECATED** — Headroom integration was removed per ADR-0006. This memory is preserved for historical reference only.

## Fact

Headroom compression was successfully deployed as ASGI middleware in better-litellm on puma.lan. Achieved 99.3% compression ratio on assistant log messages. However, multiple issues emerged in production.

## Context

### Integration

- Registered as ASGI middleware in `proxy_server.py` at ~line 15940
- Executed before `RequestSizeLimitMiddleware` (ASGI reverse order)
- 1.8M requests/30 days, 117M tokens/30 days

### What Worked

- ASGI middleware pattern reliable — no silent failures
- Compression pipeline executed correctly for recognized models (claude-3.5-sonnet, gpt-4o)
- 99.3% compression on assistant log messages (254M → 1.8M tokens compressed)

### What Broke

**1. Tiktoken encoding mismatch — zero compression for ChatGPT models:**
- `gpt-5.5`, `gpt-5.4-mini`, `codex-auto-review`: Tiktoken falls back to `cl100k_base`
- Pipeline ran 297 times for gpt-5.5 — ZERO input tokens recorded, ZERO duration
- Two metrics recording paths: pipeline + adapter; adapter's `_count_tokens` returns 0 for unrecognized models

**2. OTEL metrics discrepancies:**
- Headroom sends DELTA temporality; ClickHouse OTel receiver converts to cumulative
- Dashboard using `max(Value)` produced 10.4% ratio vs actual 14.2%
- Fix: per-series `sumIf(delta > 0)` delta computation

**3. Dashboard bugs:**
- Avg Ratio panel: `max()` on cumulative counters across restart boundaries
- Per-model breakdown: filtered models with `saved = 0` instead of `input > 0`

**4. Only compresses assistant/system messages:**
- User messages intentionally skipped
- First-turn conversations produce zero compression (by design)

### Impact

- ML dependencies (~320MB container increase)
- Tiktoken encoding issues with ChatGPT models
- OTEL metrics misconfiguration
- Only compresses assistant/system messages (user messages skipped by design)

## Action Items (if migrating to Claw Compactor)

- [x] Adopt Claw Compactor instead of headroom
- [x] Design ASGI middleware integration
- [x] Plan dashboard with correct OTEL query patterns
