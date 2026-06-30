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

try:
    from headroom.observability import (  # noqa: F401  # used below  # type: ignore[import-untyped]
        OTelMetricsConfig,
        configure_otel_metrics,
    )
except ImportError:
    configure_otel_metrics = None  # type: ignore[assignment,misc]
    OTelMetricsConfig = None  # type: ignore[assignment,misc]

# ── OTEL SDK 1.28+ compatibility fix ──────────────────────────────────────────
# Headroom creates observable gauges whose Exemplars have span_id=None and
# trace_id=None (no trace context during metric collection). The OTEL HTTP
# exporter's _encode_exemplars() calls _encode_span_id() which does
# `None.to_bytes(8)`, crashing with:
#   EncodingException: 'NoneType' object has no attribute 'to_bytes'
# Patch _encode_exemplars to sanitize null fields before encoding.
try:
    from dataclasses import replace as _dc_replace  # type: ignore[attr-defined]

    import opentelemetry.exporter.otlp.proto.common._internal.metrics_encoder as _otel_metrics_mod  # type: ignore

    _orig_encode_exemplars = _otel_metrics_mod._encode_exemplars  # type: ignore[attr-defined]

    def _safe_encode_exemplars(sdk_exemplars: list) -> list:  # type: ignore[type-arg]
        safe = []
        for ex in sdk_exemplars:
            span_id = getattr(ex, "span_id", None)
            trace_id = getattr(ex, "trace_id", None)
            if span_id is None or trace_id is None:
                ex = _dc_replace(
                    ex,
                    span_id=0 if span_id is None else span_id,
                    trace_id=0 if trace_id is None else trace_id,
                )
            safe.append(ex)
        return _orig_encode_exemplars(safe)

    _otel_metrics_mod._encode_exemplars = _safe_encode_exemplars  # type: ignore[attr-defined]

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

        # Initialize the global Headroom OTEL metrics singleton (used by the
        # pipeline inside HeadroomCallback).  The adapter itself no longer
        # records metrics — the pipeline's own record_pipeline_run() call
        # (via compress() → pipeline.apply()) produces accurate counts with
        # message overhead, per-stage timing, and transform metadata.
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

        Metrics are recorded by the pipeline inside HeadroomCallback (via
        compress() → pipeline.apply() → record_pipeline_run()), NOT here.
        The adapter only bridges the CustomLogger interface — it does not
        record its own metrics.
        """
        # Extract API key string from the dict (LiteLLM uses dict for auth)
        user_api_key: str = ""
        if user_api_key_dict is not None:
            if isinstance(user_api_key_dict, dict):
                user_api_key = user_api_key_dict.get("token", "")
            elif hasattr(user_api_key_dict, "token"):
                user_api_key = getattr(user_api_key_dict, "token", "")

        return await self._headroom_cb.async_pre_call_hook(
            user_api_key=user_api_key,
            data=data,
            call_type=call_type,
        )
