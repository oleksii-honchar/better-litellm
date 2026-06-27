---
type: memory
title: "OpenAI cached_tokens → _cache_read_input_tokens mapping issue"
createdAt: "2026-06-27T20:30:00Z"
updatedAt: "2026-06-27T20:30:00Z"
tags: [openai, cache, telemetry, usage, privateattr]
see_also:
  - "adrs/0005-openai-cache-token-telemetry-approach.adr.md"
  - "architectures/0001-cache-token-telemetry-flow.component.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: OpenAI cached_tokens → _cache_read_input_tokens mapping issue

## Fact

OpenAI's `prompt_tokens_details.cached_tokens` is NOT automatically mapped to LiteLLM's `Usage._cache_read_input_tokens` PrivateAttr. The mapping must be explicitly done in `Usage.__init__`, and PrivateAttrs must be manually merged into `model_dump()` output (they are excluded by default). Additionally, the OTel semconv integration expects the key WITHOUT the underscore prefix (`cache_read_input_tokens`, not `_cache_read_input_tokens`), requiring explicit key renaming in `get_usage_as_dict()`.

## Context

Discovered during the OpenAI cache token telemetry investigation (session 260625-1040-codex-litellm-codium-plugin). Clickhouse telemetry showed `cached_tokens=0` for all traces despite a 99.2% cache hit rate on native OpenAI API tests. The issue was a three-layer problem:
1. **Missing mapping:** `Usage.__init__` didn't extract `cached_tokens` from `prompt_tokens_details`
2. **PrivateAttr exclusion:** Pydantic's `model_dump()` excludes PrivateAttrs by default
3. **Key naming mismatch:** OTel semconv expects `cache_read_input_tokens` (no underscore) but PrivateAttr is `_cache_read_input_tokens`

The fix involved: (a) adding the mapping in `Usage.__init__`, (b) merging PrivateAttrs into the dict in `get_usage_as_dict()`, and (c) stripping the underscore prefix for semconv key naming.

## Impact

Without this fix, ALL integrations (OTel, Langfuse, Prometheus) silently drop OpenAI cache hit data. The fix benefits all integrations and prevents future cache telemetry gaps for new providers that follow the same pattern. The similar approach was previously used for Langfuse/Gemini (`test_gemini_cached_tokens.py`), confirming the pattern is correct.
