"""
Regression tests for the pass-through endpoint auth-default fix
(GHSA-7h34-mmrh-6g58).

Two failures the fix closes:

1. ``PassThroughGenericEndpoint.auth`` defaulted to ``False`` — an
   admin who added a pass-through to ``general_settings`` without
   explicitly setting ``auth: true`` shipped an unauthenticated
   forwarder.
2. Setting ``auth: true`` was rejected at startup unless the operator
   had a LiteLLM Enterprise license, leaving OSS deployments with no
   safe configuration.

The fix flips the default to ``True`` (safe-by-default) and removes
the enterprise gate so OSS operators can register an authenticated
pass-through. The runtime check in ``user_api_key_auth.py`` also now
defaults to ``True`` so a config dict (raw, not Pydantic) without an
``auth`` key still requires authentication.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath("../../../.."))

from litellm.proxy._types import PassThroughGenericEndpoint
from litellm.proxy.auth.user_api_key_auth import (
    check_api_key_for_custom_headers_or_pass_through_endpoints,
)
from litellm.proxy.pass_through_endpoints.pass_through_endpoints import (
    _register_pass_through_endpoint,
)


def test_passthrough_auth_defaults_to_true():
    # Regression: an admin who configures a pass-through without setting
    # auth explicitly used to ship an unauthenticated forwarder. The
    # default is now safe.
    endpoint = PassThroughGenericEndpoint(
        path="/canary-forwarder",
        target="https://postman-echo.com/get",
    )
    assert endpoint.auth is True


def test_passthrough_auth_can_still_be_explicitly_disabled():
    # Operators who genuinely need an unauthenticated forwarder (e.g.
    # public webhook receiver) can opt in explicitly.
    endpoint = PassThroughGenericEndpoint(
        path="/public-webhook",
        target="https://example.com/webhook",
        auth=False,
    )
    assert endpoint.auth is False


@pytest.mark.asyncio
async def test_register_passthrough_with_auth_true_works_for_oss(monkeypatch):
    # Regression: setting ``auth: true`` used to raise at startup
    # unless ``premium_user`` was True, leaving OSS with no safe
    # configuration.
    app = MagicMock(spec=FastAPI)
    visited: set = set()

    endpoint = PassThroughGenericEndpoint(
        path="/forwarder",
        target="https://example.com",
        auth=True,
    )

    # Should not raise; OSS premium_user=False is allowed to use auth=True.
    await _register_pass_through_endpoint(
        endpoint=endpoint,
        app=app,
        premium_user=False,
        visited_endpoints=visited,
    )


@pytest.mark.asyncio
async def test_runtime_check_treats_missing_auth_key_as_authenticated():
    # The runtime dispatch in user_api_key_auth pulls
    # pass_through_endpoints from general_settings as raw dicts (the
    # Pydantic default never applies). A dict without an ``auth`` key
    # must default to "authenticated" — without this, the previous
    # behaviour (``endpoint.get("auth") is not True`` -> True -> empty
    # auth) ships an unauthenticated forwarder.
    request = MagicMock()
    request.headers = {}
    raw_endpoint_no_auth_key = {
        "path": "/forwarder",
        "target": "https://example.com",
        # ``auth`` deliberately omitted
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/forwarder",
        pass_through_endpoints=[raw_endpoint_no_auth_key],
        api_key="sk-1234",
    )

    # Result is the api_key string (auth is REQUIRED for this endpoint
    # — flow continues to normal key validation), NOT an empty
    # ``UserAPIKeyAuth()`` (which was the unauthenticated-forwarder
    # bug).
    assert result == "sk-1234"


@pytest.mark.asyncio
async def test_runtime_check_explicit_auth_false_still_skips_validation():
    # Operators who explicitly set ``auth: False`` get the legacy
    # behaviour — an empty UserAPIKeyAuth, no key required.
    from litellm.proxy._types import UserAPIKeyAuth

    request = MagicMock()
    request.headers = {}
    raw_endpoint_auth_false = {
        "path": "/public-webhook",
        "target": "https://example.com",
        "auth": False,
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/public-webhook",
        pass_through_endpoints=[raw_endpoint_auth_false],
        api_key="",
    )

    assert isinstance(result, UserAPIKeyAuth)


# ---------------------------------------------------------------------------
# Subpath-aware auth bypass regression tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subpath_route_triggers_auth_bypass_when_include_subpath_true():
    """Subpath match with include_subpath=True should bypass auth.

    Configured path="/codex/v1", include_subpath=True, auth=False.
    Route "/codex/v1/responses" is a subpath → should return UserAPIKeyAuth().

    This test FAILS against current code (exact match only).
    """
    from litellm.proxy._types import UserAPIKeyAuth

    request = MagicMock()
    request.headers = {}
    raw_endpoint = {
        "path": "/codex/v1",
        "target": "https://example.com",
        "auth": False,
        "include_subpath": True,
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/codex/v1/responses",
        pass_through_endpoints=[raw_endpoint],
        api_key="",
    )

    assert isinstance(result, UserAPIKeyAuth)


@pytest.mark.asyncio
async def test_deep_subpath_route_triggers_auth_bypass():
    """Deep subpath match with include_subpath=True should bypass auth.

    Configured path="/codex/v1", include_subpath=True, auth=False.
    Route "/codex/v1/chat/completions" is a deep subpath → should return UserAPIKeyAuth().

    This test FAILS against current code (exact match only).
    """
    from litellm.proxy._types import UserAPIKeyAuth

    request = MagicMock()
    request.headers = {}
    raw_endpoint = {
        "path": "/codex/v1",
        "target": "https://example.com",
        "auth": False,
        "include_subpath": True,
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/codex/v1/chat/completions",
        pass_through_endpoints=[raw_endpoint],
        api_key="",
    )

    assert isinstance(result, UserAPIKeyAuth)


@pytest.mark.asyncio
async def test_exact_match_still_triggers_auth_bypass():
    """Exact match with auth=False should bypass auth (backward compat).

    Configured path="/codex/v1", auth=False.
    Route "/codex/v1" is an exact match → should return UserAPIKeyAuth().

    This test should PASS against current code (exact match already works).
    """
    from litellm.proxy._types import UserAPIKeyAuth

    request = MagicMock()
    request.headers = {}
    raw_endpoint = {
        "path": "/codex/v1",
        "target": "https://example.com",
        "auth": False,
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/codex/v1",
        pass_through_endpoints=[raw_endpoint],
        api_key="",
    )

    assert isinstance(result, UserAPIKeyAuth)


@pytest.mark.asyncio
async def test_non_matching_route_does_not_bypass():
    """Non-matching route should NOT bypass auth.

    Configured path="/codex/v1", auth=False.
    Route "/v1/responses" does not match → should return api_key string.

    This test should PASS against current code (non-matching already fails).
    """
    request = MagicMock()
    request.headers = {}
    raw_endpoint = {
        "path": "/codex/v1",
        "target": "https://example.com",
        "auth": False,
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/v1/responses",
        pass_through_endpoints=[raw_endpoint],
        api_key="sk-1234",
    )

    assert result == "sk-1234"


@pytest.mark.asyncio
async def test_without_include_subpath_subpath_does_not_bypass():
    """Subpath without include_subpath should NOT bypass auth (exact match only).

    Configured path="/codex/v1", auth=False, NO include_subpath key.
    Route "/codex/v1/responses" is a subpath but include_subpath defaults to False
    → should return api_key string (exact match only).

    This test FAILS against current code because /codex/v1 != /codex/v1/responses,
    so it actually returns the api_key — but the test documents the expected
    behavior: subpaths should NOT bypass unless include_subpath=True.
    """
    request = MagicMock()
    request.headers = {}
    raw_endpoint = {
        "path": "/codex/v1",
        "target": "https://example.com",
        "auth": False,
        # include_subpath deliberately omitted — defaults to False
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/codex/v1/responses",
        pass_through_endpoints=[raw_endpoint],
        api_key="sk-1234",
    )

    assert result == "sk-1234"


@pytest.mark.asyncio
async def test_prefix_collision_does_not_bypass():
    """Prefix collision should NOT bypass auth (trailing / boundary required).

    Configured path="/codex", include_subpath=True, auth=False.
    Route "/codexy/v1/responses" starts with "/codex" but NOT with
    "/codex/" — the trailing slash boundary prevents the collision.
    Should return api_key string.

    This test verifies the boundary condition: without the trailing "/"
    in startswith, a naive "startswith('/codex')" would match
    "/codexy/v1/responses" — a false positive prefix collision.
    """
    request = MagicMock()
    request.headers = {}
    raw_endpoint = {
        "path": "/codex",
        "target": "https://example.com",
        "auth": False,
        "include_subpath": True,
    }

    result = await check_api_key_for_custom_headers_or_pass_through_endpoints(
        request=request,
        route="/codexy/v1/responses",
        pass_through_endpoints=[raw_endpoint],
        api_key="sk-1234",
    )

    assert result == "sk-1234"
