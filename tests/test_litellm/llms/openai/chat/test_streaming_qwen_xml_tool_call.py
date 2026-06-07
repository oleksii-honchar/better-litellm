"""
Streaming tests for Qwen XML and JSON tool call extraction.
"""
import json
import pytest
from litellm.llms.openai.chat.gpt_transformation import (
    OpenAIGPTConfig,
    OpenAIChatCompletionStreamingHandler,
)


class TestExtractToolCallsFromBuffer:
    @pytest.fixture
    def handler(self):
        return OpenAIChatCompletionStreamingHandler.__new__(OpenAIChatCompletionStreamingHandler)

    def test_simple_qwen_xml_in_buffer(self, handler):
        handler._tool_call_buffer = "```_\n<function=bash>\n<parameter=command>\necho hello\n</parameter>\n</function>\n_```"
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "bash"
        args = json.loads(tool_calls[0].function.arguments)
        assert args["command"] == "echo hello"
        assert remaining == ""

    def test_simple_json_in_buffer(self, handler):
        handler._tool_call_buffer = '```_\n{"name": "bash", "arguments": {"command": "echo hello"}}\n_```'
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "bash"
        args = json.loads(tool_calls[0].function.arguments)
        assert args["command"] == "echo hello"
        assert remaining == ""

    def test_no_tool_calls_in_buffer(self, handler):
        handler._tool_call_buffer = "Hello world"
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 0
        assert remaining == "Hello world"

    def test_partial_tool_call_not_extracted(self, handler):
        handler._tool_call_buffer = "```_\n<function=bash>"
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 0

    def test_empty_buffer(self, handler):
        handler._tool_call_buffer = ""
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 0
        assert remaining == ""

    def test_tool_call_with_id(self, handler):
        handler._tool_call_buffer = "```_\n<function=bash>\n</function>\n_```"
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 1
        assert tool_calls[0].id.startswith("call_")
        assert tool_calls[0].type == "function"

    def test_json_tool_call_with_id(self, handler):
        handler._tool_call_buffer = '```_\n{"name": "bash"}\n_```'
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 1
        assert tool_calls[0].id.startswith("call_")
        assert tool_calls[0].type == "function"

    def test_json_with_dict_arguments(self, handler):
        handler._tool_call_buffer = '```_\n{"name": "bash", "arguments": {"command": "ls -la"}}\n_```'
        remaining, tool_calls = handler._extract_tool_calls_from_buffer()
        assert len(tool_calls) == 1
        args = json.loads(tool_calls[0].function.arguments)
        assert args["command"] == "ls -la"
