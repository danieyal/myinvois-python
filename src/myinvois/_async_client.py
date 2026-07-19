"""The asynchronous MyInvoisClient.

Mirrors :class:`~myinvois.client.MyInvoisClient` but uses
:class:`httpx.AsyncClient` and :class:`~myinvois.auth.AsyncTokenManager`.

Usage::

    async with AsyncMyInvoisClient("id", "secret") as client:
        types = await client.document_types.list()
        result = await client.submissions.submit_documents([payload])
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import httpx

from myinvois._async_auth import AsyncTokenManager
from myinvois.client import _message_from_error_payload
from myinvois.config import (
    Environment,
    base_api_url,
    base_identity_url,
    base_portal_url,
)
from myinvois.exceptions import error_for_status

if TYPE_CHECKING:
    from myinvois.services.async_document_types import AsyncDocumentTypesService
    from myinvois.services.async_documents import AsyncDocumentsService
    from myinvois.services.async_notifications import AsyncNotificationsService
    from myinvois.services.async_submissions import AsyncSubmissionsService
    from myinvois.services.async_taxpayer import AsyncTaxpayerService

__all__ = ["AsyncMyInvoisClient"]


class AsyncMyInvoisClient:
    """Asynchronous client for the MyInvois API.

    Parameters mirror :class:`~myinvois.client.MyInvoisClient`:

    - ``client_id`` / ``client_secret``: OAuth2 credentials.
    - ``environment``: :data:`Environment.SANDBOX` (default) or PRODUCTION.
    - ``on_behalf_of``: TIN for intermediary mode.
    - ``http_client``: optional pre-configured ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        environment: Environment = Environment.SANDBOX,
        on_behalf_of: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._http = http_client if http_client is not None else httpx.AsyncClient(timeout=30.0)
        self._environment = environment
        self._base_api_url = base_api_url(environment)
        self._base_portal_url = base_portal_url(environment)
        self._on_behalf_of: str | None = None
        self._document_types: AsyncDocumentTypesService | None = None
        self._documents: AsyncDocumentsService | None = None
        self._taxpayer: AsyncTaxpayerService | None = None
        self._notifications: AsyncNotificationsService | None = None
        self._submissions: AsyncSubmissionsService | None = None
        self._token_manager = AsyncTokenManager(
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

    async def login(self, *, on_behalf_of: str | None = None) -> str:
        """Acquire an OAuth2 access token asynchronously."""
        if on_behalf_of is not None:
            self.set_on_behalf_of(on_behalf_of)

        token_headers: dict[str, str] = {}
        if self._on_behalf_of is not None:
            token_headers["onbehalfof"] = self._on_behalf_of

        tok = await self._token_manager.get_token(headers=token_headers or None)
        return tok.access_token

    def set_on_behalf_of(self, tin: str) -> None:
        """Set the ``onbehalfof`` header TIN for intermediary mode."""
        self._on_behalf_of = tin

    @property
    def on_behalf_of(self) -> str | None:
        return self._on_behalf_of

    # ----- service accessors --------------------------------------------

    @property
    def document_types(self) -> AsyncDocumentTypesService:
        from myinvois.services.async_document_types import AsyncDocumentTypesService

        if self._document_types is None:
            self._document_types = AsyncDocumentTypesService(self)
        return self._document_types

    @property
    def documents(self) -> AsyncDocumentsService:
        from myinvois.services.async_documents import AsyncDocumentsService

        if self._documents is None:
            self._documents = AsyncDocumentsService(self)
        return self._documents

    @property
    def taxpayer(self) -> AsyncTaxpayerService:
        from myinvois.services.async_taxpayer import AsyncTaxpayerService

        if self._taxpayer is None:
            self._taxpayer = AsyncTaxpayerService(self)
        return self._taxpayer

    @property
    def notifications(self) -> AsyncNotificationsService:
        from myinvois.services.async_notifications import AsyncNotificationsService

        if self._notifications is None:
            self._notifications = AsyncNotificationsService(self)
        return self._notifications

    @property
    def submissions(self) -> AsyncSubmissionsService:
        from myinvois.services.async_submissions import AsyncSubmissionsService

        if self._submissions is None:
            self._submissions = AsyncSubmissionsService(self)
        return self._submissions

    # ----- HTTP ----------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Issue an authenticated async request to the MyInvois API."""
        url = self._resolve_url(path)
        request_headers: dict[str, str] = {"Authorization": f"Bearer {await self._require_token()}"}
        if self._on_behalf_of is not None:
            request_headers["onbehalfof"] = self._on_behalf_of
        if headers:
            request_headers.update(dict(headers))

        response = await self._http.request(
            method=method,
            url=url,
            params=params,
            json=json,
            headers=request_headers,
            **kwargs,
        )
        return self._handle_response(response)

    def _resolve_url(self, path: str) -> str:
        if "://" in path:
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_api_url}{path}"

    async def _require_token(self) -> str:
        tok = await self._token_manager.get_token()
        return tok.access_token

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def _raise_for_status(self, response: httpx.Response) -> None:
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

    async def aclose(self) -> None:
        """Release resources (HTTP connection pool)."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncMyInvoisClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
