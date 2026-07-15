"""UBL 2.1 namespace constants & envelope metadata for the MyInvois LHDN wire format.

.. note::

    These mirror the PHP SDK's ``Klsheng\\Myinvois\\Ubl\\Constant\\UblSpecifications``
    and the TypeScript ``myinvois-client`` definitions exactly. The wire-form
    envelope builder (Phase 3c) uses these URLs verbatim — must NOT be edited
    or signature digests computed over the resulting JSON/XML will diverge from
    LHDN's expected canonical form.
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
#: Maps the canonical PHP ``Invoice::$xmlTagName`` to the ``_D`` value emitted
#: in the JSON envelope (``urn:oasis:names:specification:ubl:schema:xsd:<Tag>-2``).
ENVELOPE_DOCUMENT_TAGS: Final[dict[str, str]] = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "DebitNote": "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2",
    "RefundNote": "urn:oasis:names:specification:ubl:schema:xsd:RefundNote-2",
    "SelfBilledInvoice": "urn:oasis:names:specification:ubl:schema:xsd:SelfBilledInvoice-2",
    "SelfBilledCreditNote": ("urn:oasis:names:specification:ubl:schema:xsd:SelfBilledCreditNote-2"),
    "SelfBilledDebitNote": ("urn:oasis:names:specification:ubl:schema:xsd:SelfBilledDebitNote-2"),
    "SelfBilledRefundNote": ("urn:oasis:names:specification:ubl:schema:xsd:SelfBilledRefundNote-2"),
}

#: e-Invoice v1.0 (unsigned) vs v1.1 (digitally signed). The Invoice's
#: ``invoice_type_code_list_version_id`` carries the same string at the
#: document level; this tuple exists alongside the envelope metadata so a
#: single ``JsonEnvelopeBuilder(...).version`` kwarg can express both shapes
#: once Phase 4 (XAdES-signed) lands.
UBL_INVOICE_FORMAT_VERSIONS: Final[tuple[str, ...]] = ("1.0", "1.1")
