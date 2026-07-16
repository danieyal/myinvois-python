"""``XmlSigner`` — XAdES-enveloped RSA-PKCS1v15-SHA256 XML signer for UBL
invoices.

Produces byte-for-byte parity with PHP's ``XmlDocumentBuilder::signDocument``
output (verified against the golden fixture
``tests/fixtures/golden_invoice_signed.xml``).

Pipeline (mirrors PHP ``AbstractDocumentBuilder::createSignature`` +
``XmlDocumentBuilder::build`` invoked AFTER ``isSigned=true``):

1. Resolve the ``CertConfig`` once into a ``LoadedCert`` byte bundle.
2. Compute ``doc_digest`` = ``base64(SHA256(unsigned_xml_bytes))``.
3. Compute ``signature_value`` = ``base64(RSA-PKCS1v15-SHA256(unsigned_xml_bytes))``.
4. Compute ``cert_digest`` = ``base64(SHA256(cert_der_bytes))``.
5. Compute ``props_digest`` = PropsDigest of the ``<xades:SignedProperties>``
   subtree (see ``_propsdigest_xml``).
6. Splice the ``<ext:UBLExtensions>`` block right after the opening
   ``<Invoice ...>`` tag.
7. Splice the ``<cac:Signature>`` sibling right after
   ``<cbc:DocumentCurrencyCode>...</cbc:DocumentCurrencyCode>``.
8. Flip ``InvoiceTypeCode['listVersionID']`` from ``"1.0"`` to ``"1.1"``.

NOTE: PHP applies ``replaceCommonAttributes`` and ``str_replace(["\\n","\\t","\\r"], ...)``
on the final document, but these are no-ops once the UBLExtensions block
template is emitted (per ``_xml_block``) with the 5 xmlns-injections already
baked in, AND the envelope-builder output is whitespace-free to begin with.
Byte-for-byte parity with the PHP golden fixture is retained without the
final pass; the unit tests assert this invariant.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime
from typing import TYPE_CHECKING

from ._cert import (
    LoadedCert,
    cert_digest_b64,
    issuer_name_string,
    load_cert_config,
    serial_number_string,
    sign_sha256,
)
from ._digests import SignerDigests
from ._propsdigest_xml import compute_props_digest_xml
from ._xml_block import build_cac_signature_block, build_xml_ublextensions_block

if TYPE_CHECKING:
    from myinvois.config import CertConfig


def _format_signing_time(signing_time: datetime) -> str:
    """Format ``signing_time`` as ``Y-m-d\\TH:i:s\\Z`` (PHP's literal escape).

    e.g. ``2024-01-15T10:00:00Z``. Pinned to UTC; seconds resolution only
    (no microseconds). Matches PHP's
    ``$dt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\\TH:i:s\\Z')``.
    """
    utc = signing_time.astimezone()
    if utc.tzinfo is None:
        raise ValueError("signing_time must be timezone-aware (use datetime(..., tzinfo=UTC))")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


class XmlSigner:
    """End-to-end UBL 2.1 + XAdES-enveloped XML signer.

    Constructed once per ``CertConfig``; ``sign`` may be called multiple
    times across different documents (the cert bundle is reused).
    """

    def __init__(self, cert_config: CertConfig) -> None:
        self._cert_config = cert_config
        self._loaded: LoadedCert | None = None

    # -- public API -------------------------------------------------------

    def sign(self, document: bytes | str, *, signing_time: datetime) -> bytes:
        """Return the signed XML document as bytes (byte-for-byte parity
        with the PHP-generated fixture).
        """
        if isinstance(document, str):
            document_bytes = document.encode("utf-8")
        else:
            document_bytes = document

        loaded = self._ensure_loaded()
        issuer = issuer_name_string(loaded.cert)
        serial = serial_number_string(loaded.cert)
        cert_digest = cert_digest_b64(loaded.cert)
        signing_time_str = _format_signing_time(signing_time)

        doc_digest_b64 = base64.b64encode(hashlib.sha256(document_bytes).digest()).decode("ascii")
        props_digest_b64 = compute_props_digest_xml(issuer, serial, cert_digest, signing_time_str)
        sig_value_b64 = base64.b64encode(sign_sha256(document_bytes, loaded.private_key)).decode(
            "ascii"
        )
        cert_pem_raw = loaded.raw_pem_cert

        ubl_extensions_block = build_xml_ublextensions_block(
            issuer_name=issuer,
            serial_number_hex=serial,
            cert_digest_b64=cert_digest,
            signature_value_b64=sig_value_b64,
            doc_digest_b64=doc_digest_b64,
            props_digest_b64=props_digest_b64,
            signing_time_str=signing_time_str,
            cert_pem_raw=cert_pem_raw,
        )

        text = document_bytes.decode("utf-8")
        # Sanity check that the document is unsigned (no UBLExtensions injected yet).
        # PHP allows for a redundant idempotency re-sign, but we treat the second
        # call as a programmer error here.
        if "<ext:UBLExtensions>" in text:
            raise ValueError("Document has already been signed (contains <ext:UBLExtensions>)")
        # Splice the UBLExtensions block right after the opening <Invoice ...> tag.
        opening_tag_end = text.find(">") + 1  # closing > of <Invoice xmlns=...>
        if opening_tag_end == 0:
            raise ValueError("Cannot locate root opening tag in document")
        text = text[:opening_tag_end] + ubl_extensions_block + text[opening_tag_end:]

        # Splice the <cac:Signature> sibling right after <cbc:DocumentCurrencyCode>
        # (and not after InvoiceTypeCode — DocumentCurrencyCode is its next sibling per PHP).
        cdc_marker = "</cbc:DocumentCurrencyCode>"
        cdc_idx = text.find(cdc_marker)
        if cdc_idx == -1:
            raise ValueError("Cannot locate <cbc:DocumentCurrencyCode> for cac:Signature splice")
        cdc_end = cdc_idx + len(cdc_marker)
        text = text[:cdc_end] + build_cac_signature_block() + text[cdc_end:]

        # Flip listVersionID="1.0" -> "1.1" (PHP's hard-coded mutation).
        text = text.replace('listVersionID="1.0"', 'listVersionID="1.1"')

        return text.encode("utf-8")

    def digests(self, document: bytes | str, *, signing_time: datetime) -> SignerDigests:
        """Return the four cryptographic primitives without weaving them into
        the final signed document. Tests can localize a drift across the
        primitives individually (see ``tests/unit/test_signer_xml.py``).
        """
        if isinstance(document, str):
            document_bytes = document.encode("utf-8")
        else:
            document_bytes = document

        loaded = self._ensure_loaded()
        issuer = issuer_name_string(loaded.cert)
        serial = serial_number_string(loaded.cert)
        cert_digest = cert_digest_b64(loaded.cert)
        signing_time_str = _format_signing_time(signing_time)

        doc_digest_b64 = base64.b64encode(hashlib.sha256(document_bytes).digest()).decode("ascii")
        props_digest_b64 = compute_props_digest_xml(issuer, serial, cert_digest, signing_time_str)
        sig_value_b64 = base64.b64encode(sign_sha256(document_bytes, loaded.private_key)).decode(
            "ascii"
        )

        return SignerDigests(
            reference_1_value=doc_digest_b64,
            reference_2_value=props_digest_b64,
            cert_digest=cert_digest,
            signature_value=sig_value_b64,
        )

    # -- private ----------------------------------------------------------

    def _ensure_loaded(self) -> LoadedCert:
        if self._loaded is None:
            self._loaded = load_cert_config(self._cert_config)
        return self._loaded


__all__ = ["XmlSigner"]
