---
type: adr
id: ADR-0005
title: "OpenAI cache token telemetry — root-cause fix in Usage class"
status: accepted
createdAt: "2026-06-27T20:30:00Z"
updatedAt: "2026-06-27T20:30:00Z"
tags: [telemetry, openai, cache, opentelemetry, usage]
supersedes: []
superseded_by: []
see_also:
  - "memories/0004-openai-cache-token-mapping-issue.memory.md"
  - "architectures/0001-cache-token-telemetry-flow.component.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0005: OpenAI cache token telemetry — root-cause fix in Usage class

## Context

OpenAI returns cache hit data in `prompt_tokens_details.cached_tokens` in API responses. LiteLLM's Usage class does NOT map this data to the `_cache_read_input_tokens` PrivateAttr, so the data is unavailable in `model_dump()` output that feeds into OTel semconv attribute emission.

**Evidence:**
- Clickhouse telemetry showed `cached_tokens=0` for all traces
- Native OpenAI API tests confirmed 99.2% cache hit rate
- LiteLLM proxy logs showed 56% cache hit rate (13,696 cached tokens)

## Decision

Fix in Usage class `__init__` — map OpenAI's `prompt_tokens_details.cached_tokens` to `_cache_read_input_tokens` PrivateAttr, and include PrivateAttrs in `model_dump()` output for telemetry contexts via a merge approach (not blanket PrivateAttr inclusion).

**Files modified:**
- `litellm/types/utils.py` — Usage class mapping for `cached_tokens` → `_cache_read_input_tokens`
- `litellm/litellm_core_utils/litellm_logging.py` — Merge PrivateAttrs into `model_dump()` output with proper key naming (no underscore prefix for semconv compatibility)

**Key detail — semconv key naming:** The `get_usage_as_dict()` method strips the underscore prefix from PrivateAttr keys (`_cache_read_input_tokens` → `cache_read_input_tokens`) to match OTel semantic convention attribute names (`gen_ai.usage.cache_read.input_tokens`).

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| Fix only in OTel integration | Minimal change, only affects OTel | Doesn't fix Langfuse/Prometheus; doesn't align with existing patterns; code duplication | Too narrow — doesn't address root cause or help other integrations |
| Combined approach (Usage + OTel fix) | Most comprehensive | More work, redundant code paths, potential for inconsistent behavior | Overkill — Usage fix addresses the root cause; OTel fix adds redundancy without value |

## Consequences

- **Positive:** Complete cache token telemetry — all integrations (OTel, Langfuse, Prometheus) can access OpenAI cache hit data consistently
- **Positive:** Consistent API — cache token handling works uniformly across providers
- **Positive:** Future-proof — new integrations automatically benefit
- **Negative:** More invasive change — required modifying both Usage class and model_dump() calls with comprehensive test coverage (10 new tests, 112 total passing, zero regressions)
