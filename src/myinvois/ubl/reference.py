"""Document-reference UBL components: AdditionalDocumentReference,
InvoiceDocumentReference, BillingReference, OrderReference, Attachment.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import Field, model_serializer, model_validator

from ._base import _leaf, _UblModel


class Attachment(_UblModel):
    """`cac:Attachment` — either an embedded binary file or an external URI.

    Phase 3b does NOT perform any file-exists check; users
    passing a `file_path` must ensure it is readable (the Phase 3c serializer
    will base64-encode the file contents lazily). Construction requires either
    a `file_path` or an `external_reference`.
    """

    file_path: str | None = Field(default=None, exclude=True, repr=False)
    external_reference: str | None = Field(default=None, serialization_alias="ExternalReference")
    mime_code: str | None = Field(default=None, exclude=True, repr=False)
    filename: str | None = Field(default=None, exclude=True, repr=False)
    base64_contents: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Pre-encoded base64 contents; if set, file_path is ignored.",
    )

    @model_validator(mode="after")
    def _requires_one(self) -> Attachment:
        if self.file_path is None and self.external_reference is None:
            raise ValueError("Attachment requires either file_path or external_reference")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.base64_contents is not None or self.file_path is not None:
            import base64 as _b64
            from mimetypes import guess_type
            from pathlib import Path

            if self.base64_contents is not None:
                contents_b64 = self.base64_contents
                fname = self.filename or "attachment"
                mime = self.mime_code or "application/octet-stream"
            else:
                p = Path(str(self.file_path))
                contents_b64 = _b64.b64encode(p.read_bytes()).decode("ascii")
                fname = p.name
                mime = self.mime_code or guess_type(p.name)[0] or "application/octet-stream"
            out["EmbeddedDocumentBinaryObject"] = _leaf(contents_b64, mimeCode=mime, filename=fname)
        if self.external_reference is not None:
            out["ExternalReference"] = {"URI": self.external_reference}
        return out


class AdditionalDocumentReference(_UblModel):
    """`cac:AdditionalDocumentReference` — referenced supporting document."""

    id: str = Field(serialization_alias="ID")
    document_type: str | None = Field(default=None, serialization_alias="DocumentType")
    document_description: str | None = Field(
        default=None, serialization_alias="DocumentDescription"
    )
    attachment: Attachment | None = Field(default=None, serialization_alias="Attachment")

    @model_validator(mode="after")
    def _must_have_id(self) -> AdditionalDocumentReference:
        if not self.id:
            raise ValueError("AdditionalDocumentReference.id is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ID": _leaf(self.id)}
        if self.document_type is not None:
            out["DocumentType"] = _leaf(self.document_type)
        if self.document_description is not None:
            out["DocumentDescription"] = _leaf(self.document_description)
        if self.attachment is not None:
            out["Attachment"] = self.attachment.model_dump(by_alias=True, exclude_none=True)
        return out


class InvoiceDocumentReference(_UblModel):
    """`cac:InvoiceDocumentReference` — used inside BillingReference."""

    id: str = Field(serialization_alias="ID")
    uuid: str = Field(serialization_alias="UUID")

    @model_validator(mode="after")
    def _requires_both(self) -> InvoiceDocumentReference:
        if not self.id:
            raise ValueError("InvoiceDocumentReference.id is required")
        if not self.uuid:
            raise ValueError("InvoiceDocumentReference.uuid is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {"ID": _leaf(self.id), "UUID": _leaf(self.uuid)}


class BillingReference(_UblModel):
    """`cac:BillingReference` — links to a prior invoice or supporting doc."""

    additional_document_reference: AdditionalDocumentReference | None = Field(
        default=None, serialization_alias="AdditionalDocumentReference"
    )
    invoice_document_reference: InvoiceDocumentReference | None = Field(
        default=None, serialization_alias="InvoiceDocumentReference"
    )

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.additional_document_reference is not None:
            out["AdditionalDocumentReference"] = [
                self.additional_document_reference.model_dump(by_alias=True, exclude_none=True)
            ]
        if self.invoice_document_reference is not None:
            out["InvoiceDocumentReference"] = [
                self.invoice_document_reference.model_dump(by_alias=True, exclude_none=True)
            ]
        return out


class OrderReference(_UblModel):
    """`cac:OrderReference` — the buyer's PO reference (id mandatory)."""

    id: str = Field(serialization_alias="ID")
    sales_order_id: str | None = Field(default=None, serialization_alias="SalesOrderID")
    issue_date: date | None = Field(default=None, serialization_alias="IssueDate")

    @model_validator(mode="after")
    def _must_have_id(self) -> OrderReference:
        if not self.id:
            raise ValueError("OrderReference.id is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.id is not None:
            out["ID"] = _leaf(self.id)
        if self.sales_order_id is not None:
            out["SalesOrderID"] = _leaf(self.sales_order_id)
        if self.issue_date is not None:
            out["IssueDate"] = _leaf(self.issue_date.isoformat())
        return out
