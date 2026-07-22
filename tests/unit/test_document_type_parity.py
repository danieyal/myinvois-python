"""Byte-parity across all eight MyInvois document types.

MyInvois does **not** use UBL's per-document root elements. A Credit Note is
not ``<CreditNote>`` in the ``CreditNote-2`` namespace -- every document type
rides the ``Invoice`` envelope and is distinguished *only* by
``cbc:InvoiceTypeCode``. The reference SDK states this outright::

    class CreditNote extends Invoice {
        public $xmlTagName = 'Invoice'; // MyInvois System re-use back same tag name
        protected $invoiceTypeCode = InvoiceTypeCodes::CREDIT_NOTE;
    }

and likewise maps ``CreditNoteLine`` back to ``InvoiceLine`` and
``CreditedQuantity`` back to ``InvoicedQuantity``.

That makes the type code load-bearing in a way that is easy to get wrong and
expensive to get wrong: the envelope for a credit note is byte-identical to an
invoice apart from two characters. A document that claims the wrong type is a
wrong tax document -- it validates, submits, and is accepted. Nothing else in
the payload would reveal the mistake.

These tests pin that property from both directions:

* against the reference implementation, for a real non-invoice type (02); and
* across all eight codes, asserting the type code is the *only* thing that
  varies -- so a future change that dispatches on document type (a different
  root element, a renamed line element, a different quantity label) fails
  loudly instead of silently emitting documents LHDN rejects.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myinvois.codes import DocumentTypeCode
from myinvois.ubl.builders import JsonEnvelopeBuilder, XmlEnvelopeBuilder

from .test_envelope_builder import _sample_invoice

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

#: Every code MyInvois defines. `01` is the baseline the goldens were built on.
ALL_DOCUMENT_TYPE_CODES = ("01", "02", "03", "04", "11", "12", "13", "14")


def _substitute_once(document: str, marker: str, replacement: str) -> str:
    """Replace ``marker`` exactly once, failing loudly if it is not unique.

    The expected document below is built by string substitution. If the marker
    ever stops matching -- a reordered attribute, a reformatted leaf -- a plain
    ``str.replace`` would quietly do nothing and hand back an expectation that
    no longer means what the test claims. Assert the marker is present exactly
    once so that shows up as a clear failure here rather than as a confusing
    mismatch downstream.
    """
    found = document.count(marker)
    assert found == 1, f"expected exactly one occurrence of {marker!r}, found {found}"
    return document.replace(marker, replacement, 1)


def _xml_for(code: str) -> str:
    invoice = _sample_invoice()
    invoice.invoice_type_code = code
    return XmlEnvelopeBuilder(invoice).build_xml()


def _json_for(code: str) -> str:
    invoice = _sample_invoice()
    invoice.invoice_type_code = code
    return JsonEnvelopeBuilder(invoice).build_json()


# ---------------------------------------------------------------------------
# 1. Anchored against the reference implementation (type 02)
# ---------------------------------------------------------------------------


class TestCreditNoteReferenceParity:
    """`golden_creditnote_unsigned.*` came from the reference SDK's builders.

    Without these, the cross-type tests below would only prove our output is
    self-consistent. These make the claim external: for a genuine non-invoice
    type, our bytes are the reference's bytes.
    """

    def test_credit_note_xml_matches_reference_byte_for_byte(self) -> None:
        golden = (_FIXTURES / "golden_creditnote_unsigned.xml").read_text(encoding="utf-8")
        assert _xml_for(DocumentTypeCode.CREDIT_NOTE) == golden

    def test_credit_note_json_matches_reference_byte_for_byte(self) -> None:
        golden = (_FIXTURES / "golden_creditnote_unsigned.json").read_text(encoding="utf-8")
        assert _json_for(DocumentTypeCode.CREDIT_NOTE) == golden

    def test_credit_note_keeps_the_invoice_root_element(self) -> None:
        # The trap this guards: "a credit note must be <CreditNote>". It must
        # not be -- LHDN rejects that.
        xml = _xml_for(DocumentTypeCode.CREDIT_NOTE)
        assert xml.startswith("<Invoice xmlns=")
        assert "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in xml
        assert "CreditNote-2" not in xml
        assert "<CreditNoteLine" not in xml
        assert "CreditedQuantity" not in xml


# ---------------------------------------------------------------------------
# 2. The type code is the only thing that varies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", ALL_DOCUMENT_TYPE_CODES)
class TestOnlyTheTypeCodeVaries:
    def test_xml_differs_from_invoice_only_in_the_type_code(self, code: str) -> None:
        baseline = (_FIXTURES / "golden_invoice_unsigned.xml").read_text(encoding="utf-8")
        expected = _substitute_once(
            baseline,
            '<cbc:InvoiceTypeCode listVersionID="1.0">01</cbc:InvoiceTypeCode>',
            f'<cbc:InvoiceTypeCode listVersionID="1.0">{code}</cbc:InvoiceTypeCode>',
        )
        assert _xml_for(code) == expected

    def test_json_differs_from_invoice_only_in_the_type_code(self, code: str) -> None:
        baseline = (_FIXTURES / "golden_creditnote_unsigned.json").read_text(encoding="utf-8")
        expected = _substitute_once(
            baseline,
            '"InvoiceTypeCode":[{"_":"02","listVersionID":"1.0"}]',
            f'"InvoiceTypeCode":[{{"_":"{code}","listVersionID":"1.0"}}]',
        )
        assert _json_for(code) == expected

    def test_emitted_type_code_is_exactly_the_requested_one(self, code: str) -> None:
        # A document tagged with the wrong type is a wrong tax document that
        # still validates and submits, so assert the emitted value directly
        # rather than inferring it from the surrounding bytes.
        assert f'<cbc:InvoiceTypeCode listVersionID="1.0">{code}</cbc:InvoiceTypeCode>' in _xml_for(
            code
        )

        parsed = json.loads(_json_for(code))
        assert parsed["Invoice"][0]["InvoiceTypeCode"] == [{"_": code, "listVersionID": "1.0"}]


# ---------------------------------------------------------------------------
# 3. Only the Invoice envelope is permitted
# ---------------------------------------------------------------------------


class TestOnlyTheInvoiceEnvelopeIsPermitted:
    """A non-``Invoice`` root must fail loudly, not be synthesised.

    Both builders used to fall back to the standard UBL pattern
    (``urn:...:xsd:<Tag>-2``) for an unrecognised tag. That turned a mistake
    into a well-formed document in the wrong namespace -- accepted by our
    serializer, rejected by LHDN, with nothing in the payload to explain why.
    """

    def test_envelope_table_lists_only_invoice(self) -> None:
        from myinvois.ubl.builders._specs import ENVELOPE_DOCUMENT_TAGS

        assert set(ENVELOPE_DOCUMENT_TAGS) == {"Invoice"}

    @pytest.mark.parametrize("bogus", ["CreditNote", "SelfBilledInvoice", "Nonsense"])
    @pytest.mark.parametrize(
        "builder_cls,method",
        [(XmlEnvelopeBuilder, "build_xml"), (JsonEnvelopeBuilder, "build_json")],
    )
    def test_non_invoice_root_is_rejected(self, builder_cls: type, method: str, bogus: str) -> None:
        invoice = _sample_invoice()
        # `xml_tag_name` is a ClassVar on the model, so override per-instance
        # through the type to simulate a future document class getting it wrong.
        impostor = type(f"Impostor{bogus}", (type(invoice),), {"xml_tag_name": bogus})
        forged = impostor.model_construct(**dict(invoice))

        with pytest.raises(ValueError, match="Invoice"):
            getattr(builder_cls(forged), method)()


# ---------------------------------------------------------------------------
# 4. The enum agrees with the wire codes
# ---------------------------------------------------------------------------


def test_document_type_code_enum_covers_exactly_these_codes() -> None:
    # Guards the other direction: a code added to the enum without a parity
    # test here, or removed from the enum while still on the wire.
    assert {c.value for c in DocumentTypeCode} == set(ALL_DOCUMENT_TYPE_CODES)


@pytest.mark.parametrize("code", ALL_DOCUMENT_TYPE_CODES)
def test_enum_member_serializes_identically_to_the_raw_string(code: str) -> None:
    # Callers may pass either; they must not diverge.
    assert _xml_for(DocumentTypeCode(code)) == _xml_for(code)
    assert _json_for(DocumentTypeCode(code)) == _json_for(code)
