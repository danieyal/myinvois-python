"""Async document-submission service.

Mirrors :class:`~myinvois.services.submissions.SubmissionsService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myinvois.exceptions import ValidationError
from myinvois.services.models import (
    GetSubmissionResponse,
    SubmitDocumentsResponse,
)

if TYPE_CHECKING:
    from myinvois._async_client import AsyncMyInvoisClient

__all__ = ["AsyncSubmissionsService"]


class AsyncSubmissionsService:
    """Async write-side operations for the LHDN document-submissions API."""

    BASE_PATH = "/api/v1.0/documentsubmissions"

    def __init__(self, client: AsyncMyInvoisClient) -> None:
        self._client = client

    async def submit_documents(
        self,
        documents: list[dict[str, str]],
    ) -> SubmitDocumentsResponse:
        """Submit one or more signed UBL documents."""
        if not documents:
            raise ValidationError("submit_documents() requires a non-empty documents list.")
        body = {"documents": documents}
        raw = await self._client.request("POST", f"{self.BASE_PATH}/", json=body)
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return SubmitDocumentsResponse.model_validate(raw)

    async def get_submission(
        self,
        submission_uid: str,
        *,
        page_no: int | None = None,
        page_size: int | None = None,
    ) -> GetSubmissionResponse:
        """Retrieve a single submission's detail, paginated over its documents."""
        params: dict[str, str] = {}
        if page_no is not None:
            params["pageNo"] = str(page_no)
        if page_size is not None:
            params["pageSize"] = str(page_size)
        raw = await self._client.request(
            "GET", f"{self.BASE_PATH}/{submission_uid}", params=params or None
        )
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return GetSubmissionResponse.model_validate(raw)
