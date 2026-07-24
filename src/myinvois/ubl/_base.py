"""Common base infrastructure for the UBL 2.1 Pydantic models.

Pydantic v2 models whose `model_dump(by_alias=True, exclude_none=True)`
emits the same nested structure as the LHDN wire form:
scalars are wrapped as `{"_": value, **attributes}` leaves, and every
repeatable element is emitted as a list. This keeps Phase 3c (the envelope
builder) trivial: it only has to wrap the per-class dumps in the
`{"_D": ..., "_A": ..., "_B": ..., "_E": ..., "<TagName>": [invoice_dump]}`
envelope.

Money is always `Decimal` — finance library; no float arithmetic.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

# These are the module's internal API, imported by the sibling model modules
# (address.py, party.py, tax.py, …) rather than used within this file. Naming
# them in __all__ marks them as exported so a "used only via import" checker
# does not read them as dead.
__all__ = ["_UblModel", "_leaf", "_money"]


class _UblModel(BaseModel):
    """Base for every UBL structural model.

    Config:
    * `populate_by_name=True` so callers construct with idiomatic snake_case
      Python attrs, *or* with the raw UBL element-name aliases.
    * `use_enum_values=False` retain the enum instance (the library convention
      is to accept either enum or raw string; we store the enum and coerce at
      construction via custom validators per field).
    * `arbitrary_types_allowed=True` because `Decimal` is fine but a couple of
      fields hold `datetime`.
    * `validate_assignment=False` to keep assignment fast; we run validation on
      construction only (and `Invoice.validate()` semantics via
      `@model_validator(mode="after")` per subclass).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=False,
        arbitrary_types_allowed=True,
        validate_assignment=False,
        extra="forbid",
        str_strip_whitespace=True,
    )


def _leaf(value: Any, **attrs: Any) -> dict[str, Any]:
    """Build a UBL leaf node `{"_": value, **attribute}`.

    Attributes whose value is None are dropped (UBL convention: omit-when-empty).
    """
    out: dict[str, Any] = {"_": value}
    for k, v in attrs.items():
        if v is not None:
            out[k] = v
    return out


def _money(value: Decimal | float | int | str | None) -> Any:
    """Return the value ready for a `_leaf("_", ...) = money` slot.

    Accepts the messy Python types a finance user might pass (float, int, str,
    Decimal) and returns a Decimal. None passes through unchanged.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    # Avoid float->decimal precision loss by stringifying the float first.
    return Decimal(str(value))
