"""UBL 2.1 namespace constants & envelope metadata for the MyInvois LHDN wire format.

.. note::

    These mirror the TypeScript ``myinvois-client`` definitions exactly. The
    wire-form envelope builder uses these URLs verbatim — must NOT be edited
    or signature digests computed over the resulting JSON/XML will diverge
    from LHDN's expected canonical form.
"""

from __future__ import annotations

from typing import Final

#: Mapping from short-name to the UBL 2.1 CommonAggregateComponents-2 /
#: CommonBasicComponents-2 / CommonExtensionComponents-2 namespace URL.
UBL_NAMESPACES: Final[dict[str, str]] = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
}

#: Full default-namespace URL per supported UBL document xmlTagName.
#:
#: **``Invoice`` is the only valid entry, for every one of the eight MyInvois
#: document types.** MyInvois does not use UBL's per-document root elements: a
#: credit note is not ``<CreditNote>`` in the ``CreditNote-2`` namespace. Every
#: type rides the ``Invoice`` envelope and is distinguished only by
#: ``cbc:InvoiceTypeCode`` (``01``-``04``, ``11``-``14``). The reference
#: implementation overrides the UBL default back to ``Invoice`` explicitly, and
#: does the same for ``CreditNoteLine`` -> ``InvoiceLine`` and
#: ``CreditedQuantity`` -> ``InvoicedQuantity``.
#:
#: This previously listed ``CreditNote-2``, ``SelfBilledInvoice-2`` and friends.
#: They were unreachable -- ``xml_tag_name`` is only ever ``"Invoice"`` -- but
#: they encoded the wrong belief, and wiring them up would have produced
#: documents LHDN rejects. Pinned by ``tests/unit/test_document_type_parity.py``.
ENVELOPE_DOCUMENT_TAGS: Final[dict[str, str]] = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
}

#: e-Invoice v1.0 (unsigned) vs v1.1 (digitally signed). The Invoice's
#: ``invoice_type_code_list_version_id`` carries the same string at the
#: document level; this tuple exists alongside the envelope metadata so a
#: single ``JsonEnvelopeBuilder(...).version`` kwarg can express both shapes
#: once Phase 4 (XAdES-signed) lands.
UBL_INVOICE_FORMAT_VERSIONS: Final[tuple[str, ...]] = ("1.0", "1.1")
