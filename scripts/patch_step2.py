#!/usr/bin/env python3
"""Patch gpt_transformation.py - Step 2: Add 4 static methods before _get_finish_reason."""
import sys

FILE = "litellm/llms/openai/chat/gpt_transformation.py"

with open(FILE, "r") as f:
    content = f.read()

marker = """        return None

    def _get_finish_reason(self, message: Message, received_finish_reason: str) -> str:"""

if marker not in content:
    print("ERROR: Could not find marker before _get_finish_reason")
    sys.exit(1)

BT = chr(96)
US = chr(95)

# Build the regex pattern for 3 backticks + underscore
open_tag = 3 * BT + US  # `` ` ` `_` ``
close_tag = US + 3 * BT  # `` `_` ` ` `_` ` ` `_` ``
pattern_str = "r'" + open_tag + r"\\s*(.*?)\\s*" + close_tag + "'"

# Build the methods
new_methods = '''        return None

    @staticmethod
    def _extract_xml_from_tool_call_tags(content: str) -> Optional[str]:
        import re
        match = re.search(''' + pattern_str + ''', content, re.DOTALL)
        if match:
            xml_content = match.group(1).strip()
            if xml_content.startswith("<function="):
                return xml_content
        return None

    @staticmethod
    def _extract_json_from_tool_call_tags(content: str) -> Optional[str]:
        import re
        match = re.search(''' + pattern_str + ''', content, re.DOTALL)
        if match:
            json_content = match.group(1).strip()
            if json_content.startswith("{"):
                return json_content
        return None

    @staticmethod
    def _parse_qwen_xml_to_tool_call(xml_content: str) -> Optional[ChatCompletionMessageToolCall]:
        import json, re
        func_match = re.match(r"<function=(\\S+?)>", xml_content)
        if not func_match:
            return None
        func_name = func_match.group(1)
        arguments = {}
        for param_match in re.finditer(r"<parameter=(\\S+)>(.*?)</parameter>", xml_content, re.DOTALL):
            param_name = param_match.group(1)
            param_value = param_match.group(2).strip()
            try:
                param_value = json.loads(param_value)
            except (json.JSONDecodeError, TypeError):
                pass
            arguments[param_name] = param_value
        return ChatCompletionMessageToolCall(
            function=Function(name=func_name, arguments=json.dumps(arguments, separators=(",", ":")))
        )

    @staticmethod
    def _parse_json_to_tool_call(json_content: str) -> Optional[ChatCompletionMessageToolCall]:
        import json
        try:
            parsed = json.loads(json_content)
            func_name = parsed.get("name")
            arguments = parsed.get("arguments")
            if not func_name:
                return None
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, separators=(",", ":"))
            elif isinstance(arguments, str):
                pass
            elif arguments is None:
                arguments = "{}"
            else:
                arguments = json.dumps(arguments, separators=(",", ":"))
            return ChatCompletionMessageToolCall(
                function=Function(name=func_name, arguments=arguments)
            )
        except (json.JSONDecodeError, TypeError):
            return None

    def _get_finish_reason(self, message: Message, received_finish_reason: str) -> str:'''

content = content.replace(marker, new_methods)

with open(FILE, "w") as f:
    f.write(content)

print("Step 2 done: 4 static methods added")
print("File now has", len(content), "chars")
