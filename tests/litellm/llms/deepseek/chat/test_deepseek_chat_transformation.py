"""
Unit tests for DeepSeek chat transformation.

Tests the thinking and reasoning_effort parameter handling for DeepSeek models.
"""

import pytest
from litellm.llms.deepseek.chat.transformation import DeepSeekChatConfig


class TestDeepSeekThinkingParams:
    """Test thinking and reasoning_effort parameter handling for DeepSeek."""

    def setup_method(self):
        self.config = DeepSeekChatConfig()
        self.model = "deepseek-reasoner"

    def test_get_supported_openai_params_includes_thinking(self):
        """Test that thinking and reasoning_effort are in supported params."""
        params = self.config.get_supported_openai_params(self.model)
        assert "thinking" in params
        assert "reasoning_effort" in params

    def test_map_thinking_enabled(self):
        """Test that thinking={"type": "enabled"} is passed through correctly."""
        non_default_params = {"thinking": {"type": "enabled"}}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert result["thinking"] == {"type": "enabled"}

    def test_map_thinking_with_budget_tokens_strips_budget(self):
        """Test that budget_tokens is stripped from thinking param (DeepSeek doesn't support it)."""
        non_default_params = {"thinking": {"type": "enabled", "budget_tokens": 2048}}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        # Should strip budget_tokens, only pass type
        assert result["thinking"] == {"type": "enabled"}
        assert "budget_tokens" not in result.get("thinking", {})

    def test_map_reasoning_effort_medium(self):
        """Test that reasoning_effort='medium' maps to thinking enabled."""
        non_default_params = {"reasoning_effort": "medium"}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert result["thinking"] == {"type": "enabled"}

    def test_map_reasoning_effort_low(self):
        """Test that reasoning_effort='low' maps to thinking enabled."""
        non_default_params = {"reasoning_effort": "low"}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert result["thinking"] == {"type": "enabled"}

    def test_map_reasoning_effort_high(self):
        """Test that reasoning_effort='high' maps to thinking enabled."""
        non_default_params = {"reasoning_effort": "high"}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert result["thinking"] == {"type": "enabled"}

    def test_map_reasoning_effort_none_does_not_enable_thinking(self):
        """Test that reasoning_effort='none' does not enable thinking."""
        non_default_params = {"reasoning_effort": "none"}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert "thinking" not in result

    def test_map_reasoning_effort_null_does_not_enable_thinking(self):
        """Test that reasoning_effort=None does not enable thinking."""
        non_default_params = {"reasoning_effort": None}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert "thinking" not in result

    def test_thinking_takes_precedence_over_reasoning_effort(self):
        """Test that thinking param takes precedence when both are provided."""
        non_default_params = {
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        }
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        # thinking should be set, reasoning_effort should not override
        assert result["thinking"] == {"type": "enabled"}

    def test_invalid_thinking_type_ignored(self):
        """Test that invalid thinking type values are ignored."""
        non_default_params = {"thinking": {"type": "invalid"}}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert "thinking" not in result

    def test_thinking_none_value_ignored(self):
        """Test that thinking=None is ignored."""
        non_default_params = {"thinking": None}
        optional_params = {}

        result = self.config.map_openai_params(
            non_default_params=non_default_params,
            optional_params=optional_params,
            model=self.model,
            drop_params=False,
        )

        assert "thinking" not in result


class TestDeepSeekDefaultBaseUrl:
    """Test that DeepSeek provider uses the stable API base URL."""

    def setup_method(self):
        self.config = DeepSeekChatConfig()

    def test_get_openai_compatible_provider_info_default_base_url(self):
        """Test that _get_openai_compatible_provider_info returns stable base URL by default."""
        api_base, api_key = self.config._get_openai_compatible_provider_info(
            api_base=None, api_key=None
        )

        assert api_base == "https://api.deepseek.com"
        assert "/beta" not in api_base

    def test_get_openai_compatible_provider_info_respects_custom_base(self):
        """Test that _get_openai_compatible_provider_info respects custom api_base."""
        custom_base = "https://custom.deepseek.example.com"
        api_base, _ = self.config._get_openai_compatible_provider_info(
            api_base=custom_base, api_key=None
        )

        assert api_base == custom_base

    def test_get_complete_url_default_base_url(self):
        """Test that get_complete_url uses stable base URL when api_base is not provided."""
        url = self.config.get_complete_url(
            api_base=None,
            api_key=None,
            model="deepseek-chat",
            optional_params={},
            litellm_params={},
        )

        assert url == "https://api.deepseek.com/chat/completions"
        assert "/beta" not in url

    def test_get_complete_url_respects_custom_base(self):
        """Test that get_complete_url respects custom api_base."""
        custom_base = "https://custom.deepseek.example.com"
        url = self.config.get_complete_url(
            api_base=custom_base,
            api_key=None,
            model="deepseek-chat",
            optional_params={},
            litellm_params={},
        )

        assert url == "https://custom.deepseek.example.com/chat/completions"

    def test_get_complete_url_preserves_trailing_completions(self):
        """Test that get_complete_url does not double-append /chat/completions."""
        url = self.config.get_complete_url(
            api_base="https://api.deepseek.com/chat/completions",
            api_key=None,
            model="deepseek-chat",
            optional_params={},
            litellm_params={},
        )

        assert url == "https://api.deepseek.com/chat/completions"
