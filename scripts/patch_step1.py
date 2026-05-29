#!/usr/bin/env python3
"""Patch gpt_transformation.py - Step 1: Replace _check_and_fix_if_content_is_tool_call."""
import sys

FILE = "litellm/llms/openai/chat/gpt_transformation.py"

with open(FILE, "r") as f:
    content = f.read()

old = """    def _check_and_fix_if_content_is_tool_call(
        self, content: str, optional_params: dict
    ) -> Optional[ChatCompletionMessageToolCall]:
        \"\"\"
        Check if the content is a tool call
        \"\"\"
        import json

        if not self._passed_in_tools(optional_params):
            return None
        tool_call_names = get_tool_call_names(optional_params.get("tools", []))
        try:
            json_content = json.loads(content)
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

        return None"""

new = """    def _check_and_fix_if_content_is_tool_call(
        self, content: str, optional_params: dict
    ) -> Optional[ChatCompletionMessageToolCall]:
        \"\"\"
        Check if the content is a tool call.

        Tries:
        1. Qwen XML format (`` tags with <function>/<parameter> XML)
        2. JSON format inside `` tags ({\"name\":..., \"arguments\":...})
        3. Pure JSON format (backward compatibility)
        \"\"\"
        import json

        if not self._passed_in_tools(optional_params):
            return None
        tool_call_names = get_tool_call_names(optional_params.get("tools", []))

        # 1) Try Qwen XML format
        try:
            xml_content = self._extract_xml_from_tool_call_tags(content)
            if xml_content:
                tool_call = self._parse_qwen_xml_to_tool_call(xml_content)
                if tool_call and tool_call.function.name in tool_call_names:
                    return tool_call
        except Exception:
            pass

        # 2) Try JSON format inside `` tags
        try:
            json_content = self._extract_json_from_tool_call_tags(content)
            if json_content:
                tool_call = self._parse_json_to_tool_call(json_content)
                if tool_call and tool_call.function.name in tool_call_names:
                    return tool_call
        except Exception:
            pass

        # 3) Fall back to pure JSON format (backward compatibility)
        try:
            json_content = json.loads(content)
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

        return None"""

if old not in content:
    print("ERROR: Could not find _check_and_fix_if_content_is_tool_call")
    sys.exit(1)

content = content.replace(old, new)

with open(FILE, "w") as f:
    f.write(content)

print("Step 1 done: _check_and_fix_if_content_is_tool_call replaced")
print(f"File now has {len(content)} chars")
