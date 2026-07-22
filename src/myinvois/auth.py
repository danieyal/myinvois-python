"""OAuth2 authentication for the MyInvois API.

The MyInvois system uses an OAuth2 ``client_credentials`` grant against an
IdentityServer4 host. Intermediaries (ERP systems submitting on behalf of a
taxpayer) additionally send an ``onbehalfof: <TIN>`` header — handled in
``client.py``, not here.

This module is responsible only for obtaining and caching bearer tokens:

- `OAuth2Token` — immutable representation of one token plus its expiry.
- `TokenManager` — acquires, refreshes-ahead-of-expiry, and caches tokens.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from myinvois.exceptions import AuthenticationError, MyInvoisError

if TYPE_CHECKING:
    pass

__all__ = ["DEFAULT_REFRESH_MARGIN", "OAuth2Token", "StoredToken", "TokenManager"]

# Re-acquire the token if it expires within this many seconds. 60s mirrors the
# access-token validity window with a safety margin so we
# never send a token that may already be expired by the time it reaches LHDN.
DEFAULT_REFRESH_MARGIN: int = 60


@dataclass(frozen=True, slots=True)
class OAuth2Token:
    """A bearer access token plus expiry."""

    access_token: str
    token_type: str
    expires_at: float  # monotonic-clock based, set by caller

    @classmethod
    def from_response(cls, payload: dict[str, object], *, fetched_at: float) -> OAuth2Token:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationError("Token response did not contain an access_token")
        token_type = payload.get("token_type")
        if not isinstance(token_type, str) or not token_type:
            token_type = "Bearer"
        expires_in_raw = payload.get("expires_in")
        expires_in = int(expires_in_raw) if isinstance(expires_in_raw, (int, float)) else 0
        return cls(
            access_token=access_token,
            token_type=token_type,
            expires_at=fetched_at + expires_in,
        )

    def is_expired(self, *, now: float, refresh_margin: int = DEFAULT_REFRESH_MARGIN) -> bool:
        # Avoid needing a monotonic clock vs wall clock interpretation: the
        # caller supplies whatever clock it used for `expires_at`.
        return now + refresh_margin >= self.expires_at


class StoredToken:
    """Internal holder so tests can poke the manager's cached token."""

    __slots__ = ("value",)

    def __init__(self, value: OAuth2Token | None) -> None:
        self.value: OAuth2Token | None = value

    @staticmethod
    def expire_now(mgr: TokenManager) -> None:
        """Force the manager to treat its token as expired (test helper)."""
        if mgr._stored.value is not None:
            mgr._stored.value = OAuth2Token(
                access_token=mgr._stored.value.access_token,
                token_type=mgr._stored.value.token_type,
                # Set expiry in the past so any freshness check fails.
                expires_at=mgr._clock() - 1,
            )


class TokenManager:
    """Acquires and caches OAuth2 ``client_credentials`` tokens.

    The manager uses an injectable ``httpx.Client`` so tests can mock the
    transport via ``respx``. The clock is also injectable to ease testing
    without sleeping.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: str = "InvoicingAPI",
        client: httpx.Client | None = None,
        refresh_margin: int = DEFAULT_REFRESH_MARGIN,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope
        self._http = client if client is not None else httpx.Client(timeout=30.0)
        self._refresh_margin = refresh_margin
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._stored = StoredToken(None)

    # ----- introspection -------------------------------------------------

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

    # ----- acquisition ---------------------------------------------------

    def get_token(self, *, headers: dict[str, str] | None = None) -> OAuth2Token:
        tok = self._stored.value
        if tok is not None and not tok.is_expired(
            now=self._clock(), refresh_margin=self._refresh_margin
        ):
            return tok
        return self._acquire(headers=headers)

    def invalidate(self) -> None:
        """Drop the cached token (call after a 401 from the API)."""
        self._stored.value = None

    # ----- internals -----------------------------------------------------

    def _build_form(self) -> dict[str, str]:
        return {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
            "scope": self._scope,
        }

    def _acquire(self, *, headers: dict[str, str] | None = None) -> OAuth2Token:
        try:
            response = self._http.post(self._token_url, data=self._build_form(), headers=headers)
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
                "MyInvois token endpoint returned non-JSON", status_code=response.status_code
            ) from exc

        tok = OAuth2Token.from_response(payload, fetched_at=self._clock())
        self._stored.value = tok
        return tok
