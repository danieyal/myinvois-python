"""Canonical number formatting for the LHDN MyInvois wire form.

Monetary amounts render as JSON number literals (not strings) and as XML
text content with a fixed 2-dp precision. The LHDN validator re-parses
these tokens, so the rendered form must round-trip cleanly.

* ``Decimal('1460.50')`` -> ``1460.5``  (trailing zero dropped)
* ``Decimal('1500.00')`` -> ``1500``     (integer-valued, no decimal point)
* ``Decimal('14.61')``   -> ``14.61``    (kept as-is)
* ``Decimal('5.07')``    -> ``5.07``
* ``Decimal('0.30')``    -> ``0.3``
* ``Decimal('10.0')``    -> ``10``       (used for ``Percent``, etc.)
* ``Decimal('0.15')``    -> ``0.15``

Models hold ``Decimal`` everywhere (no float arithmetic). The boundary to
a wire token happens at envelope rendering time so in-memory stays precise
and the signature digest (Phase 4) is computed over the canonical string.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

__all__ = [
    "PRECISION",
    "format_canonical_json_amount",
    "format_canonical_xml_amount",
    "parse_decimal",
]


#: Default decimal precision for monetary amounts.
PRECISION: int = 2


def format_canonical_json_amount(value: Decimal | float | int | str) -> str:
    """Render an amount as a canonical JSON number token.

    Two decimal places of precision, trailing zeros stripped, and the
    ``.0`` suffix dropped for integer-valued amounts (e.g. ``1460.5``,
    ``1500``, ``0.3``).

    Args:
        value: a ``Decimal`` (preferred) or any ``float``/``int``/``str``
            the user might have supplied via the model's ``field_validator``
            *before* coercion. ``str`` is parsed via ``Decimal`` so caller-
            provided ``"1460.50"`` round-trips identically to ``Decimal("1460.50")``.

    Returns:
        A JSON number token string ready to be appended to the wire payload
        (e.g. ``"1460.5"``, ``"1500"``, ``"14.61"``).

    Raises:
        InvalidOperation: if ``str`` input cannot be parsed to ``Decimal``.
    """
    if isinstance(value, str):
        value = Decimal(value)
    elif isinstance(value, float):
        # Stay precise by going via str to avoid float->Decimal noise.
        value = Decimal(str(value))
    elif isinstance(value, int):
        value = Decimal(value)
    elif not isinstance(value, Decimal):
        raise TypeError(
            f"format_canonical_json_amount expects Decimal/num/str; got {type(value)!r}"
        )

    quantized = value.quantize(Decimal(10) ** -PRECISION)
    s = str(quantized)
    # Strip trailing zeros and the decimal point for integer-valued amounts
    # (e.g. "1500.00" -> "1500", "0.30" -> "0.3", "14.61" stays "14.61").
    # Working entirely in Decimal avoids float(Decimal(...)) precision loss
    # for large monetary values.
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def parse_decimal(value: Decimal | float | int | str) -> Decimal:
    """Coerce any caller-supplied numeric type to ``Decimal`` safely.

    Used by the envelope renderer when it needs the quantized value for
    comparison purposes (the model fields already hold ``Decimal`` instances,
    so this is a defence-in-depth helper).
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as ex:
            raise InvalidOperation(f"cannot parse {value!r} as Decimal") from ex
    raise TypeError(f"parse_decimal expects Decimal/num/str; got {type(value)!r}")


def format_canonical_xml_amount(value: Decimal | float | int | str) -> str:
    """Render an amount as a canonical XML number token.

    Exactly two decimal places, dot separator, no thousands separator.
    Trailing zeros are preserved (the wire-canonical UBL XML form):

    * ``Decimal('1436.50')`` -> ``"1436.50"``
    * ``Decimal('1500')``/``Decimal('1500.00')`` -> ``"1500.00"``
    * ``Decimal('0.30')`` -> ``"0.30"``
    * ``Decimal('0.15')`` -> ``"0.15"``
    * ``Decimal('1')``     -> ``"1.00"``
    * ``Decimal('10.0')``  -> ``"10.00"`` (used for ``Percent``)

    Args:
        value: ``Decimal`` (preferred) or any ``float``/``int``/``str`` the
            user might supply (string is parsed via ``Decimal``).
    """
    return f"{_quantize(value):f}"


def _quantize(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal(10) ** -PRECISION)
    if isinstance(value, str):
        return Decimal(value).quantize(Decimal(10) ** -PRECISION)
    if isinstance(value, float):
        return Decimal(str(value)).quantize(Decimal(10) ** -PRECISION)
    if isinstance(value, int):
        return Decimal(value).quantize(Decimal(10) ** -PRECISION)
    raise TypeError(
        f"format_canonical_xml_amount expects Decimal/num/str; got {type(value)!r}"
    )  # pragma: no cover - defensive
