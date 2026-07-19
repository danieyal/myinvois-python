"""`cac:Invoice` — the top-level Invoice document (doc type code 01).

This is the mainstream `Invoice` document the LHDN MyInvois system accepts.
Inherits UBL field naming structure; `Invoice.model_dump(by_alias=True,
exclude_none=True)` produces the canonical nested structure, ready for
the envelope builder to wrap.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import Field, field_validator, model_serializer, model_validator

from myinvois.codes import Currency, DocumentTypeCode

from ._base import _leaf, _UblModel
from .common import AllowanceCharge, Delivery, InvoicePeriod, TaxExchangeRate
from .monetary import LegalMonetaryTotal
from .party import AccountingParty, Party
from .payment import PaymentMeans, PaymentTerms, PrepaidPayment
from .reference import (
    AdditionalDocumentReference,
    BillingReference,
    OrderReference,
)
from .tax import TaxTotal


class Invoice(_UblModel):
    """LHDN Invoice (document type code 01).

    Required (validated at construction):
    * `id` — invoice number.
    * `issue_date_time` — UTC; emitted as `IssueDate` + `IssueTime`.
    * `invoice_type_code` — defaults to `DocumentTypeCode.INVOICE={"01",
      listVersionID="1.0"}`.
    * `document_currency_code` — defaults to `Currency.MYR`.
    * `accounting_supplier_party`, `accounting_customer_party`.
    * `legal_monetary_total`, `tax_total`, `invoice_lines >= 1`.
    """

    # Canonical UBL XML tag name. The envelope builders read this to set
    # the outer key + default-namespace URL.
    xml_tag_name: ClassVar[str] = "Invoice"

    id: str = Field(serialization_alias="ID")
    issue_date_time: datetime = Field(serialization_alias="IssueDateTime")
    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.INVOICE, serialization_alias="InvoiceTypeCode"
    )
    invoice_type_code_list_version_id: str = Field(default="1.0", exclude=True, repr=False)
    document_currency_code: Currency | str = Field(
        default=Currency.MYR, serialization_alias="DocumentCurrencyCode"
    )
    tax_currency_code: Currency | str | None = Field(
        default=None, serialization_alias="TaxCurrencyCode"
    )
    accounting_cost_code: str | None = Field(default=None, serialization_alias="AccountingCostCode")
    buyer_reference: str | None = Field(default=None, serialization_alias="BuyerReference")
    invoice_period: InvoicePeriod | None = Field(default=None, serialization_alias="InvoicePeriod")
    order_reference: OrderReference | None = Field(
        default=None, serialization_alias="OrderReference"
    )
    billing_references: list[BillingReference] = Field(
        default_factory=list, serialization_alias="BillingReference"
    )
    additional_document_references: list[AdditionalDocumentReference] = Field(
        default_factory=list, serialization_alias="AdditionalDocumentReference"
    )
    # Signature placeholder (only requested when the document is to be signed,
    # populated by the Phase 4 signer with signatureId=...Invoice and
    # signatureMethod=urn:oasis:names:specification:ubl:dsig:enveloped:xades).
    signature_id: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    signature_method: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    # UBLOpen scope: ubl_extensions is populated only by Phase 4.
    ubl_extensions: Any | None = Field(default=None, exclude=True, repr=False)
    accounting_supplier_party: AccountingParty = Field(
        serialization_alias="AccountingSupplierParty"
    )
    accounting_customer_party: AccountingParty = Field(
        serialization_alias="AccountingCustomerParty"
    )
    payee_party: Party | None = Field(default=None, serialization_alias="PayeeParty")
    delivery: Delivery | None = Field(default=None, serialization_alias="Delivery")
    payment_means: PaymentMeans | None = Field(default=None, serialization_alias="PaymentMeans")
    payment_terms: PaymentTerms | None = Field(default=None, serialization_alias="PaymentTerms")
    prepaid_payment: PrepaidPayment | None = Field(
        default=None, serialization_alias="PrepaidPayment"
    )
    allowance_charges: list[AllowanceCharge] = Field(
        default_factory=list, serialization_alias="AllowanceCharge"
    )
    tax_exchange_rate: TaxExchangeRate | None = Field(
        default=None, serialization_alias="TaxExchangeRate"
    )
    tax_total: TaxTotal = Field(serialization_alias="TaxTotal")
    legal_monetary_total: LegalMonetaryTotal = Field(serialization_alias="LegalMonetaryTotal")
    invoice_lines: list[InvoiceLine] = Field(
        default_factory=list, serialization_alias="InvoiceLine"
    )

    @field_validator("invoice_type_code", mode="before")
    @classmethod
    def _coerce_type_code(cls, v: object) -> object:
        if isinstance(v, str) and v:
            try:
                return DocumentTypeCode.coerce(v)
            except ValueError:
                return v
        return v

    @field_validator("document_currency_code", "tax_currency_code", mode="before")
    @classmethod
    def _coerce_currency(cls, v: object) -> object:
        if isinstance(v, str) and v:
            try:
                return Currency(v)
            except ValueError:
                return v
        return v

    @field_validator("invoice_lines")
    @classmethod
    def _at_least_one_line(cls, v: list[InvoiceLine]) -> list[InvoiceLine]:
        if not v:
            raise ValueError("Invoice.invoice_lines must contain at least one InvoiceLine")
        return v

    @model_validator(mode="after")
    def _requires_core(self) -> Invoice:
        self._require_core_fields()
        self._stamp_document_currency()
        return self

    def _require_core_fields(self) -> None:
        """Enforce required core invoice fields (no silent zero-fill)."""
        required: list[tuple[object, str]] = [
            (self.id, "id"),
            (self.issue_date_time, "issue_date_time"),
            (self.invoice_type_code, "invoice_type_code"),
            (self.document_currency_code, "document_currency_code"),
            (self.accounting_supplier_party, "accounting_supplier_party"),
            (self.accounting_customer_party, "accounting_customer_party"),
            (self.legal_monetary_total, "legal_monetary_total"),
            (self.tax_total, "tax_total"),
        ]
        for value, name in required:
            if not value:
                raise ValueError(f"Invoice.{name} is required")
        # invoice_lines is enforced by the field validator above.

    def _stamp_document_currency(self) -> None:
        """Stamp the document's currency_code into every per-amount currency_id
        attribute (defaults to MYR when unset)."""
        cid = (
            self.document_currency_code.value
            if isinstance(self.document_currency_code, Currency)
            else self.document_currency_code
        )

        def _or_set(target: Any, attr: str) -> None:
            if getattr(target, attr) is None:
                setattr(target, attr, cid)

        _or_set(self.legal_monetary_total, "currency_id")
        _or_set(self.tax_total, "rounding_amount_currency_id")
        for ts in self.tax_total.tax_sub_totals:
            _or_set(ts, "taxable_amount_currency_id")
            _or_set(ts, "tax_amount_currency_id")

        for line in self.invoice_lines:
            _or_set(line, "line_extension_amount_currency_id")
            _or_set(line.price, "price_amount_currency_id")
            _or_set(line.item_price_extension, "amount_currency_id")
            for ts in line.tax_total.tax_sub_totals:
                _or_set(ts, "taxable_amount_currency_id")
                _or_set(ts, "tax_amount_currency_id")
            for ac in line.allowance_charges:
                _or_set(ac, "amount_currency_id")

        for ac in self.allowance_charges:
            _or_set(ac, "amount_currency_id")
        if self.prepaid_payment is not None:
            _or_set(self.prepaid_payment, "paid_amount_currency_id")
        if self.payment_terms is not None and self.payment_terms.amount is not None:
            _or_set(self.payment_terms, "amount_currency_id")

    @property
    def is_signed(self) -> bool:
        """True when the document is intended to be signed (Phase 4 populates
        the UBLExtensions block; Phase 3b always sets the signature_id/method
        placeholders)."""
        return bool(self.signature_id and self.signature_method)

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        def _dl(model: _UblModel | None) -> dict[str, Any] | None:
            if model is None:
                return None
            return model.model_dump(by_alias=True, exclude_none=True)

        def _dl_list(seq: list[Any]) -> list[dict[str, Any]]:
            return [item.model_dump(by_alias=True, exclude_none=True) for item in seq]

        out: dict[str, Any] = {
            "ID": _leaf(self.id),
            "IssueDate": _leaf(self.issue_date_time.strftime("%Y-%m-%d")),
            "IssueTime": _leaf(self.issue_date_time.strftime("%H:%M:%SZ")),
        }

        if self.invoice_type_code is not None:
            tc_val = (
                self.invoice_type_code.value
                if isinstance(self.invoice_type_code, DocumentTypeCode)
                else self.invoice_type_code
            )
            out["InvoiceTypeCode"] = _leaf(
                tc_val, listVersionID=self.invoice_type_code_list_version_id
            )

        doc_cc = (
            self.document_currency_code.value
            if isinstance(self.document_currency_code, Currency)
            else self.document_currency_code
        )
        out["DocumentCurrencyCode"] = _leaf(doc_cc)

        if self.tax_currency_code is not None:
            tc_cc = (
                self.tax_currency_code.value
                if isinstance(self.tax_currency_code, Currency)
                else self.tax_currency_code
            )
            out["TaxCurrencyCode"] = _leaf(tc_cc)

        if self.accounting_cost_code is not None:
            out["AccountingCostCode"] = _leaf(self.accounting_cost_code)
        if self.buyer_reference is not None:
            out["BuyerReference"] = _leaf(self.buyer_reference)

        # Optional submodel block (preserves elision + write order).
        opt_blocks: dict[str, Any] = {
            "InvoicePeriod": _dl(self.invoice_period),
            "OrderReference": _dl(self.order_reference),
            "BillingReference": (
                _dl_list(self.billing_references) if self.billing_references else None
            ),
            "AdditionalDocumentReference": (
                _dl_list(self.additional_document_references)
                if self.additional_document_references
                else None
            ),
        }
        if (
            self.ubl_extensions is not None
            and self.signature_id is not None
            and self.signature_method is not None
        ):
            opt_blocks["Signature"] = {
                "ID": [_leaf(self.signature_id)],
                "SignatureMethod": [_leaf(self.signature_method)],
            }
        opt_blocks.update(
            {
                "PayeeParty": _dl(self.payee_party),
                "Delivery": _dl(self.delivery),
                "PaymentMeans": _dl(self.payment_means),
                "PaymentTerms": _dl(self.payment_terms),
                "PrepaidPayment": _dl(self.prepaid_payment),
                "AllowanceCharge": _dl_list(self.allowance_charges)
                if self.allowance_charges
                else None,
                "TaxExchangeRate": _dl(self.tax_exchange_rate),
            }
        )
        # Emit the optional blocks in canonical write-order.
        for key in (
            "InvoicePeriod",
            "OrderReference",
            "BillingReference",
            "AdditionalDocumentReference",
            "Signature",
            "PayeeParty",
            "Delivery",
            "PaymentMeans",
            "PaymentTerms",
            "PrepaidPayment",
            "AllowanceCharge",
            "TaxExchangeRate",
        ):
            v = opt_blocks.get(key)
            if v is not None:
                out[key] = v

        # Always-present submodels.
        out["AccountingSupplierParty"] = _dl(self.accounting_supplier_party)
        out["AccountingCustomerParty"] = _dl(self.accounting_customer_party)
        out["TaxTotal"] = _dl(self.tax_total)
        out["LegalMonetaryTotal"] = _dl(self.legal_monetary_total)
        out["InvoiceLine"] = _dl_list(self.invoice_lines)
        return out


# Late import to satisfy the Invoice.invoice_lines forward reference.
from .line import InvoiceLine  # noqa: E402

Invoice.model_rebuild()
