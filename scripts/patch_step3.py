#!/usr/bin/env python3
"""Patch gpt_transformation.py - Step 3: Add streaming buffer support."""
import sys

FILE = "litellm/llms/openai/chat/gpt_transformation.py"

with open(FILE, "r") as f:
    content = f.read()

# 1. Add __init__ with buffer to OpenAIChatCompletionStreamingHandler
init_marker = """class OpenAIChatCompletionStreamingHandler(BaseModelResponseIterator):
    def _map_reasoning_to_reasoning_content(self, choices: list) -> list:"""

init_replacement = """class OpenAIChatCompletionStreamingHandler(BaseModelResponseIterator):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tool_call_buffer = ""

    def _map_reasoning_to_reasoning_content(self, choices: list) -> list:"""

if init_marker not in content:
    print("ERROR: Could not find init_marker")
    sys.exit(1)

content = content.replace(init_marker, init_replacement)

# 2. Replace chunk_parser with buffer-based version
old_chunk = """    def chunk_parser(self, chunk: dict) -> ModelResponseStream:
        try:
            choices = chunk.get("choices", [])
            choices = self._map_reasoning_to_reasoning_content(choices)

            kwargs: Dict[str, Any] = {
                "id": chunk.get("id"),
                "object": "chat.completion.chunk",
                "created": chunk.get("created"),
                "model": chunk.get("model"),
                "choices": choices,
            }
            if "usage" in chunk and chunk["usage"] is not None:
                kwargs["usage"] = chunk["usage"]
            return ModelResponseStream(**kwargs)
        except Exception as e:
            raise e"""

new_chunk = """    def chunk_parser(self, chunk: dict) -> ModelResponseStream:
        try:
            choices = chunk.get("choices", [])
            choices = self._map_reasoning_to_reasoning_content(choices)

            for choice in choices:
                delta = choice.get("delta", {})
                content = delta.get("content", "")
                role = delta.get("role")

                # Reset buffer on new message
                if role is not None:
                    self._tool_call_buffer = ""

                # Skip if no content
                if content is None or content == "":
                    continue

                # Check for tool calls in buffer
                if self._tool_call_buffer:
                    self._tool_call_buffer += content
                    extracted_tc, tool_calls = self._extract_tool_calls_from_buffer()
                    if tool_calls:
                        # Set content to empty and add tool_calls
                        delta["content"] = ""
                        delta["tool_calls"] = tool_calls
                        choice["delta"] = delta
                        self._tool_call_buffer = extracted_tc
                        break

                # Check if content starts a tool call tag
                if "```_" in content or self._tool_call_buffer:
                    self._tool_call_buffer = (self._tool_call_buffer + content) if self._tool_call_buffer else content
                    extracted_tc, tool_calls = self._extract_tool_calls_from_buffer()
                    if tool_calls:
                        delta["content"] = ""
                        delta["tool_calls"] = tool_calls
                        choice["delta"] = delta
                        self._tool_call_buffer = extracted_tc
                        break

            kwargs: Dict[str, Any] = {
                "id": chunk.get("id"),
                "object": "chat.completion.chunk",
                "created": chunk.get("created"),
                "model": chunk.get("model"),
                "choices": choices,
            }
            if "usage" in chunk and chunk["usage"] is not None:
                kwargs["usage"] = chunk["usage"]
            return ModelResponseStream(**kwargs)
        except Exception as e:
            raise e

    def _extract_tool_calls_from_buffer(self):
        import json, re
        tool_calls = []
        remaining = self._tool_call_buffer

        # Qwen XML pattern
        xml_pattern = re.compile(r'_' + chr(96)*3 + r'_\\s*(<function=\\S+?>.*?</function>)\\s*' + r'_' + chr(96)*3 + r'_', re.DOTALL)
        for match in reversed(list(xml_pattern.finditer(remaining))):
            xml_content = match.group(1)
            tool_call = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml_content)
            if tool_call:
                tc_with_id = ChatCompletionMessageToolCall(
                    id=f"call_{len(tool_calls) + 1}",
                    type="function",
                    function=Function(name=tool_call.function.name, arguments=tool_call.function.arguments),
                )
                tool_calls.append(tc_with_id)
            remaining = remaining[:match.start()] + remaining[match.end():]

        # JSON pattern
        json_pattern = re.compile(r'_' + chr(96)*3 + r'_\\s*(\\{.*?\\})\\s*' + r'_' + chr(96)*3 + r'_', re.DOTALL)
        for match in reversed(list(json_pattern.finditer(remaining))):
            json_content = match.group(1)
            tool_call = OpenAIGPTConfig._parse_json_to_tool_call(json_content)
            if tool_call:
                tc_with_id = ChatCompletionMessageToolCall(
                    id=f"call_{len(tool_calls) + 1}",
                    type="function",
                    function=Function(name=tool_call.function.name, arguments=tool_call.function.arguments),
                )
                tool_calls.append(tc_with_id)
            remaining = remaining[:match.start()] + remaining[match.end():]

        return remaining, tool_calls"""

if old_chunk not in content:
    print("ERROR: Could not find chunk_parser")
    sys.exit(1)

content = content.replace(old_chunk, new_chunk)

with open(FILE, "w") as f:
    f.write(content)

print("Step 3 done: streaming buffer support added")
print("File now has", len(content), "chars")
