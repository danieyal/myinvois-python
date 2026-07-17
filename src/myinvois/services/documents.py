"""Documents service — read + state-mutation endpoints.

Phase 2 covers read endpoints. The cancel/reject PUT-state changes (Phase 5)
live on the same service (matching the LHDN API URL family
``/api/v1.0/documents/...``).

Endpoints (from PHP SDK DocumentService + the LHDN API docs):
- GET  /api/v1.0/documents/{uuid}/raw        : source XML/JSON + metadata
- GET  /api/v1.0/documents/{uuid}/details     : full doc + validation results
- GET  /api/v1.0/documents/recent             : recent (last 30 days), paginated
- GET  /api/v1.0/documents/search             : full search (needs date pair)
- PUT  /api/v1.0/documents/state/{uuid}/state : cancel or reject a document
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, model_validator

from myinvois.exceptions import ValidationError
from myinvois.services.models import DocumentStateChangeResponse

if TYPE_CHECKING:
    from myinvois.client import MyInvoisClient

__all__ = [
    "DocumentDirection",
    "DocumentStateChangeResponse",
    "DocumentStateChangeStatus",
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


class DocumentStateChangeStatus(StrEnum):
    """Lower-case ``status`` body values for ``PUT /documents/state/{uuid}/state``.

    Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/03-cancel-document/
          https://sdk.myinvois.hasil.gov.my/einvoicingapi/04-reject-document/

    The LHDN API expects the lowercase forms (``"cancelled"`` / ``"rejected"``)
    in the request body. The response inverts to title case: ``"Cancelled"``
    for cancel and ``"Requested for Rejection"`` for reject (until the
    Supplier cancels).
    """

    CANCELLED = "cancelled"
    REJECTED = "rejected"


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

    # Phase 5 — state mutations (cancel / reject) ----------------------------

    #: Minimum and maximum allowed byte-length of the ``reason`` text field.
    #: Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/03-cancel-document/
    #: The official doc limits ``reason`` to 300 characters; reason becomes
    #: mandatory when cancelling (an empty string is permitted by the wire,
    #: matching the PHP SDK's default of ``''``).
    REASON_MAX_LEN: int = 300
    _STATE_PATH = "/api/v1.0/documents/state"

    def set_document_state(
        self,
        uuid: str,
        status: DocumentStateChangeStatus | str,
        *,
        reason: str = "",
    ) -> DocumentStateChangeResponse:
        """Generic document-state-change call.

        This is the underlying primitive used by :meth:`cancel_document`
        (``status="cancelled"``) and :meth:`reject_document`
        (``status="rejected"``). Use those convenience wrappers unless you
        need the raw primitive.

        Pre-validates the ``reason`` length client-side (>(()300 chars raises
        :class:`ValidationError`) — matches the LHDN API's documented limit
        and avoids one round-trip.
        """
        # Coerce the status to the canonical lowercase form.
        if isinstance(status, DocumentStateChangeStatus):
            status_val = status.value
        else:
            try:
                status_val = DocumentStateChangeStatus(str(status)).value
            except ValueError as exc:
                raise ValidationError(
                    f"Unknown document state-change status: {status!r}. "
                    f"Expected one of {[s.value for s in DocumentStateChangeStatus]}."
                ) from exc

        self._validate_reason(reason)

        body = {"status": status_val, "reason": reason}
        raw = self._client.request("PUT", f"{self._STATE_PATH}/{uuid}/state", json=body)
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return DocumentStateChangeResponse.model_validate(raw)

    def cancel_document(
        self,
        uuid: str,
        reason: str = "",
    ) -> DocumentStateChangeResponse:
        """Cancel a previously-issued document.

        Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/03-cancel-document/

        Only available to the issuer within a 72-hour window from the moment
        the document was marked Valid. Server-level failures (window elapsed,
        referenced by another doc, etc.) are reported back inside the
        response's ``error`` block when the server returns a 200 with an
        ``error`` field; transport-level failures raise the matching
        :class:`~myinvois.exceptions.MyInvoisError` subclass.
        """
        return self.set_document_state(uuid, DocumentStateChangeStatus.CANCELLED, reason=reason)

    def reject_document(
        self,
        uuid: str,
        reason: str = "",
    ) -> DocumentStateChangeResponse:
        """Reject a received document and request the supplier to cancel it.

        Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/04-reject-document/

        Only available to the recipient within a 72-hour window from the
        moment the document was marked Valid. The document is **not**
        immediately cancelled — the supplier must subsequently cancel.
        """
        return self.set_document_state(uuid, DocumentStateChangeStatus.REJECTED, reason=reason)

    @classmethod
    def _validate_reason(cls, reason: str) -> None:
        if not isinstance(reason, str):
            raise ValidationError(f"reason must be a str, got {type(reason).__name__}")
        if len(reason) > cls.REASON_MAX_LEN:
            raise ValidationError(
                f"reason must not exceed {cls.REASON_MAX_LEN} characters (got {len(reason)})."
            )
