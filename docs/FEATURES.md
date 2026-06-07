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

## 2. JSON in `<tool_call>` Wrapper Tag Extraction

**Status:** ✅ Implemented — 2026-06-05

**File:** `litellm/llms/openai/chat/gpt_transformation.py`

### Problem

The original 5-format cascade in `_check_and_fix_if_content_is_tool_call()` handled:
- Qwen XML in `...` tags
- JSON in `...` tags
- Qwen XML in `<tool_call>` tags
- Qwen XML in CDATA
- Pure JSON

But it missed one format: **JSON inside `<tool_call>` wrapper tags**. When the model outputs:

```
<tool_call>{"type": "bash", "command": "ls"}_</tool_call>
```

This format appeared when:
1. The model's chat template includes `<tool_call>` wrapper tags
2. The model outputs the tool call as JSON inside those tags (not Qwen XML)
3. The PEG parser in llama.cpp rejects it (expects Qwen XML inside `<tool_call>`)
4. The resulting 400 error goes through `_extract_tool_calls_from_llamacpp_error()`, which also missed this format
5. The LLM sees failure, thinks it output invalid text, and repeats the tool call — causing the "think → invalid tool call" repeat loop

### Root Cause

The `<tool_call>` extraction only looked for `<function=...>` XML content inside the wrapper tags — not plain JSON. The JSON-in-`...` extraction looked for `...` tags, not `<tool_call>` tags. The format fell through both gaps and was never recovered.

### Solution

Add two new static methods and a new extraction step to the cascade:

1. **`_extract_json_from_tool_call_wrapper_tags(text)`** — Extracts JSON from `<tool_call>...\n</tool_call>` wrapper
2. **`_parse_opencode_json_to_tool_call(json_content)`** — Handles both opencode format (`"type":"bash"` key) and OpenAI format (`"name":"bash","arguments":{...}`)

Applied to all three code paths:
| Path | File | Method |
|------|------|--------|
| Normal (non-streaming) | `gpt_transformation.py` | `_check_and_fix_if_content_is_tool_call()` — new step 5 |
| Error recovery (non-streaming) | `gpt_transformation.py` | `_extract_tool_calls_from_llamacpp_error()` — new extraction case |
| Streaming buffer | `gpt_transformation.py` | `_extract_tool_calls_from_buffer()` — new extraction case |

### Design Decisions

- **Two key formats handled:** opencode uses `"type"` for tool name; OpenAI uses `"name"` + `"arguments"`. The parser accepts both.
- **Strict-first JSON:** Only the JSON-in-`<tool_call>` wrapper is matched — existing XML and CDATA paths are unaffected.
- **All three paths:** The fix is applied to normal content, error-recovery, and streaming buffer to prevent gaps.
- **No validation against tool names:** Unlike `_check_and_fix_if_content_is_tool_call()`, the error recovery and streaming paths don't validate against declared tools — they extract whatever JSON they find.

### Impact

- Eliminates the "think → invalid tool call" repeat loop for models that output JSON in `<tool_call>` tags
- Zero impact on other formats (Qwen XML, CDATA, pure JSON still work)
- No configuration required

---

## 3. Streaming Tool Call Tag Stripping (resolved)

The `_check_and_fix_if_content_is_tool_call()` fix covered non-streaming responses. The streaming `chunk_parser()` was later updated with buffer-based tool call extraction (`_extract_tool_calls_from_buffer()`) that handles all formats including JSON-in-`<tool_call>`. No further action needed.

---

## Planned Features

### 1. Upstream Health Check (deferred)

Add a pre-flight check against the llama-swap endpoint (`/v1/models` or `/health`) before the proxy starts. This prevents the proxy from accepting requests when mammoth is down, and gives a clear error instead of connection timeouts.

### 4. Custom Model Routing (deferred)

Support request-header-based model switching, so the same proxy endpoint can route to different llama-swap models based on a custom header (e.g., `X-Model-Override: qwopus3.6-27b-precise`). Useful for agents that need different model presets per task.
