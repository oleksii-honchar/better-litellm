---
type: adr
id: ADR-0002
title: "Use ONNX Runtime for Kompress ML compression inference"
status: accepted
createdAt: "2026-06-23T22:30:00Z"
updatedAt: "2026-06-23T22:30:00Z"
tags: [headroom, compression, ml, onnx]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0001-transformers-individual-deps.adr.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0002: Use ONNX Runtime for Kompress ML compression inference

## Context

Headroom's Kompress compressor supports two inference paths:
1. **ONNX Runtime** (lightweight, no torch) — ~30MB
2. **PyTorch** (full ML stack) — ~800MB+

The goal is to enable local ML compression in the BetterLiteLLM container with minimal overhead.

## Decision

**Use ONNX Runtime path** — includes only `onnxruntime>=1.16.0` and `transformers>=4.30.0,<6.0`, excluding PyTorch.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **ONNX Runtime (Selected)** | ~30MB, no PyTorch, Headroom's default | CPU only, no GPU acceleration | — |
| **PyTorch** | GPU acceleration, custom training | ~800MB+ container, slow startup | Overkill for compression |

## Consequences

- **Positive:** Minimal container overhead; ONNX INT8 model (261MB vs 601MB fp32) matches fp32 performance (F1 0.9130 vs 0.9128); faster startup and deployment
- **Negative:** No GPU acceleration (CPU only); not suitable for custom training or model updates
- **Neutral:** Model cached at `~/.cache/huggingface/hub/chopratejas/kompress-v2-base/` after first download
