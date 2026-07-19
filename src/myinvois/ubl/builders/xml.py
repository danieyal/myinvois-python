"""Canonical UBL 2.1 XML envelope builder for LHDN MyInvois.

Produces the canonical wire form: UBL 2.1 XML, then canonicalised with
inclusive C14N-1.0 (no-comments).

This renderer **shares the per-class ``_ser`` dump** with
:class:`~myinvois.ubl.builders.json.JsonEnvelopeBuilder`; the model_dump
dict is the single source of truth for both forms. The XML builder just:

1. Walks the dump and emits lxml elements with the correct namespace prefix
   (cbc/cac/ext/none) per :data:`_prefixes.ELEMENT_PREFIXES`.
2. Renders amount ``_`` leaves with
   :func:`_number.format_canonical_xml_amount`
   (two decimal places, trailing zeros preserved); other leaves render as
   their natural string form.
3. Stamps the document currency onto every amount's ``currencyID`` attribute
   (same logic as the JSON builder).
4. Feeds the lxml tree back into ``etree.tostring(method='c14n',
   exclusive=False, with_comments=False)`` — inclusive canonicalisation
   which keeps the four xmlns declarations on the root invoice element
   exactly as the LHDN server compares. Phase 4's XAdES-ENVELOPED signature
   digest runs the same canonicaliser on the signed Invoice subtree.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

from lxml import etree

from ._number import format_canonical_xml_amount
from ._prefixes import ELEMENT_PREFIXES
from ._specs import UBL_NAMESPACES

__all__ = ["XmlEnvelopeBuilder"]

_NS_CAC = UBL_NAMESPACES["cac"]
_NS_CBC = UBL_NAMESPACES["cbc"]
_NS_EXT = UBL_NAMESPACES["ext"]


class XmlEnvelopeBuilder:
    """Build the canonical LHDN UBL XML envelope for an :class:`~myinvois.ubl.Invoice`.

    Usage::

        builder = XmlEnvelopeBuilder(invoice)
        s = builder.build_xml()  # canonical XML 1.0 (inclusive), str

    The output is the canonical LHDN-accepted form (C14N-canonical, no XML
    declaration, no inter-element whitespace), so Phase 4's signature
    digests match server-side.
    """

    __slots__ = ("_invoice",)

    def __init__(self, invoice: Any) -> None:
        self._invoice = invoice

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_xml(self) -> str:
        """Return the canonical UBL XML envelope as a C14N-1.0 inclusive string."""
        tag_name = self._document_tag_name()
        ns_url = self._document_tag_url(tag_name)

        # Root element owns all four xmlns declarations. lxml uses ``None`` as
        # the nsmap key for the default namespace so the root tag is unprefixed.
        nsmap = {None: ns_url, "cac": _NS_CAC, "cbc": _NS_CBC, "ext": _NS_EXT}
        root = etree.Element(f"{{{ns_url}}}{tag_name}", nsmap=nsmap)

        content = self._content_dump()
        self._stamp_currency(content, self._document_currency_code())
        self._render_children(root, content)

        # Inclusive C14N-1.0 (exclusive=False). Keeps all four xmlns
        # declarations on the root invoice element (the form LHDN compares).
        # with_comments=False strips any incidental lxml whitespace nodes.
        c14n = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
        return str(c14n.decode("utf-8"))

    # ------------------------------------------------------------------
    # Document introspection (mirrors JsonEnvelopeBuilder)
    # ------------------------------------------------------------------

    def _document_tag_name(self) -> str:
        return getattr(self._invoice, "xml_tag_name", "Invoice")

    def _document_tag_url(self, tag_name: str) -> str:
        from ._specs import ENVELOPE_DOCUMENT_TAGS

        url = ENVELOPE_DOCUMENT_TAGS.get(tag_name)
        if url is None:
            url = f"urn:oasis:names:specification:ubl:schema:xsd:{tag_name}-2"
        return url

    def _document_currency_code(self) -> str:
        v = getattr(self._invoice, "document_currency_code", None)
        if v is None:
            return "MYR"
        value = getattr(v, "value", v)
        return value if isinstance(value, str) else str(value)

    def _content_dump(self) -> dict[str, Any]:
        # Same dump the JsonEnvelopeBuilder consumes — single source of truth.
        dump = self._invoice.model_dump(by_alias=True, exclude_none=True)
        return dump if isinstance(dump, dict) else dict(dump)

    # ------------------------------------------------------------------
    # Currency stamping (mirrors JsonEnvelopeBuilder)
    # ------------------------------------------------------------------

    def _stamp_currency(self, node: Any, currency: str) -> None:
        if isinstance(node, dict):
            if "_" in node and "currencyID" in node:
                if not node["currencyID"]:
                    node["currencyID"] = currency
                return
            for v in node.values():
                self._stamp_currency(v, currency)
        elif isinstance(node, list):
            for e in node:
                self._stamp_currency(e, currency)

    # ------------------------------------------------------------------
    # lxml tree rendering
    # ------------------------------------------------------------------

    def _render_children(self, parent: etree._Element, content: dict[str, Any]) -> None:
        """Emit each key in ``content`` as a child element of ``parent``.

        Order of keys in the dict is preserved (Pydantic preserves the
        declaration order in per-class ``_ser()``), which follows the
        UBL 2.1 XSD element sequence that both wire forms share.
        """
        for key, value in content.items():
            tag = self._key_to_tag(key)
            if isinstance(value, list):
                # Repeatable: emit each list element under the same tag name.
                for e in value:
                    self._emit_one(parent, tag, e)
            else:
                self._emit_one(parent, tag, value)

    def _emit_one(self, parent: etree._Element, tag: str, value: Any) -> None:
        """Emit a single element for ``tag`` with ``value`` as its content."""
        if isinstance(value, dict) and "_" in value:
            el = etree.SubElement(parent, tag)
            leaf_text = value["_"]
            for attr_name, attr_val in value.items():
                if attr_name == "_":
                    continue
                el.set(attr_name, str(attr_val))
            el.text = self._format_text(leaf_text)
        elif isinstance(value, dict):
            el = etree.SubElement(parent, tag)
            self._render_children(el, value)
        else:
            el = etree.SubElement(parent, tag)
            el.text = self._format_text(value)

    def _format_text(self, value: Any) -> str:
        """Render a leaf ``_`` value as the canonical wire text.

        Decimal -> 2dp fixed, trailing zeros preserved.
        bool -> lowercase 'true'/'false'.
        str -> XML-escaped string.
        None -> empty (no text content).
        """
        if value is None:
            return ""
        if isinstance(value, bool):  # boolean handling wants lowercase 'true'/'false'
            return "true" if value else "false"
        if isinstance(value, (Decimal, float, int)):
            return format_canonical_xml_amount(value)
        return _xml_escape(str(value))

    @staticmethod
    def _key_to_tag(key: str) -> str:
        """Map a content-dump key to its Clark-notation lxml tag.

        Uses :data:`_prefixes.ELEMENT_PREFIXES` to translate the bare UBL
        local-name into a fully-qualified lxml tag. Unknown keys fall back to
        the unprefixed tag (will raise at lxml if no namespace-uri match
        exists; surfaces a clear bug for any element we forgot to register).
        """
        prefix = ELEMENT_PREFIXES.get(key, "")
        if not prefix:
            return key
        ns_uri = {"cac": _NS_CAC, "cbc": _NS_CBC, "ext": _NS_EXT}[prefix]
        return f"{{{ns_uri}}}{key}"
