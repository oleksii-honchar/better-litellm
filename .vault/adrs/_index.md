---
type: index
title: "ADRs"
createdAt: "2026-06-23T22:30:00Z"
updatedAt: "2026-06-27T20:30:00Z"
tags: []
---

# ADRs

Architecture Decision Records for the BetterLiteLLM project.

## Nodes

- [[0001-transformers-individual-deps.adr]] — Install transformers via individual dependencies rather than PyPI extras
- [[0002-onnx-kompress-inference.adr]] — Use ONNX Runtime (not PyTorch) for Kompress ML compression inference
- [[0003-prefix-check-subpath-auth-bypass.adr]] — Prefix check for subpath auth bypass (not registry integration)
- [[0004-path-normalization-consistency.adr]] — Apply path normalization in auth bypass for consistency
- [[0005-openai-cache-token-telemetry-approach.adr]] — OpenAI cache token telemetry — root-cause fix in Usage class
