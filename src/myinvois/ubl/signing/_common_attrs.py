"""Common-attribute replacement pass for signed XML fragments.

This string-surgery pass is applied to two XML fragments:

* the *SignedProperties* subtree (used to compute the PropsDigest);
* the entire signed document *after* all signature components have been
  stitched in.

In both cases it injects the 5 ``xmlns:ds`` / ``xmlns:xades`` declarations
onto elements whose serialization relies on a parent-scoped namespace, so
that LHDN's verifier sees fully-qualified elements inside the hashed byte
sequence (and inside the final signed XML payload).

Why a string replace rather than XML-tree manipulation? The canonical wire
form keeps namespace declarations on individual elements that a strict XML
serializer (e.g. ``lxml.etree.c14n()``) would prune as redundant, diverging
from the LHDN-expected byte stream. Doing the injection as a deterministic
string replace over the serialized output preserves the exact declared
attributes byte-for-byte.
"""

from __future__ import annotations

# The XML namespaces that get injected back onto individual elements.
_DS_NS = 'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"'
_XADES_NS = 'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#"'


def replace_common_attributes(xml: str) -> str:
    """Inject xmlns declarations onto 5 element-shapes that serialize without
    their parent namespace. Order is: SignedProperties, DigestMethod,
    X509SerialNumber, X509IssuerName, DigestValue.
    """
    out = xml
    out = out.replace(
        '<xades:SignedProperties Id="id-xades-signed-props">',
        f'<xades:SignedProperties Id="id-xades-signed-props" {_XADES_NS}>',
    )
    # Inject into the *empty-tag* form
    # ``<ds:DigestMethod Algorithm="..."></ds:DigestMethod>`` (the binary
    # element with a closing ``</ds:DigestMethod>``). The xmlns:ds attribute
    # is injected INSIDE the opening tag, before the existing Algorithm
    # attribute.
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
