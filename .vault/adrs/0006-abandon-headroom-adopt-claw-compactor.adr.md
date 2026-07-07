---
type: adr
id: ADR-0006
title: "Abandon headroom compression, adopt Claw Compactor"
status: implemented
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-07-07T00:00:00Z"
tags: [compression, headroom, claw-compactor, migration, strategic]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0007-claw-compactor-asgi-middleware.adr.md"
  - "concepts/0001-claw-compactor-fusion-pipeline.concept.md"
  - "memories/0005-headroom-integration-lessons.memory.md"
  - "memories/0006-no-drop-in-litellm-compression.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0006: Abandon headroom compression, adopt Claw Compactor

## Context

Headroom compression was integrated via ASGI middleware in better-litellm (deployed on puma.lan). Despite successful deployment with 99.3% compression on assistant log messages, multiple critical issues emerged:

**1. Tiktoken encoding mismatch — zero compression for ChatGPT models:**
Tiktoken does NOT recognize `gpt-5.5`, `gpt-5.4-mini`, `codex-auto-review`. It falls back to `cl100k_base` encoding. The pipeline ran 297 times for gpt-5.5 but recorded ZERO input tokens and ZERO duration. Two metrics recording paths exist (pipeline + adapter), and the adapter's `_count_tokens` returns 0 for unrecognized models.

**2. OTEL metrics discrepancies:**
Headroom sends DELTA temporality, but ClickHouse OTel receiver converts to cumulative. Dashboard queries using `max(Value)` produced 10.4% ratio vs actual 14.2% (should use `sumIf(delta > 0)` per-series delta computation).

**3. Dashboard bugs:**
Avg Ratio panel showed 10.4% (wrong — `max()` on cumulative counters across restart boundaries). Per-model breakdown filtered models with `saved = 0` instead of `input > 0`.

**4. Only compresses assistant/system messages:**
User messages intentionally skipped — first-turn conversations produce zero compression. This is by design but limits real-world effectiveness.

**5. ML model dependencies:**
Requires `transformers` and `onnxruntime` packages (~320MB container increase including 261MB ONNX model cached from HuggingFace). Silent failures when dependencies missing.

**Research finding:** No drop-in context compression solutions exist for LiteLLM proxy. All alternatives require custom ASGI middleware integration.

## Decision

**Abandon headroom. Adopt Claw Compactor** (https://github.com/open-compress/claw-compactor) as the new compression engine.

**Claw Compactor advantages:**
- **Zero ML dependencies** — no transformers, torch, or ONNX runtime required
- **1,600+ tests** — comprehensive test coverage
- **15-82% compression** — content-type dependent (code: 78%, JSON: 82%, text: 15-40%)
- **Reversible compression** — Rewind system allows LLM to retrieve original content
- **14-stage Fusion Pipeline** — deterministic, content-aware
- **MIT license**

**Alternatives considered and rejected:**

| Alternative | Rationale |
|-------------|-----------|
| Trimwire | Claude-focused, Rust compilation required, smaller community |
| LLMLingua-2 | Heavy ML dependencies (torch, transformers), ~300ms latency per request |
| Caveman-UTC | Niche M2M communication only, symbolic encoding, minimal community |
| LongRun Kompress | Research project, only 7% compression rate, complex ML setup |
| Custom middleware | Lower compression rates (10-30%), ongoing maintenance burden |

## Consequences

- **Positive:** Zero ML dependencies eliminates tiktoken encoding mismatches and silent failures; comprehensive test coverage; reversible compression; no HuggingFace dependency
- **Positive:** No tiktoken encoding issues — uses own heuristic token estimation with optional tiktoken fallback
- **Negative:** 1-2 weeks development for custom ASGI middleware (Claw Compactor not purpose-built for LiteLLM)
- **Negative:** 12,000+ lines of code — fairly complex codebase to understand
- **Neutral:** No existing LiteLLM examples to reference; must build integration from scratch

## Implementation Note

**Implementation completed: 2026-07-07.** Headroom integration code removed from the fork on branch `fix/remove-headroom`. All headroom-related dependencies, middleware, callback adapters, and configuration have been stripped. Architecture and memory vault nodes archived/deprecated accordingly.
