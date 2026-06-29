"""Integration tests for Headroom ASGI middleware end-to-end flow.

Tests the full request flow through the middleware stack — from request entry,
through compression, to response headers — using a minimal FastAPI app that
mimics the proxy middleware stack with mocked headroom compression.

These tests verify integration-level scenarios:
1. Full request/response cycle with compression headers
2. Middleware disabled — no headers injected
3. Health endpoint passthrough (non-LLM path)
4. Non-LLM POST passthrough
5. Streaming endpoint — request compressed, response unmodified
"""

import importlib
import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, StreamingResponse
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

    The middleware imports via 'from headroom.compress import compress',
    so we patch the module-level function directly.
    """

    def fake_compress(messages, model, model_limit, hooks):
        return MockCompressionResult()

    compress_mod = importlib.import_module("headroom.compress")
    with patch.object(compress_mod, "compress", fake_compress):
        yield fake_compress


@pytest.fixture
def app_with_middleware(mock_compress):
    """FastAPI app with CompressionMiddleware attached — simulates enabled middleware."""
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        # Verify the messages were actually compressed by the middleware
        assert body["messages"] == [{"role": "user", "content": "compressed"}]
        return {"id": "chatcmpl-123", "object": "chat.completion"}

    @app.get("/health/liveliness")
    async def health():
        return {"status": "ok"}

    @app.post("/some/other/path")
    async def other_path():
        return {"status": "received"}

    app.add_middleware(CompressionMiddleware, min_tokens=500, model_limit=200000)
    return app


@pytest.fixture
def app_without_middleware():
    """FastAPI app without CompressionMiddleware — simulates disabled middleware."""
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        return {"id": "chatcmpl-123", "object": "chat.completion", "input_messages": body.get("messages")}

    @app.get("/health/liveliness")
    async def health():
        return {"status": "ok"}

    @app.post("/some/other/path")
    async def other_path():
        return {"status": "received"}

    return app


@pytest.fixture
def streaming_app_with_middleware(mock_compress):
    """FastAPI app with CompressionMiddleware and a streaming endpoint."""
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions_streaming(request: Request):
        body = await request.json()
        # Verify the messages were actually compressed by the middleware
        assert body["messages"] == [{"role": "user", "content": "compressed"}]
        # Return a streaming response (SSE-like)
        async def event_generator():
            yield "data: {\"id\": \"chatcmpl-123\", \"object\": \"chat.completion.chunk\", \"choices\": []}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    app.add_middleware(CompressionMiddleware, min_tokens=500, model_limit=200000)
    return app


# ─── Integration Tests ────────────────────────────────────────────────────

class TestChatCompletionsCompressedWithHeaders:
    """POST /v1/chat/completions with middleware enabled returns compression headers."""

    def test_chat_completions_compressed_with_headers(self, app_with_middleware):
        """Full request flow: request compressed, response has x-headroom-* headers."""
        client = TestClient(app_with_middleware)

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "This is a very long message that should be compressed"}
            ],
        }

        response = client.post("/v1/chat/completions", json=payload)

        # Response is successful
        assert response.status_code == 200
        assert response.json()["id"] == "chatcmpl-123"

        # Compression headers are present
        assert response.headers["x-headroom-compressed"] == "true"
        assert response.headers["x-headroom-tokens-saved"] == "400"
        assert response.headers["x-headroom-tokens-before"] == "1000"
        assert response.headers["x-headroom-tokens-after"] == "600"

    def test_chat_completions_body_was_compressed(self, app_with_middleware):
        """The endpoint handler receives the compressed body (middleware modified the request)."""
        client = TestClient(app_with_middleware)

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Original long content"}
            ],
        }

        # This passes because the handler asserts body["messages"] == compressed value
        response = client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200

    def test_chat_completions_anthropic_endpoint_compressed(self, app_with_middleware):
        """Anthropic /v1/messages endpoint also gets compression headers."""
        # Add Anthropic endpoint to the app
        @app_with_middleware.post("/v1/messages")
        async def anthropic_messages(request: Request):
            body = await request.json()
            assert body["messages"] == [{"role": "user", "content": "compressed"}]
            return {"id": "msg_123", "type": "message"}

        client = TestClient(app_with_middleware)

        payload = {
            "model": "claude-sonnet-4-5-20250929",
            "messages": [
                {"role": "user", "content": "Anthropic message to compress"}
            ],
        }

        response = client.post("/v1/messages", json=payload)

        assert response.status_code == 200
        assert response.headers["x-headroom-compressed"] == "true"
        assert response.headers["x-headroom-tokens-saved"] == "400"


class TestChatCompletionsNotCompressedWhenDisabled:
    """POST /v1/chat/completions without middleware returns NO x-headroom-* headers."""

    def test_chat_completions_not_compressed_when_disabled(self, app_without_middleware):
        """No middleware → no x-headroom-* headers in response."""
        client = TestClient(app_without_middleware)

        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "This message should NOT be compressed"}
            ],
        }

        response = client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200
        assert response.json()["id"] == "chatcmpl-123"

        # No compression headers
        assert "x-headroom-compressed" not in response.headers
        assert "x-headroom-tokens-before" not in response.headers
        assert "x-headroom-tokens-after" not in response.headers
        assert "x-headroom-tokens-saved" not in response.headers

    def test_chat_completions_body_not_modified_when_disabled(self, app_without_middleware):
        """Without middleware, the original messages reach the handler unchanged."""
        client = TestClient(app_without_middleware)

        original_messages = [{"role": "user", "content": "Original content"}]
        payload = {
            "model": "gpt-4",
            "messages": original_messages,
        }

        response = client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200
        # The handler echoes back the input messages — they should be original
        assert response.json()["input_messages"] == original_messages


class TestHealthEndpointPassthrough:
    """GET /health/liveliness passes through unchanged with no compression headers."""

    def test_health_endpoint_passthrough(self, app_with_middleware):
        """Health endpoint returns 200 with no x-headroom-* headers."""
        client = TestClient(app_with_middleware)

        response = client.get("/health/liveliness")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        # No compression headers on health endpoint
        assert "x-headroom-compressed" not in response.headers
        assert "x-headroom-tokens-before" not in response.headers
        assert "x-headroom-tokens-after" not in response.headers
        assert "x-headroom-tokens-saved" not in response.headers

    def test_health_endpoint_without_middleware(self, app_without_middleware):
        """Health endpoint works identically without middleware."""
        client = TestClient(app_without_middleware)

        response = client.get("/health/liveliness")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "x-headroom-compressed" not in response.headers


class TestNonLLMPostPassthrough:
    """POST to a non-LLM path passes through unchanged with no compression headers."""

    def test_non_llm_post_passthrough_with_middleware(self, app_with_middleware):
        """POST /some/other/path passes through unchanged with middleware present."""
        client = TestClient(app_with_middleware)

        payload = {"data": "some data"}

        response = client.post("/some/other/path", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "received"}

        # No compression headers on non-LLM path
        assert "x-headroom-compressed" not in response.headers
        assert "x-headroom-tokens-before" not in response.headers

    def test_non_llm_post_passthrough_without_middleware(self, app_without_middleware):
        """POST /some/other/path works identically without middleware."""
        client = TestClient(app_without_middleware)

        payload = {"data": "some data"}

        response = client.post("/some/other/path", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "received"}
        assert "x-headroom-compressed" not in response.headers

    def test_get_to_llm_path_passthrough(self, app_with_middleware):
        """GET to an LLM path is not intercepted (only POST is)."""
        client = TestClient(app_with_middleware)

        response = client.get("/v1/chat/completions")

        # 405 Method Not Allowed (expected — no GET handler)
        assert response.status_code == 405
        # Even on error, no compression headers
        assert "x-headroom-compressed" not in response.headers


class TestStreamingEndpointCompressed:
    """POST /v1/chat/completions?stream=true — request compressed, response headers present."""

    def test_streaming_endpoint_compressed(self, streaming_app_with_middleware):
        """Streaming endpoint: request is compressed, response has compression headers."""
        client = TestClient(streaming_app_with_middleware)

        payload = {
            "model": "gpt-4",
            "stream": True,
            "messages": [
                {"role": "user", "content": "A very long streaming request message"}
            ],
        }

        with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            # Response is successful
            assert response.status_code == 200

            # Compression headers are present (on response start)
            assert response.headers["x-headroom-compressed"] == "true"
            assert response.headers["x-headroom-tokens-saved"] == "400"
            assert response.headers["x-headroom-tokens-before"] == "1000"
            assert response.headers["x-headroom-tokens-after"] == "600"

            # Media type is event stream
            assert "text/event-stream" in response.headers.get("content-type", "")

            # Read the streaming content
            content = b""
            for chunk in response.iter_bytes():
                content += chunk

            # Verify streaming content is present
            assert b'"id": "chatcmpl-123"' in content
            assert b"[DONE]" in content

    def test_streaming_endpoint_body_was_compressed(self, streaming_app_with_middleware):
        """Streaming endpoint handler receives the compressed request body."""
        client = TestClient(streaming_app_with_middleware)

        payload = {
            "model": "gpt-4",
            "stream": True,
            "messages": [
                {"role": "user", "content": "Original streaming content"}
            ],
        }

        # Handler asserts body["messages"] == compressed value — passes if compressed
        response = client.post("/v1/chat/completions", json=payload)

        assert response.status_code == 200
        assert response.headers["x-headroom-compressed"] == "true"

    def test_streaming_endpoint_without_middleware(self, app_without_middleware):
        """Streaming without middleware: no compression headers, original body."""
        # Add streaming endpoint to app_without_middleware
        @app_without_middleware.post("/v1/chat/completions/stream")
        async def chat_stream_no_middleware(request: Request):
            body = await request.json()
            # Body should be original (not compressed)
            assert body["messages"] == [{"role": "user", "content": "Original content"}]
            async def event_generator():
                yield "data: {\"id\": \"chatcmpl-123\"}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(event_generator(), media_type="text/event-stream")

        client = TestClient(app_without_middleware)

        payload = {
            "model": "gpt-4",
            "stream": True,
            "messages": [
                {"role": "user", "content": "Original content"}
            ],
        }

        response = client.post("/v1/chat/completions/stream", json=payload)

        assert response.status_code == 200
        # No compression headers without middleware
        assert "x-headroom-compressed" not in response.headers
