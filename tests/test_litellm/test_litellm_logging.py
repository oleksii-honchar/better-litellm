"""
Tests for get_usage_as_dict PrivateAttrs inclusion.

These tests verify that get_usage_as_dict includes cache_read_input_tokens
and cache_creation_input_tokens in the output dict (keys WITHOUT underscore prefix,
matching OTel/Langfuse/Prometheus expectations).

TDD RED phase — Tests 1-2 will FAIL against current code because:
- PrivateAttrs are excluded from model_dump() output
- get_usage_as_dict does not merge PrivateAttrs into the result
"""

import pytest
from litellm.types.utils import Usage
from litellm.litellm_core_utils.litellm_logging import StandardLoggingPayloadSetup


# =============================================================================
# Test 1: get_usage_as_dict includes cache_read_input_tokens (no underscore prefix)
# EXPECTED: FAIL (RED) — PrivateAttrs excluded from model_dump()
def test_get_usage_as_dict_includes_cache_read_input_tokens():
    """get_usage_as_dict should include cache_read_input_tokens in output dict (no underscore prefix)"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cached_tokens": 100},
    )
    # Manually set the PrivateAttr to simulate the mapping being done
    usage._cache_read_input_tokens = 100

    result = StandardLoggingPayloadSetup.get_usage_as_dict(
        response_obj=None, combined_usage_object=usage
    )
    assert "cache_read_input_tokens" in result, (
        f"Key not found in {result.keys()}"
    )
    assert result["cache_read_input_tokens"] == 100


# =============================================================================
# Test 2: get_usage_as_dict includes cache_creation_input_tokens (no underscore prefix)
# EXPECTED: FAIL (RED) — PrivateAttrs excluded from model_dump()
def test_get_usage_as_dict_includes_cache_creation_input_tokens():
    """get_usage_as_dict should include cache_creation_input_tokens in output dict (no underscore prefix)"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cache_creation_tokens": 50},
    )
    # Manually set the PrivateAttr to simulate the mapping being done
    usage._cache_creation_input_tokens = 50

    result = StandardLoggingPayloadSetup.get_usage_as_dict(
        response_obj=None, combined_usage_object=usage
    )
    assert "cache_creation_input_tokens" in result, (
        f"Key not found in {result.keys()}"
    )
    assert result["cache_creation_input_tokens"] == 50


# =============================================================================
# Test 3: get_usage_as_dict includes zero cache tokens
# EXPECTED: PASS — zero defaults exist in dict
# =============================================================================
def test_get_usage_as_dict_includes_zero_cache_tokens():
    """get_usage_as_dict should include zero-valued cache tokens in output dict"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
    )
    result = StandardLoggingPayloadSetup.get_usage_as_dict(
        response_obj=None, combined_usage_object=usage
    )
    # After fix, these keys should exist with value 0 even when no cache data
    assert "cache_read_input_tokens" in result
    assert result["cache_read_input_tokens"] == 0
    assert "cache_creation_input_tokens" in result
    assert result["cache_creation_input_tokens"] == 0
