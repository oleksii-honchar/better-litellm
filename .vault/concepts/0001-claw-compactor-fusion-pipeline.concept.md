---
type: concept
title: "Claw Compactor — 14-Stage Fusion Pipeline"
createdAt: "2026-06-30T12:00:00Z"
updatedAt: "2026-06-30T12:00:00Z"
tags: [compression, claw-compactor, fusion-pipeline, reversible, deterministic]
see_also:
  - "adrs/0006-abandon-headroom-adopt-claw-compactor.adr.md"
  - "adrs/0007-claw-compactor-asgi-middleware.adr.md"
  - "memories/0005-headroom-integration-lessons.memory.md"
---

# Claw Compactor — 14-Stage Fusion Pipeline

Claw Compactor compresses LLM context through a deterministic, reversible, content-aware pipeline of 14 specialized compressors. The pipeline is content-type aware — each stage targets specific content types (code, prose, JSON, XML).

## Compression Pipeline

### Entry Gate
```
Input: "Compress this message" (1000 tokens)
→ Gate Check: 1000 >= 500? Yes → Enter pipeline
→ Gate Check: 300 >= 500? No → Skip compression
```

### 14-Stage Pipeline

| # | Stage | Purpose | Compression Rate |
|---|-------|---------|-----------------|
| 1 | **RewriteStage** | Remove filler words, redundancies, pleasantries | 10-20% |
| 2 | **CodeStage** | Compress code into semantic summaries | 70-80% |
| 3 | **DataStage** | Detect JSON/XML/CSV → structured compression | 50-80% |
| 4 | **FormatStage** | Normalize formatting, remove whitespace | 5-15% |
| 5 | **ProseStage** | Summarize prose while preserving key information | 30-50% |
 6 | **HybridStage** | Mixed content — combine strategies | 40-60% |
| 7 | **MathStage** | Preserve mathematical notation, compress explanations | 20-40% |
| 8 | **ListStage** | Compress lists, tables, structured text | 40-60% |
| 9 | **IntentStage** | Extract intent, remove elaboration | 50-70% |
| 10 | **RewindStage** | **Critical** — record original content for reversibility | 0% (metadata) |
| 11 | **FinalStage** | Final cleanup, token optimization | 5-10% |
| 12-14 | **Fallback stages** | Additional compression, error handling | varies |

## Rewind System

Reversible compression — original content can be restored on demand by LLM:

```python
from claw_compactor import FusionEngine

engine = FusionEngine(rewind_enabled=True, min_tokens=500)

# Compress
compressed = engine.compress("long message")
# Returns: compressed_text with embedded rewind IDs

# Restore original
original = engine.rewind(compressed)
# Returns: original_text
```

### Rewind Store Options

| Store | Use Case |
|-------|----------|
| **In-memory LRU** (default) | Single process, low overhead |
| **Redis** | Multi-process, shared state |
| **S3** | Persistence across restarts |

### Rewind Store Configuration

```python
# In-memory LRU (default)
RewindStore(
    max_memory_mb=100,
    ttl_seconds=3600,
    eviction_policy="LRU"
)

# Redis
RedisRewindStore(
    host="localhost",
    port=6379,
    ttl_seconds=7200
)

# S3
S3RewindStore(
    bucket="claw-rewind",
    region="us-east-1",
    ttl_seconds=86400
)
```

## Key Properties

- **Deterministic:** Same input → same output (no ML randomness)
- **Reversible:** Rewind system allows restoring original content
- **Content-aware:** Automatic detection of content type (code, prose, JSON, XML, CSV)
- **Zero ML dependencies:** Pure Python, no transformers/torch/onnxruntime required
- **Fast:** 1-10ms typical, 10-50ms worst case for complex content

## Content Type Examples

| Type | Input Tokens | Compressed Tokens | Rate |
|------|-------------|-------------------|------|
| Code (Python) | 8,472 | 1,861 | 78% |
| JSON data | 12,000 | 2,156 | 82% |
| Prose | 5,000 | 3,000 | 40% |
| Mixed | 2,000 | 1,200 | 40% |
| Code (Rust) | 4,560 | 1,531 | 66% |
| XML | 3,450 | 723 | 79% |
