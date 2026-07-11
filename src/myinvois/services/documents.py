"""Documents service — read endpoints for the MyInvois documents API.

Phase 2 covers read endpoints. The cancel/reject state changes live in
``services/submissions`` under Phase 5.

Endpoints (from PHP SDK DocumentService):
- GET /api/v1.0/documents/{uuid}/raw   : source XML/JSON + metadata
- GET /api/v1.0/documents/{uuid}/details: full doc + validation results
- GET /api/v1.0/documents/recent        : recent (last 30 days), paginated
- GET /api/v1.0/documents/search         : full search (needs date pair)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, model_validator

from myinvois.exceptions import ValidationError

if TYPE_CHECKING:
    from myinvois.client import MyInvoisClient

__all__ = [
    "DocumentDirection",
    "DocumentStatus",
    "DocumentsService",
    "RecentDocumentsQuery",
    "SearchDocumentsQuery",
]


class DocumentDirection(StrEnum):
    SENT = "Sent"
    RECEIVED = "Received"


class DocumentStatus(StrEnum):
    VALID = "Valid"
    INVALID = "Invalid"
    CANCELLED = "Cancelled"
    SUBMITTED = "Submitted"


def _to_zulu(value: datetime | str | None) -> str | None:
    """Format a datetime as the MyInvois UTC query-string shape
    ``YYYY-MM-DDTHH:MM:SSZ``; pass strings through untouched."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return value


# camelCase keys happens manually so the query model stays Pydantic-native and
# can drop `None` without contaminating the request URL.


class _QueryBase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RecentDocumentsQuery(_QueryBase):
    page_no: int = 1
    page_size: int = 20
    submission_date_from: datetime | str | None = None
    submission_date_to: datetime | str | None = None
    issue_date_from: datetime | str | None = None
    issue_date_to: datetime | str | None = None
    invoice_direction: DocumentDirection | None = None
    status: DocumentStatus | None = None
    document_type: str | None = None
    receiver_id: str | None = None
    receiver_id_type: str | None = None
    receiver_tin: str | None = None
    issuer_id: str | None = None
    issuer_id_type: str | None = None
    issuer_tin: str | None = None

    def to_params(self) -> dict[str, str]:
        # Snapshot the current values (support both `field` and alias access).
        data = self.model_dump(exclude_none=True, by_alias=False)
        out: dict[str, str] = {}
        for key, value in data.items():
            if key in {"page_no", "page_size"}:
                out[_CAMEL[key]] = str(value)
                continue
            formatted = _to_zulu(value) if isinstance(value, datetime) else value
            out[_CAMEL[key]] = formatted if formatted is not None else str(value)
        return out


class SearchDocumentsQuery(_QueryBase):
    page_no: int = 1
    page_size: int = 100
    submission_date_from: datetime | str | None = None
    submission_date_to: datetime | str | None = None
    issue_date_from: datetime | str | None = None
    issue_date_to: datetime | str | None = None
    invoice_direction: DocumentDirection | None = None
    status: DocumentStatus | None = None
    document_type: str | None = None
    uuid: str | None = None
    search_query: str | None = None

    @model_validator(mode="after")
    def _check_date_pair(self) -> SearchDocumentsQuery:
        has_sub = self.submission_date_from is not None and self.submission_date_to is not None
        has_issue = self.issue_date_from is not None and self.issue_date_to is not None
        if not has_sub and not has_issue:
            raise ValidationError(
                "SearchDocumentsQuery requires either a (submission_date_from, "
                "submission_date_to) date pair or an (issue_date_from, "
                "issue_date_to) date pair.",
            )
        # Also reject half-pairs to match LHDN semantics ("Mandatory when X is provided").
        if (self.submission_date_from is None) != (self.submission_date_to is None):
            raise ValidationError(
                "submission_date_from and submission_date_to must be supplied together",
            )
        if (self.issue_date_from is None) != (self.issue_date_to is None):
            raise ValidationError(
                "issue_date_from and issue_date_to must be supplied together",
            )
        return self

    def to_params(self) -> dict[str, str]:
        data = self.model_dump(exclude_none=True, by_alias=False)
        out: dict[str, str] = {}
        for key, value in data.items():
            if key in {"page_no", "page_size"}:
                out[_CAMEL[key]] = str(value)
                continue
            formatted = _to_zulu(value) if isinstance(value, datetime) else value
            out[_CAMEL[key]] = formatted if formatted is not None else str(value)
        return out


# snake → camel map for the LHDN query keys.
_CAMEL: dict[str, str] = {
    "page_no": "pageNo",
    "page_size": "pageSize",
    "submission_date_from": "submissionDateFrom",
    "submission_date_to": "submissionDateTo",
    "issue_date_from": "issueDateFrom",
    "issue_date_to": "issueDateTo",
    "invoice_direction": "invoiceDirection",
    "status": "status",
    "document_type": "documentType",
    "receiver_id": "receiverId",
    "receiver_id_type": "receiverIdType",
    "receiver_tin": "receiverTin",
    "issuer_id": "issuerId",
    "issuer_id_type": "issuerIdType",
    "issuer_tin": "issuerTin",
    "uuid": "uuid",
    "search_query": "searchQuery",
}


class DocumentsService:
    """Read-side operations on MyInvois documents.

    Exposed on :class:`~myinvois.client.MyInvoisClient` as
    ``client.documents``.
    """

    BASE_PATH = "/api/v1.0/documents"

    def __init__(self, client: MyInvoisClient) -> None:
        self._client = client

    def get_raw(self, uuid: str) -> dict[str, Any]:
        """Retrieve a document's source XML/JSON plus LHDN metadata."""
        raw = self._client.request("GET", f"{self.BASE_PATH}/{uuid}/raw")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return raw

    def get_details(self, uuid: str) -> dict[str, Any]:
        """Retrieve a single document's full details including validation."""
        raw = self._client.request("GET", f"{self.BASE_PATH}/{uuid}/details")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return raw

    def get_recent_documents(
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
        raw = self._client.request("GET", f"{self.BASE_PATH}/recent", params=query.to_params())
        return raw if isinstance(raw, dict) else {}

    def search_documents(
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
        raw = self._client.request("GET", f"{self.BASE_PATH}/search", params=query.to_params())
        return raw if isinstance(raw, dict) else {}
