"""The named document classes fix their type code and nothing else.

The failure these classes exist to prevent: every MyInvois document rides the
same ``Invoice`` envelope, so a credit note built with :class:`Invoice` and a
forgotten ``invoice_type_code`` is a structurally valid, submittable document
claiming to be an invoice. LHDN accepts it, and the payload is otherwise
identical, so nothing downstream reveals the mistake.

These tests pin both halves of the guarantee:

* the type code is correct and cannot be omitted or contradicted; and
* nothing *else* changes -- the serialized bytes still match the reference
  output for the corresponding raw type code, so the safety is free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from myinvois.codes import DocumentTypeCode
from myinvois.ubl import (
    CreditNote,
    DebitNote,
    Invoice,
    RefundNote,
    SelfBilledCreditNote,
    SelfBilledDebitNote,
    SelfBilledInvoice,
    SelfBilledRefundNote,
)
from myinvois.ubl.builders import JsonEnvelopeBuilder, XmlEnvelopeBuilder

from .test_envelope_builder import _sample_invoice

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

#: (class, expected wire code) for every named document type.
DOCUMENT_CLASSES = [
    (CreditNote, "02"),
    (DebitNote, "03"),
    (RefundNote, "04"),
    (SelfBilledInvoice, "11"),
    (SelfBilledCreditNote, "12"),
    (SelfBilledDebitNote, "13"),
    (SelfBilledRefundNote, "14"),
]


def _fields_without_type_code() -> dict[str, Any]:
    """The shared sample document, minus the type code the class supplies."""
    fields = dict(_sample_invoice())
    fields.pop("invoice_type_code", None)
    return fields


# ---------------------------------------------------------------------------
# The type code cannot be omitted or contradicted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("cls", "code"), DOCUMENT_CLASSES)
class TestTypeCodeIsFixedByTheClass:
    def test_type_code_is_set_without_the_caller_supplying_it(
        self, cls: type[Invoice], code: str
    ) -> None:
        doc = cls(**_fields_without_type_code())
        assert doc.invoice_type_code == DocumentTypeCode(code)

    def test_type_code_reaches_the_wire(self, cls: type[Invoice], code: str) -> None:
        doc = cls(**_fields_without_type_code())
        expected = f'<cbc:InvoiceTypeCode listVersionID="1.0">{code}</cbc:InvoiceTypeCode>'
        assert expected in XmlEnvelopeBuilder(doc).build_xml()

    def test_a_conflicting_type_code_is_rejected(self, cls: type[Invoice], code: str) -> None:
        # `CreditNote(invoice_type_code="01")` is almost certainly a copy-paste
        # bug. Silently honouring it would produce exactly the wrong-type
        # document these classes exist to prevent.
        wrong = "01" if code != "01" else "02"
        with pytest.raises(ValueError, match="document type"):
            cls(**_fields_without_type_code(), invoice_type_code=wrong)

    def test_its_own_type_code_is_accepted_when_passed_explicitly(
        self, cls: type[Invoice], code: str
    ) -> None:
        # Redundant but not wrong, and it must not be punished -- round-tripping
        # a dumped document back through the class would otherwise fail.
        doc = cls(**_fields_without_type_code(), invoice_type_code=code)
        assert doc.invoice_type_code == DocumentTypeCode(code)

    def test_the_enum_member_is_accepted_too(self, cls: type[Invoice], code: str) -> None:
        doc = cls(**_fields_without_type_code(), invoice_type_code=DocumentTypeCode(code))
        assert doc.invoice_type_code == DocumentTypeCode(code)


# ---------------------------------------------------------------------------
# Nothing else changes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("cls", "code"), DOCUMENT_CLASSES)
class TestSerializationIsUnchanged:
    def test_still_uses_the_invoice_envelope(self, cls: type[Invoice], code: str) -> None:
        # The whole point: these are ergonomic wrappers, not different
        # documents. A per-class root element would be rejected by LHDN.
        assert cls.xml_tag_name == "Invoice"
        xml = XmlEnvelopeBuilder(cls(**_fields_without_type_code())).build_xml()
        assert xml.startswith("<Invoice xmlns=")

    def test_bytes_match_the_equivalent_raw_invoice(self, cls: type[Invoice], code: str) -> None:
        # An Invoice with the type code set by hand must serialize identically
        # to the named class, or the wrapper is doing something extra.
        raw = _sample_invoice()
        raw.invoice_type_code = code
        named = cls(**_fields_without_type_code())

        assert XmlEnvelopeBuilder(named).build_xml() == XmlEnvelopeBuilder(raw).build_xml()
        assert JsonEnvelopeBuilder(named).build_json() == JsonEnvelopeBuilder(raw).build_json()


class TestCreditNoteMatchesTheReferenceGolden:
    """Anchor one named class to reference-generated bytes, not just to us."""

    def test_credit_note_xml_matches_reference(self) -> None:
        golden = (_FIXTURES / "golden_creditnote_unsigned.xml").read_text(encoding="utf-8")
        assert XmlEnvelopeBuilder(CreditNote(**_fields_without_type_code())).build_xml() == golden

    def test_credit_note_json_matches_reference(self) -> None:
        golden = (_FIXTURES / "golden_creditnote_unsigned.json").read_text(encoding="utf-8")
        assert JsonEnvelopeBuilder(CreditNote(**_fields_without_type_code())).build_json() == golden


# ---------------------------------------------------------------------------
# Coverage and typing
# ---------------------------------------------------------------------------


def test_every_non_invoice_type_code_has_a_named_class() -> None:
    # Guards the gap this module closes: a code reachable only by remembering
    # to pass it by hand is the hazard, so every one must have a class.
    covered = {code for _, code in DOCUMENT_CLASSES} | {"01"}
    assert covered == {c.value for c in DocumentTypeCode}


@pytest.mark.parametrize(("cls", "code"), DOCUMENT_CLASSES)
def test_named_classes_are_invoices(cls: type[Invoice], code: str) -> None:
    # Anything accepting an Invoice -- signers, builders, submission helpers --
    # must accept these unchanged.
    assert issubclass(cls, Invoice)
    assert isinstance(cls(**_fields_without_type_code()), Invoice)
