"""XML PropsDigest helper — replicates ``XmlDocumentBuilder::getPropsDigestHash``.

Produces the SHA-256-base64 hash of the *SignedProperties* subtree (with five
``xmlns:ds`` / ``xmlns:xades`` declarations injected to keep parity with the
PHP ``str_replace``-based ``replaceCommonAttributes`` step).

Used both as:

* ``Reference2.DigestValue`` in the final signed XML (the enqueued Promise digest);
* the input hash for the propsDigest component computed during the digest
  Yan ``SignerDigests`` aggregator.
"""

from __future__ import annotations

import base64
import hashlib

from ._common_attrs import replace_common_attributes

# Namespace prefixes used by Sabre during the propsdigest block serialization.
_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"

# The wrapper Sabre emits around the bare QualifyingProperties::xmlSerialize
# output. ``$service->write('{xades-ns}root', $qp)`` during the getPropsDigestHash
# step produces this wrapper, which is later stripped AFTER C14N.
_PROPSDIGEST_WRAPPER_OPEN = (
    '<xades:root xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
    ' xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">'
)
_PROPSDIGEST_WRAPPER_CLOSE = "</xades:root>"

_SIGNED_PROPERTIES_OPEN = '<xades:SignedProperties Id="id-xades-signed-props'
_SIGNED_PROPERTIES_OPEN_END = '">'


def compute_props_digest_xml(
    issuer_name: str,
    serial_number_hex: str,
    cert_digest_b64: str,
    signing_time_str: str,
) -> str:
    """Replicate ``XmlDocumentBuilder::getPropsDigestHash`` byte-for-byte.

    Returns the base64-encoded SHA-256 of the c14n'd 5-attribute-injected
    ``<xades:SignedProperties>`` subtree.
    """
    props_xml = _build_signed_properties_xml(
        issuer_name=issuer_name,
        serial_number_hex=serial_number_hex,
        cert_digest_b64=cert_digest_b64,
        signing_time_str=signing_time_str,
    )
    return _hash_props_block(props_xml)


def _build_signed_properties_xml(
    issuer_name: str,
    serial_number_hex: str,
    cert_digest_b64: str,
    signing_time_str: str,
) -> str:
    """Build the ``<xades:SignedProperties>`` block as Sabre would emit it,
    wrapped in the Sabre ``<xades:root>`` wrapper used during getPropsDigestHash
    and *before* the canonicalization step.
    """
    body = (
        f'<xades:SignedProperties Id="id-xades-signed-props">'
        f"<xades:SignedSignatureProperties>"
        f"<xades:SigningTime>{signing_time_str}</xades:SigningTime>"
        f"<xades:SigningCertificate>"
        f"<xades:Cert>"
        f"<xades:CertDigest>"
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></ds:DigestMethod>'
        f"<ds:DigestValue>{cert_digest_b64}</ds:DigestValue>"
        f"</xades:CertDigest>"
        f"<xades:IssuerSerial>"
        f"<ds:X509IssuerName>{issuer_name}</ds:X509IssuerName>"
        f"<ds:X509SerialNumber>{serial_number_hex}</ds:X509SerialNumber>"
        f"</xades:IssuerSerial>"
        f"</xades:Cert>"
        f"</xades:SigningCertificate>"
        f"</xades:SignedSignatureProperties>"
        f"</xades:SignedProperties>"
    )
    return _PROPSDIGEST_WRAPPER_OPEN + body + _PROPSDIGEST_WRAPPER_CLOSE


def _hash_props_block(props_xml_with_wrapper: str) -> str:
    """C14N -> strip wrapper -> replace-common-attributes -> SHA256 -> base64."""
    canonicalized = _c14n(props_xml_with_wrapper)
    # Strip the xades:root wrapper (now it has no xmlns:ds declaration
    # after C14N pruned the redundant namespace).
    body = _strip_root_wrapper(canonicalized)
    # Apply the 5 xmlns-injection replacements.
    injected = replace_common_attributes(body)
    # Strip whitespace control chars (PHP's behavior: hash the str_replace'd
    # string verbatim).
    final_bytes = injected.encode("utf-8")
    return base64.b64encode(hashlib.sha256(final_bytes).digest()).decode("ascii")


def _c14n(xml_string: str) -> str:
    """Canonicalize XML using lxml (does NOT prune the redundant
    ``xmlns:ds`` declaration present on the wrapper? verify behavior is
    the same as PHP DOMDocument::C14N()).
    """
    from lxml import etree

    # Parse defensively — the wrapper root is a single element with two
    # namespace declarations; lxml will recognize both.
    tree = etree.fromstring(xml_string.encode("utf-8"))
    result = etree.tostring(tree, method="c14n", with_comments=False).decode("utf-8")
    assert isinstance(result, str)
    return result


def _strip_root_wrapper(c14n: str) -> str:
    """Strip the ``<?xml ...?>`` prolog if present and the ``<xades:root ...>``,
    ``</xades:root>`` wrapper tags.
    """
    if c14n.startswith("<?xml"):
        # Strip the prolog line.
        end = c14n.find("?>") + 2
        c14n = c14n[end:]
    c14n = c14n.lstrip("\n")
    # Strip the wrapper opening tag.
    if c14n.startswith(_PROPSDIGEST_WRAPPER_OPEN):
        c14n = c14n[len(_PROPSDIGEST_WRAPPER_OPEN) :]
    # Strip the wrapper closing tag.
    if c14n.endswith(_PROPSDIGEST_WRAPPER_CLOSE):
        c14n = c14n[: -len(_PROPSDIGEST_WRAPPER_CLOSE)]
    return c14n


__all__ = ["compute_props_digest_xml"]
