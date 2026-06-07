# 01 — Tool Call Wrapper Tag Extraction

**Date:** 2026-05-30 (updated 2026-06-05)
**Status:** Implemented (Phase: Completed)
**Branch:** `feat/spec-01`
**Session**: /Users/oleksii.honchar/.agent-sessions/26/05/20/260520-1441-octocode-toolcall-litellm
---

## Description

LiteLLM's `_check_and_fix_if_content_is_tool_call()` method and streaming `chunk_parser()` need to extract tool calls from Qwen-style XML tool call formats — including `...` wrapper tags, `<![CDATA[...]]>` wrappers, `<tool_call>...</tool_call>` wrappers, and JSON — when models served through llama.cpp return them.

---

## Problem

When models served through llama-swap (llama.cpp) return tool calls, they use one of several formats:

1. **Qwen XML in `...` tags** (most common in streaming):
   ```
   _<function=bash><parameter=command>ls</parameter></function>_
   ```

2. **JSON in `...` tags**:
   ```
   _{"name":"bash","arguments":{"command":"ls"}}_
   ```

3. **Qwen XML in `<tool_call>` wrapper tags**:
   ```xml
   <tool_call><function=grep><parameter=include>*.py</parameter></function></tool_call>
   ```

4. **Qwen XML in CDATA**:
   ```xml
   <![CDATA[<function=grep><parameter=include>*.py</parameter></function>]]>
   ```

5. **JSON in `<tool_call>` wrapper tags** (opencode-style or OpenAI-style):
   ```json
   <tool_call>{"type":"bash","command":"ls"}_</tool_call>
   ```
   Or:
   ```json
   <tool_call>{"name":"bash","arguments":{"command":"ls"}}_</tool_call>
   ```

6. **Pure JSON** (no wrapper):
   ```json
   {"name":"bash","arguments":{"command":"ls"}}
   ```

LiteLLM's `_check_and_fix_if_content_is_tool_call()` method passes the raw content (including tags) to `json.loads()`. Parsing fails, the method returns `None`, and the agent treats the response as plain text — the tool is never executed.

Additionally, llama.cpp's PEG autoparser (`common/chat.cpp:2601`) may fail on formats 3 and 4 when the server's chat template doesn't include `<tool_call>` wrapper tags. This generates a `400 Bad Request` error with the raw model output embedded in the error message — which requires error recovery, not just parsing.

---

## Root Cause

1. **Multiple output formats:** The Qwopus3.6 model is trained on multiple tool call formats and may output any of them depending on context.
2. **No extraction in litellm:** LiteLLM only attempts `json.loads(content)` — no XML extraction, no CDATA stripping, no `<tool_call>` wrapper detection.
3. **llama.cpp PEG parse error:** The mammoth server's chat template was built without `<tool_call>` wrapper tags. When the model outputs format 3, the PEG parser fails at the `<tool_call>` tag position and returns a 400 error.

---

## Solution

### 6-Format Extraction Cascade (was 5-Format)

In `_check_and_fix_if_content_is_tool_call()`, try extraction in this order:

| Order | Format | Method | Trigger |
|-------|--------|--------|---------|
| 1 | Qwen XML in `...` tags | `_extract_xml_from_tool_call_tags()` | Content starts/ends with `...` |
| 2 | JSON in `...` tags | `_extract_json_from_tool_call_tags()` | Content starts/ends with `...` |
| 3 | Qwen XML in `<tool_call>` tags | `_extract_xml_from_tool_call_wrapper_tags()` | Contains `<tool_call>` |
| 4 | Qwen XML in CDATA | `_extract_xml_from_cdata_tags()` | Contains `<![CDATA[` |
| 5 | JSON in `<tool_call>` tags | `_extract_json_from_tool_call_wrapper_tags()` + `_parse_opencode_json_to_tool_call()` | Contains `<tool_call>` + `{` |
| 6 | Pure JSON | `_parse_json_to_tool_call()` | Try `json.loads()` |

### Streaming Buffer-Based Extraction

Add `_tool_call_buffer` state to `OpenAIChatCompletionStreamingHandler.__init__()`. Modify `chunk_parser()` to:

1. Accumulate content across chunks into `_tool_call_buffer`
2. When content or buffer contains `...`, `<tool_call`, or `<![CDATA[`, attempt extraction via `_extract_tool_calls_from_buffer()`
3. On successful extraction: set `delta["content"] = ""` (already emitted), emit `delta["tool_calls"]`, clear buffer
4. On incomplete detection: leave content in buffer for next chunk
5. Normal chunks (no tool call markers) pass through unchanged

### llama.cpp PEG Parse Error Recovery

Catch `openai.BadRequestError` with "Failed to parse input at pos N" in:

- **Non-streaming** (`make_openai_chat_completion_request`): Extract tool calls from error message, reconstruct `ChatCompletion` via `_reconstruct_chat_completion_response()`
- **Streaming** (`__anext__`/`__next__` in `CustomStreamWrapper`): Extract tool calls from error message, yield `ModelResponseStream` with `finish_reason="tool_calls"`, set `completion_stream = None` AND `make_call = None`

---

## Changes

### File: `litellm/llms/openai/chat/gpt_transformation.py`

#### New Static Methods on `OpenAIGPTConfig`

1. **`_extract_xml_from_tool_call_tags(text) -> Optional[str]`** — Extract Qwen XML from `...` tags
   ```python
   @staticmethod
   def _extract_xml_from_tool_call_tags(text: str) -> Optional[str]:
       match = re.search(r"```[\s]*(<function=\S+?>.*?</function>)\s*```", text, re.DOTALL)
       if match:
           return match.group(1)
       return None
   ```

2. **`_extract_json_from_tool_call_tags(text) -> Optional[str]`** — Extract JSON from `...` tags
   ```python
   @staticmethod
   def _extract_json_from_tool_call_tags(text: str) -> Optional[str]:
       match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
       if match:
           return match.group(1)
       return None
   ```

3. **`_extract_xml_from_tool_call_wrapper_tags(text) -> Optional[str]`** — Extract Qwen XML from `<tool_call>` wrapper
   ```python
   @staticmethod
   def _extract_xml_from_tool_call_wrapper_tags(text: str) -> Optional[str]:
       match = re.search(
           r"<tool_call[^>]*>\s*(<function=\S+?>.*?</function>)\s*</tool_call>",
           text, re.DOTALL
       )
       if match:
           return match.group(1)
       return None
   ```

4. **`_extract_xml_from_cdata_tags(text) -> Optional[str]`** — Extract Qwen XML from CDATA
   ```python
   @staticmethod
   def _extract_xml_from_cdata_tags(text: str) -> Optional[str]:
       match = re.search(r"<!\[CDATA\[(<function=\S+?>.*?</function>)\]\]>", text, re.DOTALL)
       if match:
           return match.group(1)
       return None
   ```

5. **`_parse_qwen_xml_to_tool_call(xml_content) -> Optional[ChatCompletionMessageToolCall]`** — Parse `<function>`/`<parameter>` XML elements
   ```python
   @staticmethod
   def _parse_qwen_xml_to_tool_call(xml_content: str) -> Optional[ChatCompletionMessageToolCall]:
       import re
       import json
       import uuid
       # ... regex parsing of function name and parameters ...
   ```

6. **`_parse_json_to_tool_call(data) -> Optional[ChatCompletionMessageToolCall]`** — Parse JSON to tool call (backward compat)

7. **`_extract_json_from_tool_call_wrapper_tags(text) -> Optional[str]`** — Extract JSON from `<tool_call>` wrapper tags
   ```python
   @staticmethod
   def _extract_json_from_tool_call_wrapper_tags(text: str) -> Optional[str]:
       for match in re.finditer(
           r'<tool_call[^>]*>\s*(\{.*?\})\s*</tool_call>',
           text, re.DOTALL
       ):
           json_content = match.group(1).strip()
           if json_content.startswith("{"):
               return json_content
       return None
   ```

8. **`_parse_opencode_json_to_tool_call(json_content) -> Optional[ChatCompletionMessageToolCall]`** — Parse `<tool_call>` JSON (opencode `"type"` key and OpenAI `"name"` key)
    ```python
    @staticmethod
    def _parse_opencode_json_to_tool_call(json_content: str) -> Optional[ChatCompletionMessageToolCall]:
        parsed = json.loads(json_content)
        # opencode uses "type" for tool name, OpenAI uses "name"
        tool_name = parsed.get("type") or parsed.get("name")
        if not tool_name:
            return None
        # OpenAI-style with "arguments" key
        if "arguments" in parsed:
            arguments = json.dumps(parsed["arguments"]) if isinstance(parsed["arguments"], dict) else parsed["arguments"]
        else:
            # opencode-style: all non-"type"/"name" keys are arguments
            arguments = json.dumps({k: v for k, v in parsed.items() if k not in ("type", "name")}, separators=(",", ":"))
        return ChatCompletionMessageToolCall(
            function=Function(name=tool_name, arguments=arguments)
        )
    ```

9. **`_is_llamacpp_parse_error(message) -> bool`** — Detect llama.cpp PEG parse error
   ```python
   @staticmethod
   def _is_llamacpp_parse_error(message: str) -> bool:
       return "Failed to parse input at pos" in str(message)
   ```

10. **`_extract_tool_calls_from_llamacpp_error(error_text) -> Optional[List[ChatCompletionMessageToolCall]]`** — Extract tool calls from error message, tries all 6 formats

#### Modified: `_check_and_fix_if_content_is_tool_call()`

```
Before: json.loads(content) only → silently fails for non-JSON
After:  Try 6 formats in cascade → returns ChatCompletionMessageToolCall for any
```

#### Modified: `chunk_parser()` (streaming)

```
Before: Pass-through with no tool call extraction
After:  Content accumulated in _tool_call_buffer, extracted when complete, 
        buffer cleared, delta["content"] = "" after extraction
```

### File: `litellm/llms/openai/openai.py`

#### New: `_reconstruct_chat_completion_response()`

```python
def _reconstruct_chat_completion_response(
    model: str,
    tool_calls: List[ChatCompletionMessageToolCall],
) -> ChatCompletion:
    """Reconstruct a ChatCompletion from extracted tool calls."""
```

#### Modified: `make_openai_chat_completion_request()` (async)

```
try:
    response = await client.chat.completions.create(**request_data)
except openai.BadRequestError as e:
    if "Failed to parse input at pos" in str(e):
        tool_calls = OpenAIGPTConfig._extract_tool_calls_from_llamacpp_error(str(e))
        if tool_calls:
            return _reconstruct_chat_completion_response(model, tool_calls)
    raise
```

#### Modified: `make_sync_openai_chat_completion_request()` (sync) — Same pattern

### File: `litellm/litellm_core_utils/streaming_handler.py`

#### New: `_try_recover_llamacpp_parse_error()`

#### Modified: `__anext__()` and `__next__()`

```python
except Exception as e:
    if "Failed to parse input at pos" in str(e):
        recovered = self._try_recover_llamacpp_parse_error(str(e))
        if recovered is not None:
            self.completion_stream = None  # Terminate errored stream
            self.make_call = None          # Prevent fetch_stream from re-fetching
            return recovered
```

---

## Bugs Found and Fixed

### 1. Qwen XML Parameter Regex (Critical)

**Bug:** `\S+` in `<parameter=(\S+)>` over-consumed when values on same line:
```python
# Before (wrong):
r"<parameter=(\S+)>(.*?)</parameter>"
# After (fixed):
r"<parameter=([^>]+)>(.*?)</parameter>"
```

**Impact:** All same-line parameter names were wrong. Fixes CDATA and `<tool_call>` wrapper format parsing.

### 2. Streaming Content Duplication (Critical)

**Bug:** After extracting a tool call from the buffer, `delta["content"] = remaining` re-emitted all previously-emitted text.

**Fix:** `delta["content"] = ""` and `self._tool_call_buffer = ""` after extraction.

### 3. Streaming Recovery Re-Fetch (Critical)

**Bug:** After streaming recovery, `self.completion_stream = None` caused `fetch_stream()` to make a new HTTP request on the next `__anext__` call, resulting in `'NoneType' object is not an iterator`.

**Root cause:** `fetch_stream()` condition: `if self.completion_stream is None and self.make_call is not None`.

**Fix:** Also set `self.make_call = None` after recovery.

---

## Testing

| Suite | Tests | Pass | Fail | Description |
|-------|-------|------|------|-------------|
| `test_openai_gpt_transformation.py` | 39 | 39 | 0 | Original tests + error detection/extraction/recovery |
| `test_qwen_xml_tool_call.py` | 33 | 33 | 0 | Non-streaming Qwen XML/JSON/CDATA/`<tool_call>` parsing |
| `test_streaming_qwen_xml_tool_call.py` | 8 | 8 | 0 | Streaming buffer extraction |
| **Total** | **80** | **80** | **0** | **Zero regressions** |

### Key Test Cases

- Qwen XML in `...` tags: function name, parameters, empty params, multiline values
- JSON in `...` tags: backward compat with existing tools
- `<tool_call>` wrapper: plain, with whitespace, with attributes
- CDATA wrapper: inside and outside error messages
- JSON in `<tool_call>` wrapper: opencode-style (`"type":"bash"`), OpenAI-style (`"name":"bash","arguments":{...}`)
- llama.cpp error recovery: non-streaming, streaming, non-PEG errors re-raised
- Streaming buffer: multi-chunk, text-before-tool-call (regression for duplication), multiple tool calls
- `make_call = None` verification: no re-fetch after streaming recovery

---

## Commits

| Hash | Message | Date |
|------|---------|------|
| `6b62623282` | feat(openai): add multi-format tool call parsing for GPT models | 2026-05-24 |
| `830e4631bd` | feat(openai): recover tool calls from llama.cpp PEG parse errors | 2026-05-30 |
| `0d703cde63` | fix(streaming_handler): terminate stream on successful Llama.cpp parse recovery | 2026-05-30 |
| `b55ec6f011` | `<tool_call>` wrapper tag support in error parsing | 2026-05-30 |
| `0c1934f42e` | CDATA XML support | 2026-05-30 |

**Uncommitted:** `self.make_call = None` streaming fix (2026-05-30)

## Post-PR Follow-up (2026-06-05): JSON in `<tool_call>` Wrapper Tags

**Status:** Implemented (uncommitted)

**Problem:** The extraction cascade was missing format 5 — JSON inside `<tool_call>` tags. When models output `<tool_call>{"type":"bash","command":"ls"}</tool_call>` (opencode-style) or `<tool_call>{"name":"bash","arguments":{"command":"ls"}}</tool_call>` (OpenAI-style), it fell through to pure-JSON which failed because the `<tool_call>` wrapper was still present.

This format appeared when:
1. The model's chat template includes `<tool_call>` wrapper tags
2. The model outputs the tool call as JSON inside those tags instead of Qwen XML
3. The PEG parser in llama.cpp rejects it (non-Qwen-XML content in `<tool_call>`)
4. The resulting 400 error goes through `_extract_tool_calls_from_llamacpp_error()`, which also missed this format

**Changes:**

- **`_extract_json_from_tool_call_wrapper_tags(text)`** (new static method) — Extracts JSON from `<tool_call>...\n</tool_call>` wrapper
- **`_parse_opencode_json_to_tool_call(json_content)`** (new static method) — Handles opencode `"type"` key and OpenAI `"name"`+`"arguments"` key
- **`_check_and_fix_if_content_is_tool_call()`** — Added step 5 (JSON in `<tool_call>` tags) between CDATA and pure JSON
- **`_extract_tool_calls_from_llamacpp_error()`** — Added JSON-in-`<tool_call>` extraction inline
- **`_extract_tool_calls_from_buffer()`** — Added JSON-in-`<tool_call>` extraction with same inline logic

All three code paths (normal, error-recovery, streaming) now handle the format.
