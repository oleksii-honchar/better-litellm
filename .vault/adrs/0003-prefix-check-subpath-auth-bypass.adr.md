---
type: adr
id: ADR-0003
title: "Prefix check for subpath auth bypass (not registry integration)"
status: accepted
createdAt: "2026-06-25T18:15:00Z"
updatedAt: "2026-06-25T18:15:00Z"
tags: [auth, pass-through, subpath, codex]
supersedes: []
superseded_by: []
see_also:
  - "adrs/0004-path-normalization-consistency.adr.md"
  - "memories/0003-codex-litellm-subpath-auth-bypass-bug.memory.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# ADR-0003: Prefix check for subpath auth bypass (not registry integration)

## Context

The auth bypass check at `user_api_key_auth.py:575` uses exact path comparison that doesn't understand `include_subpath: true`. This causes the bypass to fail for subpath routes like `/codex/v1/responses` when the configured path is `/codex/v1`:

```python
# BEFORE — exact match only
if isinstance(endpoint, dict) and endpoint.get("path", "") == route:
```

With `path: "/codex/v1"` and a request to `/codex/v1/responses`, the exact comparison fails → auth bypass not triggered → JWT rejected (401).

## Decision

Implement a prefix check directly in the auth bypass function, using `startswith(endpoint_path + "/")` to match subpath routes when `include_subpath: true` is configured:

```python
# AFTER — subpath-aware
endpoint_path = endpoint.get("path", "")
path_matches = (
    endpoint_path == route or
    (endpoint.get("include_subpath", False) and
     route.startswith(endpoint_path + "/"))
)
if isinstance(endpoint, dict) and path_matches:
```

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|-------------|
| **Prefix check (Selected)** | Minimal change, no new deps, backward compatible | Slight code duplication with registry | — |
| **Use existing registry method** | Reuses tested logic, single source of truth | Circular imports risk; registry may not be populated at auth bypass time | Timing issues on startup |
| **New registry query method** | Explicit intent, reusable | More invasive, new API surface | Over-engineered for single-point fix |

## Consequences

- **Positive:** Subpath routes correctly trigger auth bypass; minimal code change; backward compatible; no new dependencies
- **Negative:** Slight code duplication with registry subpath matching logic; two code paths for subpath comparison
