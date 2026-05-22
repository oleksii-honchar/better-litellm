# 01 — Tool Call Wrapper Tag Extraction

**Date:** 2026-05-22

---

## Description

Strip `...` wrapper tags from content before `json.loads()` in `_check_and_fix_if_content_is_tool_call()`, so tool calls from llama.cpp models are parsed correctly.

---

## Problem

When models served through llama-swap (llama.cpp) return tool calls, they often wrap the JSON in `...` tags:

```
...{"type": "function", "name": "bash", "arguments": "{\"command\": \"ls\"}"}...
```

LiteLLM's `_check_and_fix_if_content_is_tool_call()` method passes the raw content (including tags) to `json.loads()`. Parsing fails, the method returns `None`, and the agent treats the response as plain text — the tool is never executed.

**Observed behavior:** An agent sends a tool-calling request to a llama-swap model. The model responds with a valid tool call, but wrapped in `...`. LiteLLM's parser sees invalid JSON, returns no tool call, and the agent receives a text message containing the raw JSON string. The loop breaks.

---

## Root Cause

The `...` tags are a llama.cpp convention for marking code blocks — equivalent to Markdown backtick fences but without the backticks. LiteLLM does not strip them before JSON parsing.

Relevant code in `litellm/llms/openai/chat/gpt_transformation.py` (line 494):

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

The `except Exception` block silently catches the `json.JSONDecodeError` and returns `None`, so the failure is invisible in logs.

---

## Justification

### Why patch instead of fix at the source?

**Option A — Fix at the model/chat-template level.** Some would suggest adjusting the llama.cpp chat template to omit `...` around tool calls. This was rejected for two reasons:

1. The `...` tags are a **llama.cpp convention**, not a bug. They signal "this is code" to the model during generation. Removing them from the template risks the model producing malformed JSON (the tags help the model stay structured).
2. Multiple models share the same llama-swap config. A template change affects all models and may break other behavior.

**Option B — Fix at the LiteLLM level.** This is the right place because:

1. LiteLLM is the **translation layer** between OpenAI-compatible responses and the caller. It already handles provider-specific quirks (e.g., Anthropic's function calling format conversion). Stripping `...` tags fits this pattern.
2. The fix is **localized** — one method, one condition, no changes to chat templates or model behavior.
3. The fix is **non-breaking** — when no `...` tags are present, the content passes through unchanged.

### Why this specific approach?

- **String operations over regex:** `startswith("...")` + slicing is faster and simpler than `re.sub(r'^\.\.\.(.*)\.\.\.$', r'\1', content)`. This runs on every assistant message.
- **Single-layer stripping:** Only one pass of `...` removal. Nested `...` are not expected and would indicate a model issue needing separate investigation.
- **No changes to other parsers:** This targets only `_check_and_fix_if_content_is_tool_call()`. The streaming path may need similar treatment but is deferred until a real issue is observed.

---

## Solution

```python
def _check_and_fix_if_content_is_tool_call(
    self, content: str, optional_params: dict
) -> Optional[ChatCompletionMessageToolCall]:
    import json

    if not self._passed_in_tools(optional_params):
        return None
    tool_call_names = get_tool_call_names(optional_params.get("tools", []))

    # Strip ... wrapper tags (llama.cpp convention for code blocks)
    stripped = content.strip()
    if stripped.startswith("...") and stripped.endswith("..."):
        stripped = stripped[3:-3].strip()

    try:
        json_content = json.loads(stripped)  # ← uses stripped content
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

### Changes

1. Added `import json` already exists — no change.
2. Added 4 lines between `tool_call_names = ...` and `try:`:
   - `stripped = content.strip()`
   - `if stripped.startswith("...") and stripped.endswith("..."): `
   - `    stripped = stripped[3:-3].strip()`
3. Changed `json.loads(content)` → `json.loads(stripped)`

**Net change: 4 new lines, 1 modified line.**

---

## Testing

| Scenario | Input | Expected |
|----------|-------|----------|
| Normal tool call with `...` | `...{"type":"function","name":"bash","arguments":"..."}...` | Parsed correctly, tool executed |
| Normal tool call without `...` | `{"type":"function","name":"bash","arguments":"..."}` | Parsed correctly (no change) |
| Starts with `...` but doesn't end | `...{"type":"function"} extra text` | Not stripped, parsing fails → None (existing behavior) |
| Empty after stripping | `......` (six dots) | Stripped to empty string, `json.loads("")` → None |
| Cloud model response | `{"type":"function",...}` | No `...` tags → no stripping → parsed normally |
| Non-tool-call content | `Hello, how are you?` | No `...` tags → no change → not a tool call → None |

---

## Scope

**In scope:**
- Non-streaming tool call parsing in `_check_and_fix_if_content_is_tool_call()`
- The `...` tag convention from llama.cpp

**Out of scope (deferred):**
- Streaming tool call chunk assembly (may need similar treatment)
- Other wrapper conventions (e.g., ```) — use standard Markdown stripping if needed later
- Chat template adjustments in llama-swap
