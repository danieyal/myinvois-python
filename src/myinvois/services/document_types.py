"""Document Type service — list / get / get_version.

Endpoints:
- GET /api/v1.0/documenttypes            : list all published document types
- GET /api/v1.0/documenttypes/{id}       : single document type
- GET /api/v1.0/documenttypes/{id}/versions/{vid} : single version of a type
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myinvois.services.models import (
    DocumentType,
    DocumentTypeList,
    DocumentTypeVersion,
)

if TYPE_CHECKING:
    from myinvois.client import MyInvoisClient

__all__ = ["DocumentType", "DocumentTypeList", "DocumentTypeVersion", "DocumentTypesService"]


class DocumentTypesService:
    """Read-only document-type operations.

    Exposed on :class:`~myinvois.client.MyInvoisClient` as
    ``client.document_types``.
    """

    BASE_PATH = "/api/v1.0/documenttypes"

    def __init__(self, client: MyInvoisClient) -> None:
        self._client = client

    def list(self, *, page_no: int = 1, page_size: int = 20) -> DocumentTypeList:
        params = {"pageNo": page_no, "pageSize": page_size}
        raw = self._client.request("GET", self.BASE_PATH, params=params)
        return self._parse_list(raw if isinstance(raw, dict) else {})

    def get(self, id_: int | str) -> DocumentType:
        raw = self._client.request("GET", f"{self.BASE_PATH}/{id_}")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return DocumentType.model_validate(raw)

    def get_version(self, id_: int | str, version_id: int | str) -> DocumentTypeVersion:
        raw = self._client.request("GET", f"{self.BASE_PATH}/{id_}/versions/{version_id}")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return DocumentTypeVersion.model_validate(raw)

    @staticmethod
    def _parse_list(raw: dict[str, object]) -> DocumentTypeList:
        return DocumentTypeList.model_validate(raw)
