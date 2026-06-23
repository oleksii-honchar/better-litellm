---
type: memory
title: "LiteLLM proxy callback resolution returns CLASS, not instance"
createdAt: "2026-06-23T22:30:00Z"
updatedAt: "2026-06-23T22:30:00Z"
tags: [litellm, callback, gotcha, headroom]
see_also:
  - "adrs/0001-transformers-individual-deps.adr.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: LiteLLM proxy callback resolution returns CLASS, not instance

## Fact

LiteLLM's `get_instance_fn` in `litellm/proxy/types_utils/utils.py` (line 149) returns the callback CLASS, not an instantiated object. This means `__init__` is never called and any initialization logic (like `configure_otel_metrics()`) never runs.

## Context

During Headroom-LiteLLM integration (June 2026), compression metrics were not flowing despite the OTEL pipeline being connected. Container logs showed:

```
TypeError: CustomLogger.async_post_call_success_hook() missing 1 required positional argument: 'self'
```

The proxy was calling hooks on the CLASS (not instance), so `self` received `user_api_key_dict` instead. Root cause: `get_instance_fn` returned `HeadroomCallbackAdapter` (the class) instead of `HeadroomCallbackAdapter()` (an instance).

Fix: One-line change at `utils.py:149`:
```python
# BEFORE: return HeadroomCallbackAdapter
# AFTER:  return HeadroomCallbackAdapter()
```

## Impact

- `__init__` never called → OTEL metrics never initialized → no compression metrics recorded
- Hook parameters misaligned (method signatures broken)
- This is a general LiteLLM behavior — any custom callback that relies on `__init__` for setup will fail silently with the same pattern
