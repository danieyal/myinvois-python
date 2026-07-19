"""The synchronous MyInvoisClient.

The client owns:
- an :class:`~myinvois.auth.TokenManager` for OAuth2 tokens,
- an ``httpx.Client`` for outbound calls,
- a per-environment base API URL,
- an optional ``onbehalfof`` header (used by intermediary/ERP systems).

Path handling in ``request()`` intentionally mirrors both endpoints formats
seen in the LHDN API reference implementations:

- an absolute path like ``"/api/v1.0/..."`` is appended to ``base_api_url``,
- a full URL like ``"https://..."`` is used verbatim,
- the auth token endpoint already knows its absolute URL via the token manager.

The async twin lives in ``myinvois._async_client``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import httpx

from myinvois.auth import TokenManager
from myinvois.config import (
    Environment,
    base_api_url,
    base_identity_url,
    base_portal_url,
)
from myinvois.exceptions import error_for_status

if TYPE_CHECKING:
    from myinvois.services.document_types import DocumentTypesService
    from myinvois.services.documents import DocumentsService
    from myinvois.services.notifications import NotificationsService
    from myinvois.services.submissions import SubmissionsService
    from myinvois.services.taxpayer import TaxpayerService

__all__ = ["MyInvoisClient"]


def _message_from_error_payload(payload: dict[str, Any]) -> str | None:
    """Best-effort human-readable message from an LHDN/IdentityServer error body.

    LHDN style:       ``{"error": {"code": ..., "message": ...}}``
    IdentityServer:   ``{"error": "invalid_client", "error_description": "..."}``
    Fallback shape:   ``{"message": "..."}``
    """
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message") or error.get("code")
        if message and code:
            return f"{code}: {message}"
        return message
    if isinstance(error, str):
        description = payload.get("error_description")
        return f"{error}: {description}" if description else error
    message = payload.get("message")
    return message if isinstance(message, str) else None


class MyInvoisClient:
    """Synchronous client for the MyInvois API.

    Parameters:

    - ``client_id`` / ``client_secret``: OAuth2 credentials issued in the
      MyInvois portal.
    - ``environment``: :data:`Environment.SANDBOX` (default) or PRODUCTION.
    - ``on_behalf_of`` (kwarg or :meth:`set_on_behalf_of`): the TIN of the
      taxpayer an intermediary is presenting. Adds the ``onbehalfof`` header.
    - ``http_client``: optional pre-configured ``httpx.Client`` (e.g. for
      shared connection pooling or custom transports in tests).
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        environment: Environment = Environment.SANDBOX,
        on_behalf_of: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._http = http_client if http_client is not None else httpx.Client(timeout=30.0)
        self._environment = environment
        self._base_api_url = base_api_url(environment)
        self._base_portal_url = base_portal_url(environment)
        self._on_behalf_of: str | None = None
        self._document_types: DocumentTypesService | None = None
        self._documents: DocumentsService | None = None
        self._taxpayer: TaxpayerService | None = None
        self._notifications: NotificationsService | None = None
        self._submissions: SubmissionsService | None = None
        self._token_manager = TokenManager(
            client_id=client_id,
            client_secret=client_secret,
            token_url=base_identity_url(environment),
            client=self._http,
        )
        if on_behalf_of is not None:
            self.set_on_behalf_of(on_behalf_of)

    # ----- introspection -------------------------------------------------

    @property
    def environment(self) -> Environment:
        return self._environment

    @property
    def base_api_url(self) -> str:
        return self._base_api_url

    @property
    def base_portal_url(self) -> str:
        return self._base_portal_url

    @property
    def access_token(self) -> str | None:
        return self._token_manager.access_token

    # ----- auth ----------------------------------------------------------

    def login(self, *, on_behalf_of: str | None = None) -> str:
        """Acquire an OAuth2 access token.

        When ``on_behalf_of`` is provided, the intermediary's ``onbehalfof``
        header is set before the request and propagates to subsequent calls.
        Returns the access token string for convenience.
        """
        if on_behalf_of is not None:
            self.set_on_behalf_of(on_behalf_of)

        # The MyInvois /connect/token endpoint also expects the onbehalfof
        # header for intermediary authentication, so add it on the token POST
        # itself when configured.
        token_headers: dict[str, str] = {}
        if self._on_behalf_of is not None:
            token_headers["onbehalfof"] = self._on_behalf_of

        tok = self._token_manager.get_token(headers=token_headers or None)
        return tok.access_token

    def set_on_behalf_of(self, tin: str) -> None:
        """Set the ``onbehalfof`` header TIN for intermediary mode."""
        self._on_behalf_of = tin

    @property
    def on_behalf_of(self) -> str | None:
        return self._on_behalf_of

    # ----- service accessors --------------------------------------------

    @property
    def document_types(self) -> DocumentTypesService:
        # Lazy import to avoid a circular dependency at import time.
        from myinvois.services.document_types import DocumentTypesService

        if self._document_types is None:
            self._document_types = DocumentTypesService(self)
        return self._document_types

    @property
    def documents(self) -> DocumentsService:
        from myinvois.services.documents import DocumentsService

        if self._documents is None:
            self._documents = DocumentsService(self)
        return self._documents

    @property
    def taxpayer(self) -> TaxpayerService:
        from myinvois.services.taxpayer import TaxpayerService

        if self._taxpayer is None:
            self._taxpayer = TaxpayerService(self)
        return self._taxpayer

    @property
    def notifications(self) -> NotificationsService:
        from myinvois.services.notifications import NotificationsService

        if self._notifications is None:
            self._notifications = NotificationsService(self)
        return self._notifications

    @property
    def submissions(self) -> SubmissionsService:
        from myinvois.services.submissions import SubmissionsService

        if self._submissions is None:
            self._submissions = SubmissionsService(self)
        return self._submissions

    # ----- HTTP ----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Issue an authenticated request to the MyInvois API.

        - ``path`` may be a relative API path (``"/api/v1.0/..."``) or a full
          URL.
        - Auto-acquires a bearer token if not yet logged in (and refreshes
          before expiry thanks to the TokenManager).
        - Maps non-2xx responses to typed MyInvoisError subclasses.
        - Returns the parsed JSON body (or ``None`` when empty).
        """
        url = self._resolve_url(path)
        request_headers: dict[str, str] = {"Authorization": f"Bearer {self._require_token()}"}
        if self._on_behalf_of is not None:
            request_headers["onbehalfof"] = self._on_behalf_of
        if headers:
            request_headers.update(dict(headers))

        response = self._http.request(
            method=method,
            url=url,
            params=params,
            json=json,
            headers=request_headers,
            **kwargs,
        )
        return self._handle_response(response)

    def _resolve_url(self, path: str) -> str:
        # Tail-friendly: absolute URL if a scheme is present.
        if "://" in path:
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_api_url}{path}"

    def _require_token(self) -> str:
        tok = self._token_manager.get_token()
        # get_token refreshes proactively; but if a 401 slips through later,
        # invalidate + retry is handled at the caller for now.
        return tok.access_token

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            # The document /raw endpoints can serve XML — parse to text there.
            return response.text

    def _raise_for_status(self, response: httpx.Response) -> None:
        # Best-effort message: try JSON {"error":{"message":...}} then text.
        message = self._extract_error_message(response) or response.reason_phrase or "Error"
        raise error_for_status(message, status_code=response.status_code)

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return response.text or None

        if not isinstance(payload, dict):
            return None

        return _message_from_error_payload(payload)

    # ----- helpers -------------------------------------------------------

    def generate_document_qr_code_url(self, id_: str, long_id: str) -> str:
        """Build the shareable QR-code URL for a validated document."""
        return f"{self._base_portal_url}/{id_}/share/{long_id}"

    def close(self) -> None:
        """Release resources (HTTP connection pool)."""
        self._http.close()

    def __enter__(self) -> MyInvoisClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
