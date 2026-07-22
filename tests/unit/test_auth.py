"""Tests for myinvois.auth — OAuth2 token acquisition + caching.

We mock the HTTP layer entirely; no network. `connect/token` is an
OAuth2 `client_credentials` endpoint. We use the `respx_mock` pytest fixture
so routes are wired into an active router for the duration of each test.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from myinvois.auth import (
    OAuth2Token,
    StoredToken,
    TokenManager,
)
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
def mgr(token_url: str) -> TokenManager:
    return TokenManager(
        client_id="cid", client_secret="csecret", token_url=token_url, scope="InvoicingAPI"
    )


def test_oauth2_token_from_response() -> None:
    tok = OAuth2Token.from_response(_token_response("TOK", expires_in=100), fetched_at=1000.0)
    assert tok.access_token == "TOK"
    assert tok.token_type == "Bearer"
    assert tok.expires_at == 1000.0 + 100


def test_oauth2_token_defaults_scheme_to_bearer() -> None:
    resp = {"access_token": "X", "expires_in": 60}  # no token_type
    assert OAuth2Token.from_response(resp, fetched_at=0.0).token_type == "Bearer"


def test_oauth2_token_rejects_missing_access() -> None:
    with pytest.raises(AuthenticationError):
        OAuth2Token.from_response({"expires_in": 60}, fetched_at=0.0)


def test_token_manager_acquires_token(respx_mock: Any, token_url: str, mgr: TokenManager) -> None:
    route = respx_mock.post(token_url).mock(
        return_value=httpx.Response(200, json=_token_response("TOK-1", expires_in=3600))
    )

    tok = mgr.get_token()

    assert tok.access_token == "TOK-1"
    assert mgr.is_valid is True

    # Pin the outgoing form too. Nothing else asserts the grant payload, so a
    # typo in `_build_form` (e.g. "client_credential") would otherwise pass
    # every test and only fail against the real LHDN token endpoint.
    # Mirrors `test_async_auth.py::test_async_token_manager_acquires_token`.
    sent = parse_qs(route.calls.last.request.content.decode())
    assert sent == {
        "client_id": ["cid"],
        "client_secret": ["csecret"],
        "grant_type": ["client_credentials"],
        "scope": ["InvoicingAPI"],
    }


def test_token_manager_caches_until_expiry(
    respx_mock: Any, token_url: str, mgr: TokenManager
) -> None:
    route = respx_mock.post(token_url).mock(
        return_value=httpx.Response(200, json=_token_response("CACHED", expires_in=3600))
    )

    mgr.get_token()
    mgr.get_token()
    assert route.call_count == 1  # cached — only hit the wire once


def test_token_manager_reacquires_after_expiry(
    respx_mock: Any, token_url: str, mgr: TokenManager
) -> None:
    route = respx_mock.post(token_url).mock(
        side_effect=[
            httpx.Response(200, json=_token_response("OLD", expires_in=1)),
            httpx.Response(200, json=_token_response("NEW", expires_in=3600)),
        ]
    )

    first = mgr.get_token()
    assert first.access_token == "OLD"

    # Force expiry without sleeping.
    StoredToken.expire_now(mgr)

    second = mgr.get_token()
    assert second.access_token == "NEW"
    assert route.call_count == 2


def test_token_manager_refresh_margin(respx_mock: Any, token_url: str, mgr: TokenManager) -> None:
    """A token expiring inside the refresh margin must be re-acquired.

    Asserting only ``is_valid`` would be weak: ``get_token`` does not consult
    that property, it re-checks ``is_expired`` itself. So this drives the real
    path -- a second ``get_token`` must go back to the wire and return the new
    token, not hand back the still-unexpired-but-stale first one.

    Mirrors ``test_async_auth.py::test_async_token_manager_refresh_margin``.
    """
    route = respx_mock.post(token_url).mock(
        side_effect=[
            # expires_in 30 is inside the default 60s refresh margin, so this
            # token counts as stale the moment it arrives.
            httpx.Response(200, json=_token_response("STALE", expires_in=30)),
            httpx.Response(200, json=_token_response("FRESH", expires_in=3600)),
        ]
    )

    assert mgr.get_token().access_token == "STALE"
    assert mgr.is_valid is False

    assert mgr.get_token().access_token == "FRESH"
    assert route.call_count == 2
    assert mgr.is_valid is True


def test_token_manager_raises_on_auth_failure(
    respx_mock: Any, token_url: str, mgr: TokenManager
) -> None:
    respx_mock.post(token_url).mock(
        return_value=httpx.Response(
            401, json={"error": "invalid_client", "error_description": "bad secret"}
        )
    )

    with pytest.raises(AuthenticationError) as ex:
        mgr.get_token()
    assert ex.value.status_code == 401


def test_token_manager_raises_on_server_error(
    respx_mock: Any, token_url: str, mgr: TokenManager
) -> None:
    respx_mock.post(token_url).mock(return_value=httpx.Response(503, text="unavailable"))

    with pytest.raises(MyInvoisError):
        mgr.get_token()


def test_new_token_manager_has_no_token(token_url: str) -> None:
    fresh = TokenManager(
        client_id="cid", client_secret="csecret", token_url=token_url, scope="InvoicingAPI"
    )
    assert fresh.is_valid is False
    assert fresh.access_token is None
    assert fresh.token is None


def test_invalidate_drops_cached_token(respx_mock: Any, token_url: str, mgr: TokenManager) -> None:
    respx_mock.post(token_url).mock(
        return_value=httpx.Response(200, json=_token_response("TOK", expires_in=3600))
    )

    mgr.get_token()
    assert mgr.access_token == "TOK"

    mgr.invalidate()
    assert mgr.access_token is None
    assert mgr.is_valid is False
