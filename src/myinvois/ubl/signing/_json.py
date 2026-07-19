"""``JsonSigner`` — XAdES-enveloped RSA-PKCS1v15-SHA256 JSON signer for UBL
invoices.

Produces the canonical LHDN-signed JSON wire form (verified against the
golden fixture ``tests/fixtures/golden_invoice_signed.json``).

Pipeline:

1. Resolve ``CertConfig`` once into a ``LoadedCert`` byte bundle.
2. Compute ``doc_digest`` = ``base64(SHA256(unsigned_json_bytes))``.
3. Compute ``signature_value`` = ``base64(RSA-PKCS1v15-SHA256(unsigned_json_bytes))``.
4. Compute ``cert_digest`` = ``base64(SHA256(cert_der_bytes))``.
5. Compute ``props_digest`` = PropsDigest of the QualifyingProperties dict
   (see ``_propsdigest_json``).
6. Build the canonical JSON signature deep-dict.
7. Splice ``"UBLExtensions"`` (at the head) and ``"Signature"`` (after
   ``DocumentCurrencyCode``) into the Invoice's JSON dict.
8. Flip ``InvoiceTypeCode.listVersionID`` "1.0" -> "1.1".
9. ``str_replace`` Reference2's ``Type`` attribute string
   ``http://www.w3.org/2000/09/xmldsig#SignatureProperties`` ->
   ``http://uri.etsi.org/01903/v1.3.2#SignedProperties`` (hard-coded).
10. ``json.dumps`` with canonical-JSON semantics (``separators=(",",":")`` +
    ``ensure_ascii=False``; forward slashes not escaped), then strip ``\\r\\n``.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ._cert import (
    LoadedCert,
    cert_digest_b64,
    issuer_name_string,
    load_cert_config,
    serial_number_string,
    sign_sha256,
)
from ._digests import SignerDigests
from ._propsdigest_json import compute_props_digest_json

if TYPE_CHECKING:
    from myinvois.config import CertConfig

# Invoice-level signature scope URNs (UBL 2.1 signature spec defaults).
_SIGN_ID = "urn:oasis:names:specification:ubl:signature:1"
_REFERENCED_SIG_ID = "urn:oasis:names:specification:ubl:signature:Invoice"
_SIG_METHOD_URN = "urn:oasis:names:specification:ubl:dsig:enveloped:xades"

_SIGNATURE_METHOD_ALGORITHM = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
_DIGEST_METHOD_ALGORITHM = "http://www.w3.org/2001/04/xmlenc#sha256"
_REF2_TYPE_PRE_REWRITE = "http://www.w3.org/2000/09/xmldsig#SignatureProperties"
_REF2_TYPE_POST_REWRITE = "http://uri.etsi.org/01903/v1.3.2#SignedProperties"


def _format_signing_time(signing_time: datetime) -> str:
    """Format ``signing_time`` as ``Y-m-d\\TH:i:s\\Z``.

    e.g. ``2024-01-15T10:00:00Z``. Pinned to UTC; seconds resolution only
    (no microseconds).
    """
    if signing_time.tzinfo is None:
        raise ValueError("signing_time must be timezone-aware (use datetime(..., tzinfo=UTC))")
    return signing_time.astimezone().strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_encode_canonical(content: Any) -> str:
    """Encode in the canonical JSON wire form: no whitespace, no Unicode
    escapes, forward slashes not backslash-escaped.
    """
    return json.dumps(content, separators=(",", ":"), ensure_ascii=False)


class JsonSigner:
    """End-to-end UBL 2.1 + XAdES-enveloped JSON signer.

    Constructed once per ``CertConfig``; ``sign`` may be called multiple
    times across different documents (the cert bundle is reused)."""

    def __init__(self, cert_config: CertConfig) -> None:
        self._cert_config = cert_config
        self._loaded: LoadedCert | None = None

    # -- public API -------------------------------------------------------

    def sign(self, document: bytes | str, *, signing_time: datetime) -> str:
        """Return the signed JSON document as a string (canonical LHDN wire form)."""
        if isinstance(document, str):
            document_bytes = document.encode("utf-8")
        else:
            document_bytes = document

        loaded = self._ensure_loaded()
        issuer = issuer_name_string(loaded.cert)
        serial = serial_number_string(loaded.cert)
        cert_digest = cert_digest_b64(loaded.cert)
        signing_time_str = _format_signing_time(signing_time)
        cert_pem_raw = loaded.raw_pem_cert

        # Primitives.
        doc_digest_b64 = base64.b64encode(hashlib.sha256(document_bytes).digest()).decode("ascii")
        props_digest_b64 = compute_props_digest_json(issuer, serial, cert_digest, signing_time_str)
        sig_value_b64 = base64.b64encode(sign_sha256(document_bytes, loaded.private_key)).decode(
            "ascii"
        )

        # Build the deep signature dict.
        sig_dict = _build_signature_json_dict(
            issuer_name=issuer,
            serial_number_hex=serial,
            cert_digest_b64=cert_digest,
            signature_value_b64=sig_value_b64,
            doc_digest_b64=doc_digest_b64,
            props_digest_b64=props_digest_b64,
            signing_time_str=signing_time_str,
            cert_pem_raw=cert_pem_raw,
        )

        # Parse the unsigned JSON into a Python tree and splice.
        tree: dict[str, Any] = json.loads(document_bytes.decode("utf-8"))
        # Sanity check.
        if "Invoice" not in tree:
            raise ValueError("Document JSON does not have an 'Invoice' key")
        invoice = tree["Invoice"][0]
        if "UBLExtensions" in invoice:
            raise ValueError("Document has already been signed")
        # Insert UBLExtensions at the very front of the Invoice dict.
        new_invoice: dict[str, Any] = {"UBLExtensions": [_build_ubl_extensions_outer(sig_dict)]}
        # Maintain field order: keys before Signature are inserted in their
        # original order, then Signature goes after DocumentCurrencyCode, then
        # everything after DocumentCurrencyCode.
        inserted_sig = False
        for k, v in invoice.items():
            if k == "InvoiceTypeCode":
                # Copy and apply the 1.0 -> 1.1 flip on the listVersionID attr.
                new_invoice[k] = _flip_invoice_type_code_list_version_id(v)
            else:
                new_invoice[k] = v
            if k == "DocumentCurrencyCode" and not inserted_sig:
                new_invoice["Signature"] = [_build_signature_sibling()]
                inserted_sig = True
        if not inserted_sig:
            raise ValueError(
                "DocumentCurrencyCode key not found in invoice — cannot splice Signature sibling"
            )
        tree["Invoice"][0] = new_invoice

        # Final encoding.
        encoded = _json_encode_canonical(tree)
        # Strip any \r\n line breaks.
        encoded = encoded.replace("\r", "").replace("\n", "")
        # Final flip of Reference2.Type from ds:SignatureProperties to
        # xades:SignedProperties (hard-coded str_replace at end of build()).
        encoded = encoded.replace(
            f'"Type":"{_REF2_TYPE_PRE_REWRITE}"',
            f'"Type":"{_REF2_TYPE_POST_REWRITE}"',
        )
        return encoded

    def digests(self, document: bytes | str, *, signing_time: datetime) -> SignerDigests:
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
        props_digest_b64 = compute_props_digest_json(issuer, serial, cert_digest, signing_time_str)
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


# ---------------------------------------------------------------------------
# Deep dict builders — emit the canonical JSON signature structure.
# ---------------------------------------------------------------------------


def _build_signature_json_dict(
    *,
    issuer_name: str,
    serial_number_hex: str,
    cert_digest_b64: str,
    signature_value_b64: str,
    doc_digest_b64: str,
    props_digest_b64: str,
    signing_time_str: str,
    cert_pem_raw: str,
) -> dict[str, Any]:
    """Build the canonical ``Signature`` sub-dict."""
    signed_info = {
        "SignatureMethod": [{"_": "", "Algorithm": _SIGNATURE_METHOD_ALGORITHM}],
        "Reference": [
            {
                "Id": "id-doc-signed-data",
                "URI": "",
                "DigestMethod": [{"_": "", "Algorithm": _DIGEST_METHOD_ALGORITHM}],
                "DigestValue": [{"_": doc_digest_b64}],
            },
            {
                "Type": _REF2_TYPE_PRE_REWRITE,  # post-str_replace flips this.
                "URI": "#id-xades-signed-props",
                "DigestMethod": [{"_": "", "Algorithm": _DIGEST_METHOD_ALGORITHM}],
                "DigestValue": [{"_": props_digest_b64}],
            },
        ],
    }
    signature_value = {"_": signature_value_b64}
    # KeyInfo includes X509SubjectName + X509IssuerSerial in JSON.
    key_info = {
        "X509Data": [
            {
                "X509Certificate": [{"_": cert_pem_raw}],
                "X509SubjectName": [{"_": issuer_name}],
                "X509IssuerSerial": [
                    {
                        "X509IssuerName": [{"_": issuer_name}],
                        "X509SerialNumber": [{"_": serial_number_hex}],
                    }
                ],
            }
        ]
    }
    qualifying_properties = {
        "Target": "signature",
        "SignedProperties": [
            {
                "Id": "id-xades-signed-props",
                "SignedSignatureProperties": [
                    {
                        "SigningTime": [{"_": signing_time_str}],
                        "SigningCertificate": [
                            {
                                "Cert": [
                                    {
                                        "CertDigest": [
                                            {
                                                "DigestMethod": [
                                                    {"_": "", "Algorithm": _DIGEST_METHOD_ALGORITHM}
                                                ],
                                                "DigestValue": [{"_": cert_digest_b64}],
                                            }
                                        ],
                                        "IssuerSerial": [
                                            {
                                                "X509IssuerName": [{"_": issuer_name}],
                                                "X509SerialNumber": [{"_": serial_number_hex}],
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }
    object_block = {"QualifyingProperties": [qualifying_properties]}

    return {
        "Id": "signature",
        "SignedInfo": [signed_info],
        "SignatureValue": [signature_value],
        "KeyInfo": [key_info],
        "Object": [object_block],
    }


def _build_signature_information_json(signature: dict[str, Any]) -> dict[str, Any]:
    """Build the ``SignatureInformation`` dict."""
    return {
        "ID": [{"_": _SIGN_ID}],
        "ReferencedSignatureID": [{"_": _REFERENCED_SIG_ID}],
        "Signature": [signature],
    }


def _build_ubl_document_signatures_json(signature: dict[str, Any]) -> dict[str, Any]:
    """Build the ``UBLDocumentSignatures`` dict."""
    return {
        "UBLDocumentSignatures": [
            {"SignatureInformation": [_build_signature_information_json(signature)]}
        ]
    }


def _build_ubl_extension_item_json(signature: dict[str, Any]) -> dict[str, Any]:
    """Build the ``UBLExtensionItem`` dict."""
    return {
        "ExtensionURI": [{"_": _SIG_METHOD_URN}],
        "ExtensionContent": [_build_ubl_document_signatures_json(signature)],
    }


def _build_ubl_extensions_outer(signature: dict[str, Any]) -> dict[str, Any]:
    """Build the ``UBLExtensions`` outer wrapper around the list."""
    return {"UBLExtension": [_build_ubl_extension_item_json(signature)]}


def _build_signature_sibling() -> dict[str, Any]:
    """Build the two-element ``Signature`` sibling the Invoice emits when
    UBLExtensions have been attached.
    """
    return {
        "ID": [{"_": _REFERENCED_SIG_ID}],
        "SignatureMethod": [{"_": _SIG_METHOD_URN}],
    }


def _flip_invoice_type_code_list_version_id(
    invoice_type_code_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flip ``listVersionID`` from ``"1.0"`` to ``"1.1"``."""
    out = []
    for entry in invoice_type_code_entries:
        new_entry = dict(entry)
        lv = new_entry.get("listVersionID")
        if lv == "1.0":
            new_entry["listVersionID"] = "1.1"
        out.append(new_entry)
    return out


__all__ = ["JsonSigner"]
