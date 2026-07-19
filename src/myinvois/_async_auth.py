"""Async OAuth2 authentication for the MyInvois API.

Mirrors :class:`~myinvois.auth.TokenManager` but uses
:class:`httpx.AsyncClient` for the token acquisition call.

Token caching and refresh-ahead logic are identical to the sync version; only
the I/O (``_acquire``) is async.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx

from myinvois.auth import (
    DEFAULT_REFRESH_MARGIN,
    OAuth2Token,
    StoredToken,
)
from myinvois.exceptions import AuthenticationError, MyInvoisError

if TYPE_CHECKING:
    pass

__all__ = ["AsyncTokenManager"]


class AsyncTokenManager:
    """Acquires and caches OAuth2 ``client_credentials`` tokens asynchronously.

    Uses an injectable ``httpx.AsyncClient`` so tests can mock the transport
    via ``respx``.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: str = "InvoicingAPI",
        client: httpx.AsyncClient | None = None,
        refresh_margin: int = DEFAULT_REFRESH_MARGIN,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope
        self._http = client if client is not None else httpx.AsyncClient(timeout=30.0)
        self._refresh_margin = refresh_margin
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._stored = StoredToken(None)

    @property
    def is_valid(self) -> bool:
        tok = self._stored.value
        if tok is None:
            return False
        return not tok.is_expired(now=self._clock(), refresh_margin=self._refresh_margin)

    @property
    def access_token(self) -> str | None:
        tok = self._stored.value
        return tok.access_token if tok is not None else None

    @property
    def token(self) -> OAuth2Token | None:
        return self._stored.value

    async def get_token(self, *, headers: dict[str, str] | None = None) -> OAuth2Token:
        tok = self._stored.value
        if tok is not None and not tok.is_expired(
            now=self._clock(), refresh_margin=self._refresh_margin
        ):
            return tok
        return await self._acquire(headers=headers)

    def invalidate(self) -> None:
        """Drop the cached token."""
        self._stored.value = None

    def _build_form(self) -> dict[str, str]:
        return {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
            "scope": self._scope,
        }

    async def _acquire(self, *, headers: dict[str, str] | None = None) -> OAuth2Token:
        try:
            response = await self._http.post(
                self._token_url, data=self._build_form(), headers=headers
            )
        except httpx.HTTPError as exc:
            raise MyInvoisError(
                f"Failed to reach MyInvois token endpoint: {exc!r}",
            ) from exc

        if response.status_code in (401, 403):
            raise AuthenticationError(
                "MyInvois rejected client credentials",
                status_code=response.status_code,
            ) from None
        if response.status_code >= 400:
            raise MyInvoisError(
                f"MyInvois token endpoint returned {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MyInvoisError(
                "MyInvois token endpoint returned non-JSON",
                status_code=response.status_code,
            ) from exc

        tok = OAuth2Token.from_response(payload, fetched_at=self._clock())
        self._stored.value = tok
        return tok
