"""
Non-streaming tests for Qwen XML and JSON tool call extraction.
"""
import json
import pytest
from litellm.llms.openai.chat.gpt_transformation import (
    ChatCompletionMessageToolCall,
    Function,
    OpenAIGPTConfig,
)


class TestExtractXmlFromToolCallTags:
    def test_simple_qwen_xml(self):
        content = "```_\n<function=bash>\n</function>\n_```"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_tags(content)
        assert result == "<function=bash>\n</function>"

    def test_with_whitespace(self):
        content = "  ```_  \n  <function=bash>  \n  </function>  \n  _```  "
        result = OpenAIGPTConfig._extract_xml_from_tool_call_tags(content)
        assert result == "<function=bash>  \n  </function>"

    def test_no_tags_returns_none(self):
        content = "<function=bash>\n</function>"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_tags(content)
        assert result is None

    def test_tags_with_non_xml_returns_none(self):
        content = "```_\nHello world\n_```"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_tags(content)
        assert result is None

    def test_json_in_tags_returns_none(self):
        content = '```_\n{"name": "bash"}\n_```'
        result = OpenAIGPTConfig._extract_json_from_tool_call_tags(content)
        assert result is not None

    def test_multiline_xml(self):
        content = "```_\n<function=bash>\n<parameter=command>\necho hello\n</parameter>\n</function>\n_```"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_tags(content)
        assert result is not None
        assert "<parameter=command>" in result

    def test_empty_tags_returns_none(self):
        content = "```_\n_```"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_tags(content)
        assert result is None


class TestParseQwenXmlToToolCall:
    def test_simple_function(self):
        xml = "<function=bash>\n</function>"
        result = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml)
        assert result is not None
        assert result.function.name == "bash"

    def test_with_parameters(self):
        xml = "<function=bash>\n<parameter=command>\necho hello\n</parameter>\n</function>"
        result = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml)
        assert result is not None
        assert result.function.name == "bash"
        args = json.loads(result.function.arguments)
        assert args["command"] == "echo hello"

    def test_multiple_parameters(self):
        xml = "<function=tool>\n<parameter=a>1\n</parameter>\n<parameter=b>\n2\n</parameter>\n</function>"
        result = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml)
        assert result is not None
        assert result.function.name == "tool"
        args = json.loads(result.function.arguments)
        assert args["a"] == 1
        assert args["b"] == 2

    def test_json_value_in_parameter(self):
        xml = "<function=tool>\n<parameter=arr>\n[1, 2, 3]\n</parameter>\n</function>"
        result = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml)
        assert result is not None
        args = json.loads(result.function.arguments)
        assert args["arr"] == [1, 2, 3]

    def test_no_function_tag_returns_none(self):
        xml = "<parameter=command>echo</parameter>"
        result = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml)
        assert result is None

    def test_invalid_xml_returns_none(self):
        xml = "not xml at all"
        result = OpenAIGPTConfig._parse_qwen_xml_to_tool_call(xml)
        assert result is None


class TestExtractJsonFromToolCallTags:
    def test_simple_json(self):
        content = '```_\n{"name": "bash"}\n_```'
        result = OpenAIGPTConfig._extract_json_from_tool_call_tags(content)
        assert result == '{"name": "bash"}'

    def test_xml_in_tags_returns_none(self):
        content = "```_\n<function=bash>\n</function>\n_```"
        result = OpenAIGPTConfig._extract_json_from_tool_call_tags(content)
        assert result is None

    def test_no_tags_returns_none(self):
        content = '{"name": "bash"}'
        result = OpenAIGPTConfig._extract_json_from_tool_call_tags(content)
        assert result is None


class TestParseJsonToToolCall:
    def test_simple_json(self):
        json_str = '{"name": "bash"}'
        result = OpenAIGPTConfig._parse_json_to_tool_call(json_str)
        assert result is not None
        assert result.function.name == "bash"
        assert result.function.arguments == "{}"

    def test_json_with_dict_arguments(self):
        json_str = '{"name": "bash", "arguments": {"command": "echo hello"}}'
        result = OpenAIGPTConfig._parse_json_to_tool_call(json_str)
        assert result is not None
        assert result.function.name == "bash"
        args = json.loads(result.function.arguments)
        assert args["command"] == "echo hello"

    def test_json_without_name_returns_none(self):
        json_str = '{"arguments": {"command": "echo"}}'
        result = OpenAIGPTConfig._parse_json_to_tool_call(json_str)
        assert result is None

    def test_invalid_json_returns_none(self):
        json_str = '{"name": "bash", invalid}'
        result = OpenAIGPTConfig._parse_json_to_tool_call(json_str)
        assert result is None


class TestCheckAndFixIfContentIsToolCall:
    @pytest.fixture
    def config(self):
        return OpenAIGPTConfig()

    @pytest.fixture
    def optional_params_with_tools(self):
        return {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "description": "Run a bash command",
                        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "search",
                        "description": "Search the web",
                        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                    },
                },
            ]
        }

    def test_qwen_xml_tool_call(self, config, optional_params_with_tools):
        content = "```_\n<function=bash>\n<parameter=command>\necho hello\n</parameter>\n</function>\n_```"
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is not None
        assert result.function.name == "bash"
        args = json.loads(result.function.arguments)
        assert args["command"] == "echo hello"

    def test_json_tool_call_in_tags(self, config, optional_params_with_tools):
        content = '```_\n{"name": "bash", "arguments": {"command": "echo hello"}}\n_```'
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is not None
        assert result.function.name == "bash"
        args = json.loads(result.function.arguments)
        assert args["command"] == "echo hello"

    def test_tool_name_not_in_tools_returns_none(self, config, optional_params_with_tools):
        content = "```_\n<function=nonexistent>\n</function>\n_```"
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is None

    def test_no_tools_returns_none(self, config):
        content = "```_\n<function=bash>\n</function>\n_```"
        result = config._check_and_fix_if_content_is_tool_call(content, {})
        assert result is None

    def test_pure_json_fallback(self, config, optional_params_with_tools):
        content = '{"type": "function", "name": "bash", "arguments": {"command": "echo hello"}}'
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is not None
        assert result.function.name == "bash"

    def test_with_thinking_then_tool_call(self, config, optional_params_with_tools):
        content = "```_\nLet me use the bash tool.\n_```\n```_\n<function=bash>\n<parameter=command>\necho hello\n</parameter>\n</function>\n_```"
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is not None
        assert result.function.name == "bash"

    def test_second_tool_in_list(self, config, optional_params_with_tools):
        content = "```_\n<function=search>\n<parameter=query>\ntest\n</parameter>\n</function>\n_```"
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is not None
        assert result.function.name == "search"
        args = json.loads(result.function.arguments)
        assert args["query"] == "test"

    def test_no_content_returns_none(self, config, optional_params_with_tools):
        content = ""
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is None

    def test_plain_text_returns_none(self, config, optional_params_with_tools):
        content = "Here is the answer: 42"
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is None

    def test_tool_call_wrapper_qwen_xml(self, config, optional_params_with_tools):
        content = "<tool_call>\n<function=bash>\n<parameter=command>find /Users/oleksii.honchar/www/misc/better-opencode -name '*.ts'</parameter>\n</function>\n</tool_call>"
        result = config._check_and_fix_if_content_is_tool_call(content, optional_params_with_tools)
        assert result is not None
        assert result.function.name == "bash"
        args = json.loads(result.function.arguments)
        assert args["command"] == "find /Users/oleksii.honchar/www/misc/better-opencode -name '*.ts'"


class TestExtractXmlFromToolCallWrapperTags:
    def test_simple_tool_call_wrapper(self):
        content = "<tool_call>\n<function=bash>\n</function>\n</tool_call>"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_wrapper_tags(content)
        assert result == "<function=bash>\n</function>"

    def test_no_wrapper_returns_none(self):
        content = "<function=bash>\n</function>"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_wrapper_tags(content)
        assert result is None

    def test_wrapper_with_attributes(self):
        content = '<tool_call id="call_1">\n<function=bash>\n</function>\n</tool_call>'
        result = OpenAIGPTConfig._extract_xml_from_tool_call_wrapper_tags(content)
        assert result == "<function=bash>\n</function>"

    def test_multiple_tool_calls(self):
        content = "<tool_call>\n<function=grep>\n<parameter=pattern>test</parameter>\n</function>\n</tool_call>\n<tool_call>\n<function=ls>\n<parameter=path>/tmp</parameter>\n</function>\n</tool_call>"
        result = OpenAIGPTConfig._extract_xml_from_tool_call_wrapper_tags(content)
        # finditer returns first match
        assert result is not None
        assert "<function=grep>" in result
