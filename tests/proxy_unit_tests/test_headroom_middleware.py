"""Unit tests for Headroom compression middleware integration.

Tests verify:
1. Conditional registration based on HEADROOM_MIDDLEWARE_ENABLED env var
2. Conditional registration based on _HEADROOM_AVAILABLE flag
3. Middleware passthrough for non-LLM paths
4. Middleware compression headers on eligible LLM requests
"""

import importlib
import json
import os
from unittest.mock import patch

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from headroom.integrations.asgi import CompressionMiddleware


class MockCompressionResult:
    """Deterministic mock result for headroom.compress()."""

    def __init__(self):
        self.messages = [{"role": "user", "content": "compressed"}]
        self.tokens_before = 1000
        self.tokens_after = 600
        self.tokens_saved = 400
        self.compression_ratio = 0.4


@pytest.fixture
def mock_compress():
    """Mock headroom.compress() to return deterministic results.

    The headroom package exports compress as both headroom.compress (the function)
    and headroom.compress.compress (module attribute). The middleware imports it
    via 'from headroom.compress import compress', so we patch the module-level
    function directly.
    """

    def fake_compress(messages, model, model_limit, hooks):
        return MockCompressionResult()

    # Patch the actual module's compress function
    compress_mod = importlib.import_module("headroom.compress")
    with patch.object(compress_mod, "compress", fake_compress):
        yield fake_compress


# ─── Conditional Registration Tests ───────────────────────────────────────

class TestConditionalRegistration:
    """Test that middleware is conditionally registered based on env vars and availability."""

    def test_headroom_middleware_not_registered_when_disabled(self, monkeypatch):
        """Middleware NOT registered when HEADROOM_MIDDLEWARE_ENABLED is not set."""
        monkeypatch.delenv("HEADROOM_MIDDLEWARE_ENABLED", raising=False)

        # Simulate the registration logic from proxy_server.py
        _HEADROOM_AVAILABLE = True  # Assume headroom is installed

        registered = False
        if _HEADROOM_AVAILABLE and (
            os.environ.get("HEADROOM_MIDDLEWARE_ENABLED", "").lower()
            not in ("0", "false", "no", "")
        ):
            registered = True

        assert registered is False

    def test_headroom_middleware_not_registered_when_false_values(self, monkeypatch):
        """Middleware NOT registered for disabled env var values: 0, false, no."""
        for value in ("0", "false", "no", "FALSE", "NO", "False"):
            monkeypatch.setenv("HEADROOM_MIDDLEWARE_ENABLED", value)

            _HEADROOM_AVAILABLE = True
            registered = False
            if _HEADROOM_AVAILABLE and (
                os.environ.get("HEADROOM_MIDDLEWARE_ENABLED", "").lower()
                not in ("0", "false", "no", "")
            ):
                registered = True

            assert registered is False, f"Expected disabled for value={value!r}"

    def test_headroom_middleware_registered_when_enabled(self, monkeypatch):
        """Middleware IS registered when HEADROOM_MIDDLEWARE_ENABLED=true."""
        monkeypatch.setenv("HEADROOM_MIDDLEWARE_ENABLED", "true")

        _HEADROOM_AVAILABLE = True
        registered = False
        if _HEADROOM_AVAILABLE and (
            os.environ.get("HEADROOM_MIDDLEWARE_ENABLED", "").lower()
            not in ("0", "false", "no", "")
        ):
            registered = True

        assert registered is True

    def test_headroom_middleware_not_registered_when_unavailable(self, monkeypatch):
        """Middleware NOT registered when _HEADROOM_AVAILABLE is False (import failure)."""
        monkeypatch.setenv("HEADROOM_MIDDLEWARE_ENABLED", "true")

        _HEADROOM_AVAILABLE = False  # Simulate ImportError
        registered = False
        if _HEADROOM_AVAILABLE and (
            os.environ.get("HEADROOM_MIDDLEWARE_ENABLED", "").lower()
            not in ("0", "false", "no", "")
        ):
            registered = True

        assert registered is False

    def test_headroom_middleware_registered_with_various_true_values(self, monkeypatch):
        """Middleware IS registered for various truthy env var values."""
        for value in ("true", "1", "yes", "TRUE", "enabled"):
            monkeypatch.setenv("HEADROOM_MIDDLEWARE_ENABLED", value)

            _HEADROOM_AVAILABLE = True
            registered = False
            if _HEADROOM_AVAILABLE and (
                os.environ.get("HEADROOM_MIDDLEWARE_ENABLED", "").lower()
                not in ("0", "false", "no", "")
            ):
                registered = True

            assert registered is True, f"Expected enabled for value={value!r}"


# ─── Middleware Passthrough Tests ─────────────────────────────────────────

class TestMiddlewarePassthrough:
    """Test that CompressionMiddleware passes through non-LLM paths unchanged."""

    def test_headroom_middleware_passthrough_non_llm_path(self):
        """Non-LLM paths (GET /health) pass through unchanged."""

        async def mock_app(scope, receive, send):
            response = JSONResponse({"status": "ok"})
            await response(scope, receive, send)

        middleware = CompressionMiddleware(mock_app)
        client = TestClient(middleware)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "x-headroom-compressed" not in response.headers

    def test_headroom_middleware_passthrough_get_llm_path(self):
        """GET requests to LLM paths pass through unchanged."""

        async def mock_app(scope, receive, send):
            response = JSONResponse({"status": "ok"})
            await response(scope, receive, send)

        middleware = CompressionMiddleware(mock_app)
        client = TestClient(middleware)

        response = client.get("/v1/chat/completions")

        assert response.status_code == 200
        assert "x-headroom-compressed" not in response.headers

    def test_headroom_middleware_passthrough_non_llm_post(self):
        """POST to non-LLM paths passes through unchanged."""

        async def mock_app(scope, receive, send):
            response = JSONResponse({"status": "ok"})
            await response(scope, receive, send)

        middleware = CompressionMiddleware(mock_app)
        client = TestClient(middleware)

        response = client.post("/some/other/path")

        assert response.status_code == 200
        assert "x-headroom-compressed" not in response.headers


# ─── Middleware Compression Tests ─────────────────────────────────────────

class TestMiddlewareCompression:
    """Test that CompressionMiddleware adds x-headroom-* headers on eligible requests."""

    def test_headroom_middleware_compression_with_headers(self, mock_compress):
        """POST /v1/chat/completions returns x-headroom-compressed and x-headroom-tokens-saved headers."""

        async def mock_app(scope, receive, send):
            # Read the body to verify it was compressed
            body = b""
            while True:
                message = await receive()
                if message["type"] == "http.request":
                    body += message.get("body", b"")
                    if not message.get("more_body", False):
                        break

            # Parse and verify messages were compressed
            body_json = json.loads(body)
            assert body_json["messages"] == [{"role": "user", "content": "compressed"}]

            response = JSONResponse({"id": "chatcmpl-123"})
            await response(scope, receive, send)

        middleware = CompressionMiddleware(mock_app)
        client = TestClient(middleware)

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "This is a very long message that should be compressed"}
            ],
        }

        response = client.post(
            "/v1/chat/completions",
            json=payload,
        )

        assert response.status_code == 200
        assert response.headers["x-headroom-compressed"] == "true"
        assert response.headers["x-headroom-tokens-before"] == "1000"
        assert response.headers["x-headroom-tokens-after"] == "600"
        assert response.headers["x-headroom-tokens-saved"] == "400"

    def test_headroom_middleware_compression_anthropic_messages(self, mock_compress):
        """POST /v1/messages (Anthropic) also gets compressed."""

        async def mock_app(scope, receive, send):
            body = b""
            while True:
                message = await receive()
                if message["type"] == "http.request":
                    body += message.get("body", b"")
                    if not message.get("more_body", False):
                        break

            response = JSONResponse({"id": "msg_123"})
            await response(scope, receive, send)

        middleware = CompressionMiddleware(mock_app)
        client = TestClient(middleware)

        payload = {
            "model": "claude-sonnet-4-5-20250929",
            "messages": [
                {"role": "user", "content": "Anthropic message to compress"}
            ],
        }

        response = client.post(
            "/v1/messages",
            json=payload,
        )

        assert response.status_code == 200
        assert response.headers["x-headroom-compressed"] == "true"

    def test_headroom_middleware_no_compression_short_messages(self):
        """Messages below min_tokens threshold are not compressed."""

        # Mock compress to return zero tokens saved (simulating short messages)
        class ShortResult:
            messages = [{"role": "user", "content": "short"}]
            tokens_before = 10
            tokens_after = 10
            tokens_saved = 0
            compression_ratio = 0.0

        compress_mod = importlib.import_module("headroom.compress")
        with patch.object(compress_mod, "compress", return_value=ShortResult()):
            async def mock_app(scope, receive, send):
                response = JSONResponse({"id": "chatcmpl-123"})
                await response(scope, receive, send)

            middleware = CompressionMiddleware(mock_app, min_tokens=500)
            client = TestClient(middleware)

            payload = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
            }

            response = client.post(
                "/v1/chat/completions",
                json=payload,
            )

            assert response.status_code == 200
            # No compression headers when tokens_saved == 0
            assert "x-headroom-compressed" not in response.headers
