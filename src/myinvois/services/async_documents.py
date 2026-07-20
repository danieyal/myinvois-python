"""Async documents service — read + state-mutation endpoints.

Mirrors :class:`~myinvois.services.documents.DocumentsService`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from myinvois.services.documents import (
    DocumentDirection,
    DocumentStateChangeStatus,
    DocumentStatus,
    RecentDocumentsQuery,
    SearchDocumentsQuery,
)
from myinvois.services.models import DocumentStateChangeResponse

if TYPE_CHECKING:
    from myinvois._async_client import AsyncMyInvoisClient

__all__ = ["AsyncDocumentsService"]


class AsyncDocumentsService:
    """Async read- and state-mutation operations on MyInvois documents."""

    BASE_PATH = "/api/v1.0/documents"
    _STATE_PATH = "/api/v1.0/documents/state"
    REASON_MAX_LEN: int = 300

    def __init__(self, client: AsyncMyInvoisClient) -> None:
        self._client = client

    async def get_raw(self, uuid: str) -> dict[str, Any]:
        """Retrieve a document's source XML/JSON plus LHDN metadata."""
        raw = await self._client.request("GET", f"{self.BASE_PATH}/{uuid}/raw")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return raw

    async def get_details(self, uuid: str) -> dict[str, Any]:
        """Retrieve a single document's full details including validation."""
        raw = await self._client.request("GET", f"{self.BASE_PATH}/{uuid}/details")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return raw

    async def get_recent_documents(
        self,
        *,
        page_no: int = 1,
        page_size: int = 20,
        submission_date_from: datetime | str | None = None,
        submission_date_to: datetime | str | None = None,
        issue_date_from: datetime | str | None = None,
        issue_date_to: datetime | str | None = None,
        invoice_direction: DocumentDirection | None = None,
        status: DocumentStatus | None = None,
        document_type: str | None = None,
        receiver_id: str | None = None,
        receiver_id_type: str | None = None,
        receiver_tin: str | None = None,
        issuer_id: str | None = None,
        issuer_id_type: str | None = None,
        issuer_tin: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve documents issued within the last 30 days (paginated)."""
        query = RecentDocumentsQuery(
            page_no=page_no,
            page_size=page_size,
            submission_date_from=submission_date_from,
            submission_date_to=submission_date_to,
            issue_date_from=issue_date_from,
            issue_date_to=issue_date_to,
            invoice_direction=invoice_direction,
            status=status,
            document_type=document_type,
            receiver_id=receiver_id,
            receiver_id_type=receiver_id_type,
            receiver_tin=receiver_tin,
            issuer_id=issuer_id,
            issuer_id_type=issuer_id_type,
            issuer_tin=issuer_tin,
        )
        raw = await self._client.request(
            "GET", f"{self.BASE_PATH}/recent", params=query.to_params()
        )

        return raw if isinstance(raw, dict) else {}

    async def search_documents(
        self,
        *,
        submission_date_from: datetime | str | None = None,
        submission_date_to: datetime | str | None = None,
        issue_date_from: datetime | str | None = None,
        issue_date_to: datetime | str | None = None,
        page_no: int = 1,
        page_size: int = 100,
        invoice_direction: DocumentDirection | None = None,
        status: DocumentStatus | None = None,
        document_type: str | None = None,
        uuid: str | None = None,
        search_query: str | None = None,
    ) -> dict[str, Any]:
        """Search across all submitted documents (requires a date pair)."""
        query = SearchDocumentsQuery(
            page_no=page_no,
            page_size=page_size,
            submission_date_from=submission_date_from,
            submission_date_to=submission_date_to,
            issue_date_from=issue_date_from,
            issue_date_to=issue_date_to,
            invoice_direction=invoice_direction,
            status=status,
            document_type=document_type,
            uuid=uuid,
            search_query=search_query,
        )
        raw = await self._client.request(
            "GET", f"{self.BASE_PATH}/search", params=query.to_params()
        )
        return raw if isinstance(raw, dict) else {}

    async def set_document_state(
        self,
        uuid: str,
        status: DocumentStateChangeStatus | str,
        *,
        reason: str = "",
    ) -> DocumentStateChangeResponse:
        """Generic document-state-change call (cancel or reject)."""
        if isinstance(status, DocumentStateChangeStatus):
            status_val = status.value
        else:
            try:
                status_val = DocumentStateChangeStatus(str(status)).value
            except ValueError as exc:
                from myinvois.exceptions import ValidationError

                raise ValidationError(
                    f"Unknown document state-change status: {status!r}. "
                    f"Expected one of {[s.value for s in DocumentStateChangeStatus]}."
                ) from exc

        self._validate_reason(reason)

        body = {"status": status_val, "reason": reason}
        raw = await self._client.request("PUT", f"{self._STATE_PATH}/{uuid}/state", json=body)
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return DocumentStateChangeResponse.model_validate(raw)

    async def cancel_document(
        self,
        uuid: str,
        reason: str = "",
    ) -> DocumentStateChangeResponse:
        """Cancel a previously-issued document."""
        return await self.set_document_state(
            uuid, DocumentStateChangeStatus.CANCELLED, reason=reason
        )

    async def reject_document(
        self,
        uuid: str,
        reason: str = "",
    ) -> DocumentStateChangeResponse:
        """Reject a received document and request the supplier to cancel it."""
        return await self.set_document_state(
            uuid, DocumentStateChangeStatus.REJECTED, reason=reason
        )

    @classmethod
    def _validate_reason(cls, reason: str) -> None:
        from myinvois.exceptions import ValidationError

        if not isinstance(reason, str):
            raise ValidationError(f"reason must be a str, got {type(reason).__name__}")
        if len(reason) > cls.REASON_MAX_LEN:
            raise ValidationError(
                f"reason must not exceed {cls.REASON_MAX_LEN} characters (got {len(reason)})."
            )
