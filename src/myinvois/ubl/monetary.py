"""Monetary totals: `cac:LegalMonetaryTotal`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from ._base import _leaf, _money, _UblModel


def _amt(value: Any, currency_id: str | None) -> dict[str, Any]:
    """Emit a monetary leaf, always (matches PHP SDK getAmountArray default 0)."""
    return _leaf(value, currencyID=currency_id)


class LegalMonetaryTotal(_UblModel):
    """`cac:LegalMonetaryTotal` — document totals."""

    line_extension_amount: Decimal = Field(
        default=Decimal("0"), serialization_alias="LineExtensionAmount"
    )
    tax_exclusive_amount: Decimal = Field(serialization_alias="TaxExclusiveAmount")
    tax_inclusive_amount: Decimal = Field(serialization_alias="TaxInclusiveAmount")
    allowance_total_amount: Decimal | None = Field(
        default=Decimal("0"), serialization_alias="AllowanceTotalAmount"
    )
    prepaid_amount: Decimal | None = Field(default=None, serialization_alias="PrepaidAmount")
    charge_total_amount: Decimal | None = Field(
        default=None, serialization_alias="ChargeTotalAmount"
    )
    payable_rounding_amount: Decimal | None = Field(
        default=None, serialization_alias="PayableRoundingAmount"
    )
    payable_amount: Decimal = Field(serialization_alias="PayableAmount")

    # The PHP SDK attaches currencyID=MYR to *every* amount attribute by default;
    # the actual currency is the document's DocumentCurrencyCode. The Phase 3c
    # envelope builder stamps the right currencyID based on the invoice's own
    # currency. Here we expose an optional override hook per amount.
    currency_id: str | None = Field(default="MYR", exclude=True, repr=False)

    @field_validator(
        "line_extension_amount",
        "tax_exclusive_amount",
        "tax_inclusive_amount",
        "allowance_total_amount",
        "prepaid_amount",
        "charge_total_amount",
        "payable_rounding_amount",
        "payable_amount",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _requires_three_core_amounts(self) -> LegalMonetaryTotal:
        # PHP validate(): tax_exclusive_amount, tax_inclusive_amount, payable_amount
        # must be non-null. We additionally require line_extension_amount for the
        # finance library (no silent zero-fill).
        for name in (
            "line_extension_amount",
            "tax_exclusive_amount",
            "tax_inclusive_amount",
            "payable_amount",
        ):
            if getattr(self, name) is None:
                raise ValueError(f"LegalMonetaryTotal.{name} is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        cid = self.currency_id
        # Always-emit core totals (default 0 in PHP SDK).
        out: dict[str, Any] = {
            "LineExtensionAmount": _amt(self.line_extension_amount, cid),
            "TaxExclusiveAmount": _amt(self.tax_exclusive_amount, cid),
            "TaxInclusiveAmount": _amt(self.tax_inclusive_amount, cid),
            "AllowanceTotalAmount": _amt(self.allowance_total_amount, cid),
        }
        if self.prepaid_amount is not None:
            out["PrepaidAmount"] = _amt(self.prepaid_amount, cid)
        if self.charge_total_amount is not None:
            out["ChargeTotalAmount"] = _amt(self.charge_total_amount, cid)
        if self.payable_rounding_amount is not None:
            out["PayableRoundingAmount"] = _amt(self.payable_rounding_amount, cid)
        out["PayableAmount"] = _amt(self.payable_amount, cid)
        return out
