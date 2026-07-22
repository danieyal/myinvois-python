"""Tests for AsyncTokenManager.

Mirrors the sync tests in test_auth.py. The caching and refresh-ahead logic is
duplicated between TokenManager and AsyncTokenManager rather than shared, so
the sync suite passing says nothing about the async one -- these tests exist to
catch drift between the two implementations.

Covers what the async side previously left untested: cache hits, expiry-driven
re-acquisition, the refresh margin, the asyncio.Lock that collapses concurrent
refreshes, and error mapping at the token endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from myinvois._async_auth import AsyncTokenManager
from myinvois.auth import OAuth2Token
from myinvois.config import Environment, base_identity_url
from myinvois.exceptions import AuthenticationError, MyInvoisError


def _token_response(
    access_token: str = "abc-access",
    expires_in: int = 3600,
    token_type: str = "Bearer",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "access_token": access_token,
        "expires_in": expires_in,
        "token_type": token_type,
        **extra,
    }


@pytest.fixture
def token_url() -> str:
    return base_identity_url(Environment.SANDBOX)


@pytest.fixture
def mgr(token_url: str) -> AsyncTokenManager:
    return AsyncTokenManager(
        client_id="cid", client_secret="csecret", token_url=token_url, scope="InvoicingAPI"
    )


def _expire_now(mgr: AsyncTokenManager) -> None:
    """Force the manager to treat its cached token as expired.

    The sync suite uses ``StoredToken.expire_now``, which is annotated for
    ``TokenManager``; this is the same rewrite against the async manager's
    identically-shaped ``_stored`` slot.
    """
    current = mgr._stored.value
    assert current is not None, "no token cached to expire"
    mgr._stored.value = OAuth2Token(
        access_token=current.access_token,
        token_type=current.token_type,
        expires_at=mgr._clock() - 1,
    )


# ===== caching and refresh =====


async def test_async_token_manager_acquires_token(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    respx_mock.post(token_url).mock(return_value=httpx.Response(200, json=_token_response("FIRST")))

    tok = await mgr.get_token()

    assert tok.access_token == "FIRST"
    assert mgr.access_token == "FIRST"
    assert mgr.is_valid is True


async def test_async_token_manager_caches_until_expiry(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    route = respx_mock.post(token_url).mock(
        return_value=httpx.Response(200, json=_token_response("CACHED", expires_in=3600))
    )

    await mgr.get_token()
    await mgr.get_token()

    assert route.call_count == 1  # cached -- only hit the wire once


async def test_async_token_manager_reacquires_after_expiry(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    route = respx_mock.post(token_url).mock(
        side_effect=[
            httpx.Response(200, json=_token_response("OLD", expires_in=1)),
            httpx.Response(200, json=_token_response("NEW", expires_in=3600)),
        ]
    )

    assert (await mgr.get_token()).access_token == "OLD"
    _expire_now(mgr)  # force expiry without sleeping
    assert (await mgr.get_token()).access_token == "NEW"
    assert route.call_count == 2


async def test_async_token_manager_refresh_margin(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    # expires_in 30 is inside the default 60s refresh margin, so a freshly
    # acquired token must already count as stale.
    respx_mock.post(token_url).mock(
        return_value=httpx.Response(200, json=_token_response("TOK", expires_in=30))
    )

    await mgr.get_token()

    assert mgr.is_valid is False


async def test_async_invalidate_drops_cached_token(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    route = respx_mock.post(token_url).mock(
        return_value=httpx.Response(200, json=_token_response("TOK"))
    )

    await mgr.get_token()
    mgr.invalidate()

    assert mgr.access_token is None
    assert mgr.is_valid is False

    await mgr.get_token()
    assert route.call_count == 2


# ===== concurrency =====


async def test_async_concurrent_get_token_acquires_once(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    """The asyncio.Lock must collapse a concurrent stampede into one request.

    Without the lock (or with a lock but no re-check inside it) every waiter
    would fetch its own token, which is the failure this pins. The handler
    yields to the event loop so the coroutines genuinely interleave rather
    than running to completion one at a time.
    """
    calls = 0

    async def _slow(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)  # force a suspension point mid-acquire
        return httpx.Response(200, json=_token_response("SHARED"))

    respx_mock.post(token_url).mock(side_effect=_slow)

    tokens = await asyncio.gather(*(mgr.get_token() for _ in range(10)))

    assert calls == 1, "concurrent refreshes must collapse into a single request"
    assert {t.access_token for t in tokens} == {"SHARED"}


# ===== error mapping =====


async def test_async_token_manager_raises_on_auth_failure(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    respx_mock.post(token_url).mock(
        return_value=httpx.Response(
            401, json={"error": "invalid_client", "error_description": "bad secret"}
        )
    )

    with pytest.raises(AuthenticationError) as ex:
        await mgr.get_token()
    assert ex.value.status_code == 401


async def test_async_token_manager_raises_on_server_error(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    respx_mock.post(token_url).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(MyInvoisError) as ex:
        await mgr.get_token()
    assert ex.value.status_code == 500


async def test_async_token_manager_raises_on_transport_error(
    respx_mock: Any, token_url: str, mgr: AsyncTokenManager
) -> None:
    respx_mock.post(token_url).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(MyInvoisError, match="Failed to reach MyInvois token endpoint"):
        await mgr.get_token()
