# better-litellm Features

This document describes the features and patches added by the `better-litellm` fork.

For an overview of the fork's purpose and installation, see [BETTER-LITELLM.md](./BETTER-LITELLM.md).

---

## 1. Tool Call Wrapper Tag Extraction

**Status:** ⏳ Planned — first feature

**File:** `litellm/llms/openai/chat/gpt_transformation.py`

### Problem

When models served through llama-swap (llama.cpp) return tool calls, they often wrap the JSON in `...` tags:

```
...{"type": "function", "name": "bash", "arguments": "{\"command\": \"ls\"}"}...
```

LiteLLM's `_check_and_fix_if_content_is_tool_call()` method (line 494 in `gpt_transformation.py`) attempts to parse the content directly with `json.loads(content)`. When the content includes the `...` wrapper tags, parsing fails, and the method returns `None`. The agent then treats the response as plain text instead of a tool call — the tool is never executed.

### Root Cause

The `...` tags are a llama.cpp convention for marking code blocks. They are not stripped before JSON parsing:

```python
def _check_and_fix_if_content_is_tool_call(
    self, content: str, optional_params: dict
) -> Optional[ChatCompletionMessageToolCall]:
    import json

    if not self._passed_in_tools(optional_params):
        return None
    tool_call_names = get_tool_call_names(optional_params.get("tools", []))
    try:
        json_content = json.loads(content)  # ← FAILS when content has ... tags
        if (
            json_content.get("type") == "function"
            and json_content.get("name") in tool_call_names
        ):
            return ChatCompletionMessageToolCall(...)
    except Exception:
        return None
    return None
```

### Solution

Strip `...` wrapper tags before calling `json.loads()`:

```python
def _check_and_fix_if_content_is_tool_call(
    self, content: str, optional_params: dict
) -> Optional[ChatCompletionMessageToolCall]:
    import json
    import re

    if not self._passed_in_tools(optional_params):
        return None
    tool_call_names = get_tool_call_names(optional_params.get("tools", []))

    # Strip ... wrapper tags (llama.cpp convention)
    stripped = content.strip()
    if stripped.startswith("...") and stripped.endswith("..."):
        stripped = stripped[3:-3].strip()

    try:
        json_content = json.loads(stripped)  # ← USES stripped content
        if (
            json_content.get("type") == "function"
            and json_content.get("name") in tool_call_names
        ):
            return ChatCompletionMessageToolCall(
                function=Function(
                    name=json_content.get("name"),
                    arguments=json_content.get("arguments"),
                )
            )
    except Exception:
        return None

    return None
```

### Design Decisions

- **Non-breaking:** When no `...` tags are present, `stripped` equals the original content. Cloud models and other providers are unaffected.
- **Minimal regex:** Uses string operations (`startswith`/`endswith`/slicing) instead of `re.sub()` for performance — this runs on every assistant message.
- **Single pass:** Only strips one layer of `...` tags. Nested `...` are not expected in tool call content and would be a sign of a deeper model issue.
- **No changes to other parsers:** This fix targets only `_check_and_fix_if_content_is_tool_call()`. The streaming path and other JSON extraction points may need similar treatment but are deferred until needed.

### Impact

- Tool calls from llama.cpp models served via llama-swap are now correctly parsed and executed by agents.
- Zero impact on cloud provider responses (no `...` tags in their output).
- No configuration required — the fix is transparent.

### Testing

The patch should be verified with:
1. A llama.cpp model that returns tool calls wrapped in `...` tags
2. A cloud model that returns tool calls without `...` tags (regression check)
3. Edge case: content that starts with `...` but does not end with `...` (should not be stripped)
4. Edge case: empty content after stripping

---

## Planned Features

### 2. Streaming Tool Call Tag Stripping (deferred)

The `_check_and_fix_if_content_is_tool_call()` fix covers non-streaming responses. When streaming, the chunk assembler builds the full content before this method is called, so it may work. However, if the streaming path has its own tool call detection, similar `...` stripping may be needed there. Defer until a real issue is observed.

### 3. Upstream Health Check (deferred)

Add a pre-flight check against the llama-swap endpoint (`/v1/models` or `/health`) before the proxy starts. This prevents the proxy from accepting requests when mammoth is down, and gives a clear error instead of connection timeouts.

### 4. Custom Model Routing (deferred)

Support request-header-based model switching, so the same proxy endpoint can route to different llama-swap models based on a custom header (e.g., `X-Model-Override: qwopus3.6-27b-precise`). Useful for agents that need different model presets per task.
