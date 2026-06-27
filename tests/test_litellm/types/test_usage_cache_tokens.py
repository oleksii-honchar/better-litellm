"""
Tests for cache token mapping from prompt_tokens_details to PrivateAttrs.

These tests verify that OpenAI's cached_tokens and cache_creation_tokens
from prompt_tokens_details are correctly mapped to _cache_read_input_tokens
and _cache_creation_input_tokens respectively.

TDD RED phase — Tests 1-3 and 8-9 will FAIL against current code because:
- prompt_tokens_details.cached_tokens is NOT mapped to _cache_read_input_tokens
- PrivateAttrs are excluded from model_dump() output
"""

import pytest
from litellm.types.utils import Usage


# =============================================================================
# Test 1: cached_tokens in prompt_tokens_details maps to _cache_read_input_tokens
# EXPECTED: FAIL (RED) — current code does not perform this mapping
# =============================================================================
def test_cached_tokens_maps_to_cache_read_input_tokens():
    """OpenAI cached_tokens should map to _cache_read_input_tokens"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cached_tokens": 100},
    )
    assert usage._cache_read_input_tokens == 100, (
        f"Expected 100, got {usage._cache_read_input_tokens}"
    )


# =============================================================================
# Test 2: cache_creation_tokens in prompt_tokens_details maps to _cache_creation_input_tokens
# EXPECTED: FAIL (RED) — current code does not perform this mapping
# =============================================================================
def test_cache_creation_tokens_maps_to_cache_creation_input_tokens():
    """OpenAI cache_creation_tokens should map to _cache_creation_input_tokens"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cache_creation_tokens": 50},
    )
    assert usage._cache_creation_input_tokens == 50, (
        f"Expected 50, got {usage._cache_creation_input_tokens}"
    )


# =============================================================================
# Test 3: Both cached_tokens and cache_creation_tokens map simultaneously
# EXPECTED: FAIL (RED) — current code does not perform this mapping
# =============================================================================
def test_both_cache_tokens_map_simultaneously():
    """Both cached_tokens and cache_creation_tokens should map"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cached_tokens": 100, "cache_creation_tokens": 50},
    )
    assert usage._cache_read_input_tokens == 100
    assert usage._cache_creation_input_tokens == 50


# =============================================================================
# Test 4: Zero cached_tokens is ignored
# EXPECTED: PASS — zero defaults to 0, no mapping needed
# =============================================================================
def test_zero_cached_tokens_is_ignored():
    """Zero cached_tokens should not set _cache_read_input_tokens"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cached_tokens": 0},
    )
    assert usage._cache_read_input_tokens == 0


# =============================================================================
# Test 5: None cached_tokens is ignored
# EXPECTED: PASS — None values are ignored, no mapping needed
# =============================================================================
def test_none_cached_tokens_is_ignored():
    """None cached_tokens should not set _cache_read_input_tokens"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_tokens_details={"cached_tokens": None},
    )
    assert usage._cache_read_input_tokens == 0


# =============================================================================
# Test 6: Anthropic cache_read_input_tokens via params still works
# EXPECTED: PASS — existing Anthropic mapping still works
# =============================================================================
def test_anthropic_cache_read_input_tokens_backward_compat():
    """Anthropic cache_read_input_tokens param should still work"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        cache_read_input_tokens=100,
    )
    assert usage._cache_read_input_tokens == 100


# =============================================================================
# Test 7: DeepSeek prompt_cache_hit_tokens via params still works
# EXPECTED: PASS — existing DeepSeek mapping still works
# =============================================================================
def test_deeplseek_prompt_cache_hit_tokens_backward_compat():
    """DeepSeek prompt_cache_hit_tokens param should still work"""
    usage = Usage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_cache_hit_tokens=100,
    )
    assert usage._cache_read_input_tokens == 100
