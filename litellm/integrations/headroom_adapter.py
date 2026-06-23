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

import time
from typing import Any, Optional

import tiktoken

from litellm.integrations.custom_logger import CustomLogger
from litellm.types.llms.openai import ChatCompletionRequest as _ChatCompletionRequest

try:
    from headroom.integrations.litellm_callback import HeadroomCallback  # type: ignore
except ImportError:
    HeadroomCallback = None  # type: ignore[assignment,misc]

try:
    from headroom.observability import (  # noqa: F401  # used below  # type: ignore[import-untyped]
        OTelMetricsConfig,
        configure_otel_metrics,
    )
except ImportError:
    configure_otel_metrics = None  # type: ignore[assignment,misc]
    OTelMetricsConfig = None  # type: ignore[assignment,misc]

# ── OTEL SDK 1.28+ compatibility fix ──────────────────────────────────────────
# headroom-ai creates Gauge metrics with start_time_unix_nano=None, but the OTEL
# HTTP exporter's encode_metrics() calls .to_bytes() on it, crashing with:
#   EncodingException: 'NoneType' object has no attribute 'to_bytes'
# Monkey-patch the _encode_data_point() to coerce None → time_unix_nano.
try:
    import opentelemetry.exporter.otlp.proto.common._internal.metrics_encoder as _otel_metrics_mod  # type: ignore
    from opentelemetry.exporter.otlp.proto.common._internal.metrics_encoder import (
        _encode_data_point as _orig_encode_data_point,
    )  # type: ignore

    def _patched_encode_data_point(dp: Any) -> Any:
        if getattr(dp, "start_time_unix_nano", None) is None:
            if getattr(dp, "time_unix_nano", None) is not None:
                dp.start_time_unix_nano = dp.time_unix_nano
        return _orig_encode_data_point(dp)  # type: ignore

    # Replace in module namespace so callers see the patched version
    _otel_metrics_mod._encode_data_point = _patched_encode_data_point  # type: ignore

except (ImportError, AttributeError):
    # OTEL SDK not installed or incompatible version — no patch needed
    pass  # noqa: PIE790


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

        # Initialize Headroom OTEL metrics with graceful fallback
        if configure_otel_metrics is not None and OTelMetricsConfig is not None:
            try:
                self._otel_metrics = configure_otel_metrics(  # type: ignore[misc]
                    OTelMetricsConfig.from_env()  # type: ignore[arg-type]
                )
            except Exception:
                self._otel_metrics = None
        else:
            self._otel_metrics = None

    @property
    def total_tokens_saved(self) -> int:
        """Total tokens saved across all compressions."""
        return self._headroom_cb.total_tokens_saved

    @property
    def cloud_mode(self) -> bool:
        """Whether cloud compression is enabled."""
        return self._headroom_cb.cloud_mode

    @staticmethod
    def _count_tokens(messages: list, model_name: str) -> int:
        """Count tokens in messages using tiktoken.

        Returns 0 if messages is empty, or if tiktoken fails to encode.
        """
        if not messages:
            return 0
        try:
            try:
                enc = tiktoken.encoding_for_model(model_name)
            except (KeyError, ValueError):
                enc = tiktoken.encoding_for_model("gpt-3.5-turbo")  # fallback

            total = 0
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str):
                    total += len(enc.encode(content))
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            total += len(enc.encode(part["text"]))
            return total
        except Exception:
            # Token counting failure should not block compression
            return 0

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

        # Extract model and messages for metrics
        model = data.get("model", "")
        messages = data.get("messages", [])

        # Count tokens before compression
        tokens_before = self._count_tokens(messages, model) if isinstance(messages, list) else 0

        # Measure compression duration
        start_time = time.monotonic()

        # Delegate to the real HeadroomCallback
        result = await self._headroom_cb.async_pre_call_hook(
            user_api_key=user_api_key,
            data=data,
            call_type=call_type,
        )
        end_time = time.monotonic()
        duration_ms = int((end_time - start_time) * 1000)

        # Count tokens after compression (from result)
        tokens_after = 0
        if result is not None:
            result_messages = result.get("messages", [])
            if isinstance(result_messages, list):
                tokens_after = self._count_tokens(result_messages, model)

        # Record OTEL metrics (failure must not block compression)
        if self._otel_metrics is not None:
            try:
                self._otel_metrics.record_pipeline_run(
                    model=model,
                    provider="local" if not self.cloud_mode else "cloud",
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    duration_ms=duration_ms,
                )
            except Exception:
                # Metrics failure should not block compression
                pass

        return result
