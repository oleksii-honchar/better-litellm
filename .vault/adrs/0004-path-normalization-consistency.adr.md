---
type: adr
id: ADR-0004
title: "Path normalization consistency in auth bypass"
status: accepted
createdAt: "2026-06-25T18:15:00Z"
updatedAt: "2026-06-25T18:15:00Z"
tags: [auth, pass-through, normalization]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0003-prefix-check-subpath-auth-bypass.adr.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0004: Path normalization consistency in auth bypass

## Context

The auth bypass function already uses `normalize_route_for_root_path()` at line 564 for upstream checks. The same normalization should be applied to the endpoint path before comparison — preventing edge cases where endpoint paths are stored with different prefixes (e.g., leading/trailing slash variations).

## Decision

Apply `normalize_route_for_root_path()` to the endpoint path before comparison in the subpath-aware auth bypass check:

```python
normalized_endpoint_path = normalize_route_for_root_path(endpoint_path) or endpoint_path
```

This ensures the normalized path is used for both exact-match and subpath (`startswith`) comparisons.

## Consequences

- **Positive:** Prevents edge cases where endpoint paths are stored with different prefixes; consistent with existing auth bypass logic
- **Negative:** Additional function call per endpoint comparison (negligible O(1) cost)
