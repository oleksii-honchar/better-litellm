---
type: memory
title: "Subpath auth bypass 401 — exact path comparison in pass-through endpoints"
createdAt: "2026-06-25T18:15:00Z"
updatedAt: "2026-06-25T18:15:00Z"
tags: [litellm, auth, pass-through, gotcha, codex]
see_also:
  - "adrs/0003-prefix-check-subpath-auth-bypass.adr.md"
  - "adrs/0004-path-normalization-consistency.adr.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: Subpath auth bypass 401 — exact path comparison in pass-through endpoints

## Fact

Configuring a LiteLLM pass-through endpoint with `include_subpath: true` and `auth: false` results in a **401 Unauthorized** error — even though the pass-through handler correctly matches subpath routes. The auth bypass check at `user_api_key_auth.py:575` uses exact string comparison, so it never fires for subpaths.

## Context

Two sequential bugs discovered when routing Codex through LiteLLM:

### Bug 1 (404): Malformed FastAPI route from wildcard in path

Using `path: "/codex/v1/*"` creates a malformed FastAPI route `/codex/v1/*/{subpath:path}` (literal asterisk `*`, not a glob).

**Fix:** Remove `*` — use `path: "/codex/v1"`.

### Bug 2 (401): Auth bypass exact-path mismatch

The auth bypass at `user_api_key_auth.py:575` does:

```python
if isinstance(endpoint, dict) and endpoint.get("path", "") == route:
```

With `path: "/codex/v1"` and request to `/codex/v1/responses`:
- Exact match fails → auth bypass NOT triggered
- Falls through to normal key validation → JWT `eyJh...` rejected ("LiteLLM Virtual Key expected")

The `_registered_pass_through_routes` registry already supports subpath matching, but the auth bypass function does its own naive comparison against raw config dicts.

**Fix:** ADR-0003 + ADR-0004 — subpath-aware prefix check with `startswith(endpoint_path + "/")` and path normalization.

## Impact

- Any future `include_subpath: true` + `auth: false` pass-through endpoint will hit the same 401 if this fix is ever reverted
- Workaround (without code change): register each specific route individually — brittle, not recommended
