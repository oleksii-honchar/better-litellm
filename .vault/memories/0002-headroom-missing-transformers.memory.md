---
type: memory
title: "headroom-ai core package does NOT include transformers; ML compression fails silently"
createdAt: "2026-06-23T22:30:00Z"
updatedAt: "2026-06-23T22:30:00Z"
tags: [headroom, gotcha, compression, ml]
see_also:
  - "adrs/0001-transformers-individual-deps.adr.md"
  - "memories/0001-litellm-callback-class-not-instance.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: headroom-ai core package does NOT include transformers; ML compression fails silently

## Fact

The `headroom-ai` core package does NOT include the `transformers` or `onnxruntime` dependencies. They are opt-in extras (`[ml]` or `[proxy]`). Without them, all ML compression (Kompress) silently fails and returns the original messages.

## Context

After fixing the callback instantiation bug (see memory 0001), compression metrics still didn't appear. Container logs revealed:

```
Compression failed, returning original messages: No module named 'transformers'
```

The failure chain: `async_pre_call_hook` → `headroom.compress()` → `TransformPipeline` → `ContentRouter` → `_try_ml_compressor()` → `_get_kompress()` → `is_kompress_available()` → `import transformers` → `ImportError`.

The error is caught gracefully at `headroom/compress.py:336-349`, returning original messages with a warning — no exception, no metric recorded for the failure.

The `headroom-ai[ml]` extra includes torch+transformers+onnxruntime; `headroom-ai[proxy]` includes onnxruntime+transformers (without torch). The decision (ADR-0001) was to install the two packages individually rather than use either extra.

## Impact

- If you install `headroom-ai` without `transformers` and `onnxruntime`, ML compression is completely non-functional
- The failure is silent — no exception, no crash; just a warning log
- Compression metrics (`headroom.compression.*`) never appear in ClickHouse
- To verify: `from headroom.transforms.kompress_compressor import is_kompress_available; print(is_kompress_available())`
