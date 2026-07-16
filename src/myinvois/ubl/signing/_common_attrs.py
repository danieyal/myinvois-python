"""Replication of PHP ``MyInvoisHelper::replaceCommonAttributes``.

MyInvois PHP SDK applies this string-surgery to two XML fragments:

* the *SignedProperties* subtree (used to compute the PropsDigest) — see
  ``XmlDocumentBuilder::getPropsDigestHash``.
* the entire signed document *after* all signature components have been
  stitched in (the final stage of ``AbstractDocumentBuilder::signDocument``).

In both cases the function injects the 5 ``xmlns:ds`` / ``xmlns:xades``
declarations onto elements whose PHP-side serialization relied on the
parent-scoped namespace, so that LHDN's verifier sees fully-qualified
elements inside the hashed byte sequence (and inside the final signed XML
payload).

Why a string replace rather than XML-tree manipulation? PHP itself uses
``str_replace`` over the serialized string. To match byte-for-byte we must
do the same. ``lxml.etree.c14n()`` is overly aggressive about pruning
redundant namespace declarations PHP keeps, and resorting to manual tree
injection caused several hash mismatches during reverse-engineering (see
AGENTS.md PHASE 4 for context).
"""

from __future__ import annotations

# The XML namespaces that get injected back onto individual elements.
_DS_NS = 'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
_XADES_NS = 'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#"'


def replace_common_attributes(xml: str) -> str:
    """Replicate ``MyInvoisHelper::replaceCommonAttributes`` byte-for-byte.

    Injects xmlns declarations onto 5 element-shapes that PHP serializes
    without their parent namespace. Order matches PHP's replacement table
    (see ``MyInvoisHelper.php``): SignedProperties, DigestMethod,
    X509SerialNumber, X509IssuerName, DigestValue.
    """
    out = xml
    out = out.replace(
        '<xades:SignedProperties Id="id-xades-signed-props">',
        f'<xades:SignedProperties Id="id-xades-signed-props" {_XADES_NS}>',
    )
    # Note: PHP matches the *empty-tag* form ``<ds:DigestMethod Algorithm="..."
    # ></ds:DigestMethod>`` (Sabre emits the binary element with a closing
    # </ds:DigestMethod>). The xmlns:ds attribute is injected INSIDE the
    # opening tag, before the existing Algorithm attribute.
    out = out.replace(
        '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></ds:DigestMethod>',
        '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"'
        f" {_DS_NS}></ds:DigestMethod>",
    )
    out = out.replace("<ds:X509SerialNumber>", f"<ds:X509SerialNumber {_DS_NS}>")
    out = out.replace("<ds:X509IssuerName>", f"<ds:X509IssuerName {_DS_NS}>")
    out = out.replace("<ds:DigestValue>", f"<ds:DigestValue {_DS_NS}>")
    return out


__all__ = ["replace_common_attributes"]
