"""Pydantic response models returned by the MyInvois API.

These models are read-side response schemas (Phase 2). Phase 3 will add the
write-side UBL document models under ``myinvois.ubl.models``.

Conventions:
- snake_case aliases for the LHDN camelCase JSON fields via Pydantic `alias`.
- Optional fields are tolerant of missing keys (`model_config = ConfigDict(extra="ignore")`)
  so forward-compatible additions by LHDN don't break parsing.
- Unknown fields are *ignored* (not rejected) — LHDN can add fields safely.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AcceptedDocument",
    "DocumentStateChangeResponse",
    "DocumentSummary",
    "DocumentSummaryTotals",
    "DocumentType",
    "DocumentTypeList",
    "DocumentTypeSchema",
    "DocumentTypeVersion",
    "GetSubmissionResponse",
    "LhdnError",
    "Paginated",
    "RejectedDocument",
    "SubmitDocumentsResponse",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Paginated(_Base):
    page_size: int
    total_pages: int = 0


class DocumentTypeSchema(_Base):
    schema_id: str | None = Field(default=None, alias="schemaId")
    valid_from: str | None = Field(default=None, alias="validFrom")
    valid_to: str | None = Field(default=None, alias="validTo")


class DocumentType(_Base):
    id: int
    name: str
    description: str | None = None
    code_number: str | None = Field(default=None, alias="codeNumber")
    active_since: str | None = Field(default=None, alias="activeSince")
    active_to: str | None = Field(default=None, alias="activeTo")
    active_version_id: int | None = Field(default=None, alias="activeVersionId")


class DocumentTypeVersion(_Base):
    id: int
    name: str
    description: str | None = None
    version_number: str | None = Field(default=None, alias="versionNumber")
    active_since: str | None = Field(default=None, alias="activeSince")
    active_to: str | None = Field(default=None, alias="activeTo")
    schemas: list[DocumentTypeSchema] = Field(default_factory=list)


class DocumentTypeList(_Base):
    total_pages: int = Field(default=0, alias="totalPages")
    page_size: int = Field(default=0, alias="pageSize")
    result: list[DocumentType]


# A small helper used by services to wrap raw dicts as models where the LHDN
# response shape is a plain list (no `result` wrapper).
def _as_items(raw: Any, *, model: type[BaseModel], key: str = "result") -> list[BaseModel]:
    if isinstance(raw, dict) and key in raw and isinstance(raw[key], list):
        return [model.model_validate(item) for item in raw[key]]
    if isinstance(raw, list):
        return [model.model_validate(item) for item in raw]
    return []


# ---------------------------------------------------------------------------
# Phase 5 — Submit documents + Get submission response models
# Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/02-submit-documents/
#       https://sdk.myinvois.hasil.gov.my/einvoicingapi/06-get-submission/
# ---------------------------------------------------------------------------


class LhdnError(_Base):
    """The ``error`` object shape returned inside LHDN response bodies.

    Spec: https://sdk.myinvois.hasil.gov.my/standard-error-response/
    """

    code: str | None = None
    message: str | None = None
    target: str | None = None
    details: list[dict[str, Any]] = Field(default_factory=list)
    property: str | None = None


class AcceptedDocument(_Base):
    """An entry in ``acceptedDocuments[]`` from a successful submit response."""

    uuid: str
    invoice_code_number: str = Field(alias="invoiceCodeNumber")


class RejectedDocument(_Base):
    """An entry in ``rejectedDocuments[]`` from a submit response."""

    invoice_code_number: str = Field(alias="invoiceCodeNumber")
    error: LhdnError | None = None


class SubmitDocumentsResponse(_Base):
    """Body of the HTTP 202 response returned by ``POST /documentsubmissions``."""

    submission_uid: str = Field(alias="submissionUID")
    accepted_documents: list[AcceptedDocument] = Field(
        default_factory=list, alias="acceptedDocuments"
    )
    rejected_documents: list[RejectedDocument] = Field(
        default_factory=list, alias="rejectedDocuments"
    )


class DocumentSummaryTotals(_Base):
    """Decimally-typed totals block inside each ``DocumentSummary`` row."""

    total_excluding_tax: Decimal | None = Field(default=None, alias="totalExcludingTax")
    total_discount: Decimal | None = Field(default=None, alias="totalDiscount")
    total_net_amount: Decimal | None = Field(default=None, alias="totalNetAmount")
    total_payable_amount: Decimal | None = Field(default=None, alias="totalPayableAmount")


_TOTAL_KEYS = (
    "totalExcludingTax",
    "totalDiscount",
    "totalNetAmount",
    "totalPayableAmount",
)


class DocumentSummary(_Base):
    """A single document row in a ``GET /documentsubmissions/{id}`` response.

    The LHDN API returns the four ``total*`` keys at the same level as
    ``uuid``/``status``/etc. A ``model_validator(mode="before")`` reshapes
    those into a nested ``totals`` sub-object so each row's totals are
    addressable via ``doc.totals.total_*`` (mirroring the grouping in the
    LHDN documentation).
    """

    uuid: str
    submission_uid: str | None = Field(default=None, alias="submissionUid")
    long_id: str | None = None
    internal_id: str | None = Field(default=None, alias="internalId")
    type_name: str | None = Field(default=None, alias="typeName")
    type_version_name: str | None = Field(default=None, alias="typeVersionName")
    issuer_tin: str | None = Field(default=None, alias="issuerTin")
    issuer_name: str | None = Field(default=None, alias="issuerName")
    receiver_id: str | None = Field(default=None, alias="receiverId")
    receiver_name: str | None = Field(default=None, alias="receiverName")
    date_time_issued: str | None = Field(default=None, alias="dateTimeIssued")
    date_time_received: str | None = Field(default=None, alias="dateTimeReceived")
    date_time_validated: str | None = Field(default=None, alias="dateTimeValidated")
    cancel_date_time: str | None = Field(default=None, alias="cancelDateTime")
    reject_request_date_time: str | None = Field(default=None, alias="rejectRequestDateTime")
    document_status_reason: str | None = None
    created_by_user_id: str | None = Field(default=None, alias="createdByUserId")
    status: str | None = None
    totals: DocumentSummaryTotals = Field(default_factory=DocumentSummaryTotals)

    @model_validator(mode="before")
    @classmethod
    def _nest_totals(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "totals" in data:
            return data
        lifted = {k: data[k] for k in _TOTAL_KEYS if k in data}
        if not lifted:
            return data
        out = dict(data)
        for k in lifted:
            out.pop(k)
        out["totals"] = lifted
        return out


class GetSubmissionResponse(_Base):
    """Body of the HTTP 200 response returned by ``GET /documentsubmissions/{id}``."""

    submission_uid: str = Field(alias="submissionUid")
    document_count: int | None = Field(default=None, alias="documentCount")
    date_time_received: str | None = Field(default=None, alias="dateTimeReceived")
    overall_status: str | None = Field(default=None, alias="overallStatus")
    document_summary: list[DocumentSummary] = Field(default_factory=list, alias="documentSummary")


# ---------------------------------------------------------------------------
# Phase 5 — Document state change (cancel/reject) response models.
# Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/03-cancel-document/
#       https://sdk.myinvois.hasil.gov.my/einvoicingapi/04-reject-document/
# ---------------------------------------------------------------------------


class DocumentStateChangeResponse(_Base):
    """Result of ``PUT /documents/state/{uuid}/state``.

    The ``status`` field echoes the document's status as the server sees it:
    * ``"Cancelled"`` after a successful cancel,
    * ``"Requested for Rejection"`` after a reject request (until Supplier
      cancels), and
    * If the request was logically refused (still inside the same endpoint
      call), an ``error`` block is returned alongside the unchanged status.
    """

    uuid: str
    status: str | None = None
    error: LhdnError | None = None
