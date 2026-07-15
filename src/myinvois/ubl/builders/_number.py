"""Number formatting compatible with the PHP SDK's ``NumberFormatter::formatAsFloat``.

The wire form expects every monetary amount to render as a JSON number
literal, NOT a string. The canonical rules (cross-verified against the PHP
SDK and the TypeScript ``myinvois-client``):

* ``Decimal('1460.50')`` -> ``1460.5``  (trailing zero dropped)
* ``Decimal('1500.00')`` -> ``1500``     (integer-valued, no decimal point)
* ``Decimal('14.61')``   -> ``14.61`    (kept as-is)
* ``Decimal('5.07')``    -> ``5.07``
* ``Decimal('0.30')``    -> ``0.3``
* ``Decimal('10.0')``    -> ``10``       (used for ``Percent``, etc.)
* ``Decimal('0.15')``    -> ``0.15``

Internally the models hold ``Decimal`` instances for finance precision. The
boundary to JSON numeric token happens at envelope rendering time so that:

1. In-memory stays precise (no float arithmetic).
2. The serialized token round-trips through LHDN's JSON validator, which
   re-parses the number back into a float and applies its own decimal math.
3. Phase 4's signature digest is computed over the canonical string emitted
   by ``format_as_php_float_token`` so digests match the PHP / LHDN canonical
   form exactly.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

__all__ = ["PRECISION", "format_as_php_float_token", "format_as_php_xml_token"]


#: Default decimal precision — mirrors
#: ``NumberFormatConfiguration::DEFAULT_PRECISION = 2``.
PRECISION: int = 2


def format_as_php_float_token(value: Decimal | float | int | str) -> str:
    """Return the canonical PHP-compliant JSON number token for an amount.

    Mirrors ``(float) number_format($value, 2, ".", "")`` followed by PHP's
    ``json_encode`` float serialization (strip trailing zeros, drop ``.0``
    for integer-valued floats).

    Args:
        value: a ``Decimal`` (preferred) or any ``float``/``int``/``str``
            the user might have supplied via the model's ``field_validator``
            *before* coercion. ``str`` is parsed via ``Decimal`` so caller-
            provided ``"1460.50"`` round-trips identically to ``Decimal("1460.50")``.

    Returns:
        A JSON number token string ready to be appended to the wire-form
        payload (e.g. ``"1460.5"``, ``"1500"``, ``"14.61"``).

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
        raise TypeError(f"format_as_php_float_token expects Decimal/num/str; got {type(value)!r}")

    quantized = value.quantize(Decimal(10) ** -PRECISION)
    f = float(quantized)
    s = repr(f)
    # Python repr(float) gives short form e.g. '1460.5', '0.3' — matches PHP
    # json_encode for non-integer-valued floats. For integer-valued floats
    # repr gives '1500.0' but PHP emits '1500' (drops the trailing '.0').
    if s.endswith(".0"):
        s = s[:-2]
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


def format_as_php_xml_token(value: Decimal | float | int | str) -> str:
    """Return the canonical PHP-compliant XML number token for an amount.

    Mirrors ``NumberFormatter::format($value)`` (no precision override) as
    called by the per-class ``xmlSerialize()`` methods::

        number_format($value, 2, '.', '')

    — exactly two decimal places, dot separator, no thousands separator.
    Trailing zeros are preserved (matches the wire-canonical UBL XML form):

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
        f"format_as_php_xml_token expects Decimal/num/str; got {type(value)!r}"
    )  # pragma: no cover - defensive
