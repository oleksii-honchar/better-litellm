#!/usr/bin/env python3
"""Patch gpt_transformation.py for Qwen XML and JSON tool call extraction."""
import sys

FILE = "litellm/llms/openai/chat/gpt_transformation.py"

with open(FILE, "r") as f:
    lines = f.readlines()

# Find line numbers
check_and_fix_line = None
get_finish_reason_line = None
transform_choices_line = None
chunk_parser_line = None

for i, line in enumerate(lines):
    if "def _check_and_fix_if_content_is_tool_call(" in line:
        check_and_fix_line = i
    if "def _get_finish_reason(" in line:
        get_finish_reason_line = i
    if "def _transform_choices(" in line and "OpenAIGPTConfig" not in lines[i-1] if i > 0 else True:
        if transform_choices_line is None:
            transform_choices_line = i
    if "def chunk_parser(" in line:
        chunk_parser_line = i

print(f"check_and_fix line: {check_and_fix_line}")
print(f"get_finish_reason line: {get_finish_reason_line}")
print(f"transform_choices line: {transform_choices_line}")
print(f"chunk_parser line: {chunk_parser_line}")

if any(v is None for v in [check_and_fix_line, get_finish_reason_line, transform_choices_line, chunk_parser_line]):
    print("ERROR: Could not find all markers")
    sys.exit(1)
