"""Adapter that wraps headroom-ai's HeadroomCallback into LiteLLM's CustomLogger interface.

The original HeadroomCallback inherits from object, not CustomLogger, so the proxy's
_callback_capabilities() skips it entirely (isinstance check on CustomLogger).
This adapter bridges the gap by:
  1. Inheriting from CustomLogger
  2. Wrapping the real HeadroomCallback
  3. Adapting async_pre_call_hook from CustomLogger's 4-param signature to
     HeadroomCallback's 3-param signature
"""

from __future__ import annotations

from typing import Any, Optional

from litellm.integrations.custom_logger import CustomLogger
from litellm.types.llms.openai import ChatCompletionRequest as _ChatCompletionRequest

try:
    from headroom.integrations.litellm_callback import HeadroomCallback  # type: ignore
except ImportError:
    HeadroomCallback = None  # type: ignore[assignment,misc]


class HeadroomCallbackAdapter(CustomLogger):
    """Wraps HeadroomCallback for LiteLLM proxy compatibility.

    The proxy only calls hooks on CustomLogger subclasses. The original
    HeadroomCallback inherits from object, so it gets silently skipped.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        if HeadroomCallback is None:
            raise ImportError(
                "headroom-ai is required for HeadroomCallbackAdapter. "
                "Install it: pip install headroom-ai"
            )
        self._headroom_cb = HeadroomCallback(*args, **kwargs)  # type: ignore[misc]

    @property
    def total_tokens_saved(self) -> int:
        """Total tokens saved across all compressions."""
        return self._headroom_cb.total_tokens_saved

    @property
    def cloud_mode(self) -> bool:
        """Whether cloud compression is enabled."""
        return self._headroom_cb.cloud_mode

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict,
        call_type: str,
    ) -> Optional[dict]:
        """Adapt CustomLogger's pre_call_hook to HeadroomCallback's signature.

        CustomLogger passes: user_api_key_dict, cache, data, call_type
        HeadroomCallback expects: user_api_key, data, call_type

        We extract the API key string from user_api_key_dict (or use a fallback)
        and skip the cache parameter (HeadroomCallback doesn't use it).
        """
        # Extract API key string from the dict (LiteLLM uses dict for auth)
        user_api_key: str = ""
        if user_api_key_dict is not None:
            if isinstance(user_api_key_dict, dict):
                user_api_key = user_api_key_dict.get("token", "")
            elif hasattr(user_api_key_dict, "token"):
                user_api_key = getattr(user_api_key_dict, "token", "")

        # Delegate to the real HeadroomCallback
        result = await self._headroom_cb.async_pre_call_hook(
            user_api_key=user_api_key,
            data=data,
            call_type=call_type,
        )
        return result
