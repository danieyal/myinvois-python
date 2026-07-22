"""Canonical JSON envelope builder for the LHDN MyInvois wire form.

The renderer is hand-rolled rather than slaved to Python's ``json.dumps``
because the canonical LHDN form has two requirements that ``json.dumps``
cannot satisfy:

1. **Every keyed element inside the document content is wrapped as a
   one-or-more-element JSON array.** This includes singletons (e.g.
   ``"IssueDate": [{"_": "2024-06-14"}]``) and structural submodels
   (e.g. ``"TaxTotal": [{...}]``).

2. **Money renders as JSON *numbers* in a compact float style.**
   ``Decimal("1460.50")`` -> ``1460.5``; ``Decimal("1500.00")`` -> ``1500``
   (no ``.0``); ``Decimal("0.30")`` -> ``0.3``. Python's ``repr(float)`` has
   the same shape for the non-integer case but emits ``1500.0`` for
   integer-valued floats. The
   ``_number.format_canonical_json_amount`` helper handles this consistently.

Output is byte-identical to the canonical LHDN-conformant form (compact,
no escapes, no slash escapes — equivalent to
``JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES``). Phase 4's signature
digest operates on this exact string; do NOT edit any formatting choice
without regenerating the golden test fixtures.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ._number import format_canonical_json_amount
from ._specs import ENVELOPE_DOCUMENT_TAGS, UBL_NAMESPACES

__all__ = ["JsonEnvelopeBuilder"]


class JsonEnvelopeBuilder:
    """Build the canonical LHDN UBL JSON envelope for an :class:`~myinvois.ubl.Invoice`.

    Usage::

        builder = JsonEnvelopeBuilder(invoice)
        s = builder.build_json()  # str, ready for POST /documents

    The builder treats the invoice's ``model_dump(by_alias=True, exclude_none=True)``
    output as the *idiomatic Python surface* (unwrapped dicts for leaf elements)
    and transforms it into the canonical LHDN wire form at the boundary.
    """

    __slots__ = ("_invoice",)

    def __init__(self, invoice: Any) -> None:
        self._invoice = invoice

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_json(self) -> str:
        """Return the canonical UBL JSON envelope as a compact Unicode string."""
        content_url = self._document_tag()
        content = self._content_dump()

        # Stamp document currency onto every amount that did not override it.
        self._stamp_currency(content, self._document_currency_code())

        wrapped = self._wrap_array_form(content)

        envelope: dict[str, Any] = {
            "_D": content_url,
            "_A": UBL_NAMESPACES["cac"],
            "_B": UBL_NAMESPACES["cbc"],
            "_E": UBL_NAMESPACES["ext"],
            self._document_tag_name(): [wrapped],
        }
        return self._render(envelope)

    # ------------------------------------------------------------------
    # Document introspection
    # ------------------------------------------------------------------

    def _document_tag_name(self) -> str:
        # Top-level document classes carry ``xml_tag_name`` (e.g. ``"Invoice"``).
        return getattr(self._invoice, "xml_tag_name", "Invoice")

    def _document_tag(self) -> str:
        name = self._document_tag_name()
        url = ENVELOPE_DOCUMENT_TAGS.get(name)
        if url is None:
            # Deliberately not falling back to the standard UBL pattern
            # (``...:<Tag>-2``). MyInvois accepts only the ``Invoice``
            # envelope; synthesising e.g. ``CreditNote-2`` would emit a
            # well-formed document that LHDN rejects, with nothing in the
            # payload to explain why. Fail here instead.
            raise ValueError(
                f"Unsupported UBL document tag {name!r}. MyInvois carries every "
                f"document type on the 'Invoice' envelope, distinguished by "
                f"InvoiceTypeCode -- set invoice_type_code, not xml_tag_name."
            )
        return url

    def _document_currency_code(self) -> str:
        v = getattr(self._invoice, "document_currency_code", None)
        if v is None:
            return "MYR"
        # Allow StrEnum-with-value OR raw string.
        value = getattr(v, "value", v)
        return value if isinstance(value, str) else str(value)

    def _content_dump(self) -> dict[str, Any]:
        # `Invoice.model_dump(by_alias=True, exclude_none=True)` returns the
        # per-class `_ser` dict already aligned to the canonical keyspace —
        # leaves are `{"_": value, attrs...}` dicts and repeatables are
        # lists-of-dicts.
        dump = self._invoice.model_dump(by_alias=True, exclude_none=True)
        return dump if isinstance(dump, dict) else dict(dump)

    # ------------------------------------------------------------------
    # Currency stamping (default currencyID = document currency)
    # ------------------------------------------------------------------

    # Every amount-bearing leaf-form dict we recognize by attribute name. If
    # the leaf has no `currencyID` set, default it to the document currency.
    _AMOUNT_LEAF_ATTR_FIELDS: tuple[str, ...] = (
        "tax_amount",
        "taxable_amount",
        "per_unit_amount",
        "base_unit_measure",
        "rounding_amount",
        "line_extension_amount",
        "amount",
        "price_amount",
        "base_quantity",
        "paid_amount",
        "prepaid_amount",
        "allowance_total_amount",
        "charge_total_amount",
        "payable_rounding_amount",
        "payable_amount",
        "tax_exclusive_amount",
        "tax_inclusive_amount",
    )

    def _stamp_currency(self, node: Any, currency: str) -> None:
        """Walk the dump tree and apply the document currency to amount leaves.

        Mutates leaves of the form ``{"_": <number>, "currencyID": None}``
        (or absent currencyID) in place. Skips leaves whose `currencyID` is
        already set. Also touches the corresponding ``*_currency_id`` model
        private attrs (not in the dump) — but since we operate purely on the
        dump, we just patch the `currencyID` field of the leaf dict here.
        """
        if isinstance(node, dict):
            if "_" in node and "currencyID" in node:
                # Leaf with a `currencyID` attribute — apply the default if
                # the caller didn't override.
                if not node["currencyID"]:
                    node["currencyID"] = currency
                return
            for v in node.values():
                self._stamp_currency(v, currency)
        elif isinstance(node, list):
            for e in node:
                self._stamp_currency(e, currency)

    # ------------------------------------------------------------------
    # Array-form wrapping
    # ------------------------------------------------------------------

    def _wrap_array_form(self, node: Any) -> Any:
        """Recursively wrap all keyed elements as JSON arrays-of-one-or-more.

        Contract:
          * list nodes are kept as lists; each element recurses.
          * structural dict nodes (no ``_`` key): each value is wrapped in
            ``[value]`` and recurses into the (unwrapped) inner dict.
          * leaf dicts (``"_"`` key present): returned unchanged — the
            parent will wrap them.
        """
        if isinstance(node, list):
            return [self._wrap_array_form(e) for e in node]
        if isinstance(node, dict):
            if "_" in node:
                # Leaf — leave for parent to wrap.
                return node
            result: dict[str, Any] = {}
            for k, v in node.items():
                if isinstance(v, list):
                    # Repeatable element: keep the list; recurse each element.
                    result[k] = [self._wrap_array_form(e) for e in v]
                elif isinstance(v, dict):
                    if "_" in v:
                        # Leaf — wrap as array-of-one.
                        result[k] = [v]
                    else:
                        # Structural submodel — recurse then wrap.
                        result[k] = [self._wrap_array_form(v)]
                else:
                    # Primitive — wrap as array-of-one.
                    result[k] = [v]
            return result
        # Primitive at top-level (unexpected for content dump) — pass through.
        return node

    # ------------------------------------------------------------------
    # JSON renderer (compact serialiser)
    # ------------------------------------------------------------------

    def _render(self, node: Any) -> str:
        # Use a sentinel-aware compact renderer: handles Decimal as a JSON
        # number token via format_canonical_json_amount, emits
        # dicts/lists/strs/bools/None/int per Python json semantics, Unicode
        # passthrough (ensure_ascii=False), and forwards slashes unescaped.
        out: list[str] = []
        self._serialize(node, out)
        return "".join(out)

    def _serialize(self, node: Any, out: list[str]) -> None:  # noqa: PLR0911
        # Dispatch by Python type so this stays a linear sequence, not a
        # nested if/elif chain (ruff keeps the branch count bounded).
        if node is None:
            out.append("null")
            return
        if isinstance(node, bool):
            out.append("true" if node else "false")
            return
        if isinstance(node, str):
            out.append(self._render_string(node))
            return
        if isinstance(node, Decimal):
            out.append(format_canonical_json_amount(node))
            return
        if isinstance(node, float):
            s = repr(node)
            out.append(s[:-2] if s.endswith(".0") else s)
            return
        if isinstance(node, int):  # after Decimal/float to avoid bool/int overlap
            out.append(str(node))
            return
        if isinstance(node, dict):
            out.append("{")
            for i, (k, v) in enumerate(node.items()):
                if i:
                    out.append(",")
                out.append(self._render_string(k))
                out.append(":")
                self._serialize(v, out)
            out.append("}")
            return
        if isinstance(node, (list, tuple)):
            out.append("[")
            for i, e in enumerate(node):
                if i:
                    out.append(",")
                self._serialize(e, out)
            out.append("]")
            return
        raise TypeError(
            f"unsupported JSON node type: {type(node)!r}"
        )  # pragma: no cover - defensive

    # Cache for JSON string escapes. The canonical form emits non-ASCII
    # characters literally and does not escape forward slashes (Python matches
    # via ensure_ascii=False, and doesn't escape ``/`` by default). The only
    # required escapes are the JSON-grammar-mandatory ones.
    @staticmethod
    def _render_string(s: str) -> str:
        # Use json.dumps with ensure_ascii=False for the canonical escape set
        # (quotes, backslashes, control chars). json.dumps does NOT escape
        # forward slashes by default in Python (matches JSON_UNESCAPED_SLASHES).
        import json

        return json.dumps(s, ensure_ascii=False)
