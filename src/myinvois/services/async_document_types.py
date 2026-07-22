"""Async document-type operations — list / get / get_version.

Mirrors :class:`~myinvois.services.document_types.DocumentTypesService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myinvois.services.models import (
    DocumentType,
    DocumentTypeList,
    DocumentTypeVersion,
)

if TYPE_CHECKING:
    from myinvois._async_client import AsyncMyInvoisClient

__all__ = ["AsyncDocumentTypesService"]


class AsyncDocumentTypesService:
    """Async read-only document-type operations."""

    BASE_PATH = "/api/v1.0/documenttypes"

    def __init__(self, client: AsyncMyInvoisClient) -> None:
        self._client = client

    async def list(self, *, page_no: int = 1, page_size: int = 20) -> DocumentTypeList:
        params = {"pageNo": page_no, "pageSize": page_size}
        raw = await self._client.request("GET", self.BASE_PATH, params=params)
        return DocumentTypeList.model_validate(raw if isinstance(raw, dict) else {})

    async def get(self, id_: int | str) -> DocumentType:
        raw = await self._client.request("GET", f"{self.BASE_PATH}/{id_}")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return DocumentType.model_validate(raw)

    async def get_version(self, id_: int | str, version_id: int | str) -> DocumentTypeVersion:
        raw = await self._client.request("GET", f"{self.BASE_PATH}/{id_}/versions/{version_id}")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return DocumentTypeVersion.model_validate(raw)
