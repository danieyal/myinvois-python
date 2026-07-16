"""XML-signed UBLExtensions block construction.

Produces the exact byte sequence PHP's ``XmlDocumentBuilder::signDocument``
injects into the unsigned XML between ``<Invoice ...>`` (opening tag) and the
first child element (``<cbc:ID>``).

The block contains:

* ``ext:UBLExtensions > ext:UBLExtension > ext:ExtensionURI``
* ``ext:ExtensionContent > sig:UBLDocumentSignatures`` (with 4 namespaces
  declared on the root sig: tag)
* ``sac:SignatureInformation``
* ``cbc:ID`` (URI of the signature) + ``sbc:ReferencedSignatureID``
* ``ds:Signature`` (with xmlns:ds + Id="signature")
* ``ds:SignedInfo`` (CanonicalizationMethod + SignatureMethod + 2 References)
* ``ds:SignatureValue``
* ``ds:KeyInfo > ds:X509Data > ds:X509Certificate``
* ``ds:Object > xades:QualifyingProperties > xades:SignedProperties > ...``
"""

from __future__ import annotations

# Namespace URIs.
_NS_SAC = "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2"
_NS_SBC = "urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2"
_NS_SIG = "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2"
_NS_DS = "http://www.w3.org/2000/09/xmldsig#"
_NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"

_SIGN_ID = "urn:oasis:names:specification:ubl:signature:1"
_REFERENCED_SIG_ID = "urn:oasis:names:specification:ubl:signature:Invoice"
_SIG_METHOD_URN = "urn:oasis:names:specification:ubl:dsig:enveloped:xades"


def build_xml_ublextensions_block(
    issuer_name: str,
    serial_number_hex: str,
    cert_digest_b64: str,
    signature_value_b64: str,
    doc_digest_b64: str,
    props_digest_b64: str,
    signing_time_str: str,
    cert_pem_raw: str,
) -> str:
    """Build the ``<ext:UBLExtensions>...</ext:UBLExtensions>`` block exactly
    as PHP emits it (after the apply of ``replaceCommonAttributes``).
    """
    sig_open = '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="signature">'
    signed_info = (
        "<ds:SignedInfo>"
        '<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11">'
        "</ds:CanonicalizationMethod>"
        '<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256">'
        "</ds:SignatureMethod>"
        '<ds:Reference Id="id-doc-signed-data" URI="">'
        "<ds:Transforms>"
        '<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">'
        "<ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>"
        "</ds:Transform>"
        '<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">'
        "<ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>"
        "</ds:Transform>"
        '<ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></ds:Transform>'
        "</ds:Transforms>"
        '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" '
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"></ds:DigestMethod>'
        f'<ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{doc_digest_b64}</ds:DigestValue>'
        "</ds:Reference>"
        '<ds:Reference Type="http://uri.etsi.org/01903/v1.3.2#SignedProperties" '
        'URI="#id-xades-signed-props">'
        '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" '
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"></ds:DigestMethod>'
        f'<ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{props_digest_b64}</ds:DigestValue>'
        "</ds:Reference>"
        "</ds:SignedInfo>"
    )
    signature_value = f"<ds:SignatureValue>{signature_value_b64}</ds:SignatureValue>"
    key_info = (
        "<ds:KeyInfo>"
        "<ds:X509Data>"
        f"<ds:X509Certificate>{cert_pem_raw}</ds:X509Certificate>"
        "</ds:X509Data>"
        "</ds:KeyInfo>"
    )
    object_block = (
        "<ds:Object>"
        f'<xades:QualifyingProperties xmlns:xades="{_NS_XADES}" Target="signature">'
        f'<xades:SignedProperties Id="id-xades-signed-props" '
        f'xmlns:xades="{_NS_XADES}">'
        "<xades:SignedSignatureProperties>"
        f"<xades:SigningTime>{signing_time_str}</xades:SigningTime>"
        "<xades:SigningCertificate>"
        "<xades:Cert>"
        "<xades:CertDigest>"
        '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" '
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"></ds:DigestMethod>'
        f'<ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{cert_digest_b64}</ds:DigestValue>'
        "</xades:CertDigest>"
        "<xades:IssuerSerial>"
        f'<ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{issuer_name}</ds:X509IssuerName>'
        f'<ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{serial_number_hex}</ds:X509SerialNumber>'
        "</xades:IssuerSerial>"
        "</xades:Cert>"
        "</xades:SigningCertificate>"
        "</xades:SignedSignatureProperties>"
        "</xades:SignedProperties>"
        "</xades:QualifyingProperties>"
        "</ds:Object>"
    )
    ds_signature = (
        sig_open + signed_info + signature_value + key_info + object_block + "</ds:Signature>"
    )

    sig_information = (
        "<sac:SignatureInformation>"
        f"<cbc:ID>{_SIGN_ID}</cbc:ID>"
        f"<sbc:ReferencedSignatureID>{_REFERENCED_SIG_ID}</sbc:ReferencedSignatureID>"
        + ds_signature
        + "</sac:SignatureInformation>"
    )
    ubl_document_signatures_open = (
        f'<sig:UBLDocumentSignatures xmlns:sac="{_NS_SAC}" xmlns:sbc="{_NS_SBC}" '
        f'xmlns:sig="{_NS_SIG}">'
    )
    ubl_document_signatures_close = "</sig:UBLDocumentSignatures>"

    extension_content = (
        "<ext:ExtensionContent>"
        + ubl_document_signatures_open
        + sig_information
        + ubl_document_signatures_close
        + "</ext:ExtensionContent>"
    )
    ubl_extension = (
        "<ext:UBLExtension>"
        f"<ext:ExtensionURI>{_SIG_METHOD_URN}</ext:ExtensionURI>"
        + extension_content
        + "</ext:UBLExtension>"
    )
    return "<ext:UBLExtensions>" + ubl_extension + "</ext:UBLExtensions>"


_CAC_SIGNATURE_BLOCK = (
    "<cac:Signature>"
    f"<cbc:ID>{_REFERENCED_SIG_ID}</cbc:ID>"
    f"<cbc:SignatureMethod>{_SIG_METHOD_URN}</cbc:SignatureMethod>"
    "</cac:Signature>"
)


def build_cac_signature_block() -> str:
    """Return the ``<cac:Signature>...</cac:Signature>`` sibling block.

    PHP's ``Invoice::xmlSerialize`` emits this right after the
    ``<cbc:DocumentCurrencyCode>`` element when UBLExtensions have been
    attached to the Invoice — it is the *UBL 2.1 metadata signature* that
    lives as a sibling to ``ext:UBLExtensions`` (NOT inside it). LHDN's
    validator uses this as the "what was signed" anchor for the
    ``URI="#id-xades-signed-props"`` reference.
    """
    return _CAC_SIGNATURE_BLOCK


__all__ = ["build_cac_signature_block", "build_xml_ublextensions_block"]
