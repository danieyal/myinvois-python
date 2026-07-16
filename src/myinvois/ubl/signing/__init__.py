"""Digital-signing utilities for the MyInvois / LHDN e-Invoice SDK.

This subpackage mirrors PHP's ``AbstractDocumentBuilder::signDocument``
logic: it accepts an unsigned UBL document (bytes/str for XML, dict for
JSON), resolves the supplied certificate bundle, computes the four
cryptographic primitives needed by XAdES (Reference1 DocDigest, Reference2
PropsDigest, CertDigest, SignatureValue), and stitches the full
``ext:UBLExtensions`` / ``cac:Signature`` block back into the serialized
document.

For JSON, the equivalent sibling structure is the ``"UBLExtensions"`` /
``"Signature"`` keys inserted directly into the Invoice's JSON dictionary
(per PHP ``JsonDocumentBuilder::build`` + ``Invoice::jsonSerialize``).

Public surface:

* ``XmlSigner`` — sign a UBL XML document and return the signed XML.
* ``JsonSigner`` — sign a UBL JSON document and return the signed JSON.
* ``SignerDigests`` — frozen dataclass exposing the 4 primitives used
  during signing (also useful for diagnostic inspection).
"""

from __future__ import annotations

from ._digests import SignerDigests
from ._json import JsonSigner
from ._xml import XmlSigner

__all__ = ["JsonSigner", "SignerDigests", "XmlSigner"]
