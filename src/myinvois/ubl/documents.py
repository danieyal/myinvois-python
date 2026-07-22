"""Named document classes for the seven non-Invoice MyInvois document types.

Every MyInvois document rides the same ``Invoice`` envelope and is
distinguished *only* by ``cbc:InvoiceTypeCode``. A credit note and an invoice
are byte-identical apart from two characters (see
``tests/unit/test_document_type_parity.py``).

That makes the type code uniquely dangerous to get wrong. ``Invoice`` defaults
it to ``01``, so building a credit note with :class:`Invoice` and forgetting
the field yields a structurally valid, submittable document that claims to be
an invoice. LHDN accepts it. Nothing downstream reveals the mistake, because
there is nothing else to reveal -- the rest of the payload is identical.

These classes remove that failure mode: the type code is fixed by the class and
cannot be omitted. Passing a conflicting one raises rather than silently
winning, so ``CreditNote(invoice_type_code="01")`` -- almost certainly a
copy-paste bug -- fails at construction.

Everything else is inherited from :class:`~myinvois.ubl.invoice.Invoice`, and
serialization is unchanged: ``xml_tag_name`` stays ``"Invoice"`` for all of
them, exactly as MyInvois requires.

    >>> from myinvois.ubl import CreditNote
    >>> note = CreditNote(id="CN-0001", ...)   # doctest: +SKIP
    >>> note.invoice_type_code
    <DocumentTypeCode.CREDIT_NOTE: '02'>

**Self-billed documents.** In a self-billed arrangement the *buyer* issues the
document on the supplier's behalf, so the party roles are the reverse of the
commercial direction most people picture. These classes deliberately do **not**
transpose ``accounting_supplier_party`` and ``accounting_customer_party`` for
you: silently swapping the parties on a tax document would be a far worse
failure than the one this module exists to prevent. Populate them per LHDN's
self-billed rules -- the supplier remains the supplier of the goods or
services.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from myinvois.codes import DocumentTypeCode

from .invoice import Invoice

__all__ = [
    "CreditNote",
    "DebitNote",
    "RefundNote",
    "SelfBilledCreditNote",
    "SelfBilledDebitNote",
    "SelfBilledInvoice",
    "SelfBilledRefundNote",
]


class _FixedTypeDocument(Invoice):
    """An :class:`Invoice` whose ``invoice_type_code`` is fixed by its class.

    Subclasses re-declare ``invoice_type_code`` with their own default, which
    is the single source of truth for the class's type. The validator below is
    what makes the guarantee real: without it a caller could pass a conflicting
    code and quietly get a document of the wrong type from a class that says
    otherwise.
    """

    @model_validator(mode="after")
    def _enforce_fixed_type_code(self) -> _FixedTypeDocument:
        expected = type(self).model_fields["invoice_type_code"].default
        actual = self.invoice_type_code
        try:
            actual_code = DocumentTypeCode.coerce(actual)
        except ValueError:
            actual_code = actual  # type: ignore[assignment]

        if actual_code != expected:
            raise ValueError(
                f"{type(self).__name__} is document type {expected.value!r} "
                f"({expected.name}), but invoice_type_code={actual!r} was given. "
                f"Use Invoice directly if you need an arbitrary type code."
            )
        return self


class CreditNote(_FixedTypeDocument):
    """Credit note — document type ``02``.

    Issued by the supplier to correct or reduce a previously issued invoice.
    Reference the original document via ``billing_references``.
    """

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.CREDIT_NOTE, serialization_alias="InvoiceTypeCode"
    )


class DebitNote(_FixedTypeDocument):
    """Debit note — document type ``03``.

    Issued by the supplier to increase the amount of a previously issued
    invoice. Reference the original document via ``billing_references``.
    """

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.DEBIT_NOTE, serialization_alias="InvoiceTypeCode"
    )


class RefundNote(_FixedTypeDocument):
    """Refund note — document type ``04``.

    Issued by the supplier to confirm a refund of a previously issued invoice.
    Distinct from a credit note: this records money actually returned.
    """

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.REFUND_NOTE, serialization_alias="InvoiceTypeCode"
    )


class SelfBilledInvoice(_FixedTypeDocument):
    """Self-billed invoice — document type ``11``.

    Issued by the *buyer* on the supplier's behalf. See the module docstring:
    the party fields are not transposed for you.
    """

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.SELF_BILLED_INVOICE, serialization_alias="InvoiceTypeCode"
    )


class SelfBilledCreditNote(_FixedTypeDocument):
    """Self-billed credit note — document type ``12``."""

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.SELF_BILLED_CREDIT_NOTE, serialization_alias="InvoiceTypeCode"
    )


class SelfBilledDebitNote(_FixedTypeDocument):
    """Self-billed debit note — document type ``13``."""

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.SELF_BILLED_DEBIT_NOTE, serialization_alias="InvoiceTypeCode"
    )


class SelfBilledRefundNote(_FixedTypeDocument):
    """Self-billed refund note — document type ``14``."""

    invoice_type_code: DocumentTypeCode | str = Field(
        default=DocumentTypeCode.SELF_BILLED_REFUND_NOTE, serialization_alias="InvoiceTypeCode"
    )
