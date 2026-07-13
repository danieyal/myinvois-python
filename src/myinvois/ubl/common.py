"""Common reusable UBL components: AllowanceCharge, InvoicePeriod,
SettlementPeriod, TaxExchangeRate.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from ._base import _leaf, _money, _UblModel
from .address import Address
from .party import Party


class AllowanceCharge(_UblModel):
    """`cac:AllowanceCharge` — document- or line-level allowances/charges."""

    charge_indicator: bool = Field(serialization_alias="ChargeIndicator")
    allowance_charge_reason: str | None = Field(
        default=None, serialization_alias="AllowanceChargeReason"
    )
    multiplier_factor_numeric: Decimal | None = Field(
        default=None, serialization_alias="MultiplierFactorNumeric"
    )
    amount: Decimal | None = Field(default=None, serialization_alias="Amount")
    amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("multiplier_factor_numeric", "amount", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _requires_charge_indicator(self) -> AllowanceCharge:
        if self.charge_indicator is None:
            raise ValueError("AllowanceCharge.charge_indicator is required")
        return self

    @property
    def is_charge(self) -> bool:
        return self.charge_indicator

    @property
    def is_allowance(self) -> bool:
        return not self.charge_indicator

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ChargeIndicator": _leaf(bool(self.charge_indicator))}
        if self.allowance_charge_reason is not None:
            out["AllowanceChargeReason"] = _leaf(self.allowance_charge_reason)
        if self.multiplier_factor_numeric is not None:
            out["MultiplierFactorNumeric"] = _leaf(self.multiplier_factor_numeric)
        if self.amount is not None:
            out["Amount"] = _leaf(self.amount, currencyID=self.amount_currency_id)
        return out


class InvoicePeriod(_UblModel):
    """`cac:InvoicePeriod` — must have a start_date / end_date / description
    (PHP validate() requires at least one).
    """

    start_date: date | None = Field(default=None, serialization_alias="StartDate")
    end_date: date | None = Field(default=None, serialization_alias="EndDate")
    description: str | None = Field(default=None, serialization_alias="Description")

    @model_validator(mode="after")
    def _requires_some_payload(self) -> InvoicePeriod:
        if self.description is None and self.start_date is None and self.end_date is None:
            raise ValueError("InvoicePeriod requires start_date, end_date or description")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.start_date is not None:
            out["StartDate"] = _leaf(self.start_date.isoformat())
        if self.end_date is not None:
            out["EndDate"] = _leaf(self.end_date.isoformat())
        if self.description is not None:
            out["Description"] = _leaf(self.description)
        return out


class SettlementPeriod(_UblModel):
    """`cac:SettlementPeriod` — days-based window within payment terms."""

    start_date: date = Field(serialization_alias="StartDate")
    end_date: date = Field(serialization_alias="EndDate")

    @model_validator(mode="after")
    def _requires_both(self) -> SettlementPeriod:
        if self.start_date is None:
            raise ValueError("SettlementPeriod.start_date is required")
        if self.end_date is None:
            raise ValueError("SettlementPeriod.end_date is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "StartDate": _leaf(self.start_date.isoformat()),
            "EndDate": _leaf(self.end_date.isoformat()),
            "DurationMeasure": _leaf((self.end_date - self.start_date).days, unitCode="DAY"),
        }


class TaxExchangeRate(_UblModel):
    """`cac:TaxExchangeRate` — multi-currency tax conversion rate."""

    source_currency_code: str | None = Field(default=None, serialization_alias="SourceCurrencyCode")
    source_currency_base_rate: Decimal | None = Field(
        default=None, serialization_alias="SourceCurrencyBaseRate"
    )
    target_currency_code: str | None = Field(default=None, serialization_alias="TargetCurrencyCode")
    target_currency_base_rate: Decimal | None = Field(
        default=None, serialization_alias="TargetCurrencyBaseRate"
    )
    calculation_rate: Decimal = Field(serialization_alias="CalculationRate")

    @field_validator(
        "source_currency_base_rate",
        "target_currency_base_rate",
        "calculation_rate",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _must_have_calculation_rate(self) -> TaxExchangeRate:
        if self.calculation_rate is None:
            raise ValueError("TaxExchangeRate.calculation_rate is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.source_currency_code is not None:
            out["SourceCurrencyCode"] = _leaf(self.source_currency_code)
        if self.source_currency_base_rate is not None:
            out["SourceCurrencyBaseRate"] = _leaf(self.source_currency_base_rate)
        if self.target_currency_code is not None:
            out["TargetCurrencyCode"] = _leaf(self.target_currency_code)
        if self.target_currency_base_rate is not None:
            out["TargetCurrencyBaseRate"] = _leaf(self.target_currency_base_rate)
        out["CalculationRate"] = _leaf(self.calculation_rate)
        return out


class Shipment(_UblModel):
    """`cac:Shipment` — a shipment identifier plus optional freight charges."""

    id: str = Field(default="", serialization_alias="ID")
    freight_allowance_charge: list[AllowanceCharge] = Field(
        default_factory=list, serialization_alias="FreightAllowanceCharge"
    )

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ID": _leaf(self.id)}
        if self.freight_allowance_charge:
            out["FreightAllowanceCharge"] = [
                ac.model_dump(by_alias=True, exclude_none=True)
                for ac in self.freight_allowance_charge
            ]
        return out


class Delivery(_UblModel):
    """`cac:Delivery` — actual delivery date / location / party / shipment."""

    actual_delivery_date: date | None = Field(
        default=None, serialization_alias="ActualDeliveryDate"
    )
    delivery_location: Address | None = Field(default=None, exclude=True, repr=False)
    delivery_party: Party = Field(serialization_alias="DeliveryParty")
    shipment: Shipment | None = Field(default=None, serialization_alias="Shipment")

    @model_validator(mode="after")
    def _must_have_delivery_party(self) -> Delivery:
        if self.delivery_party is None:
            raise ValueError("Delivery.delivery_party is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.actual_delivery_date is not None:
            out["ActualDeliveryDate"] = _leaf(self.actual_delivery_date.isoformat())
        if self.delivery_location is not None:
            out["DeliveryLocation"] = {
                "Address": self.delivery_location.model_dump(by_alias=True, exclude_none=True)
            }
        out["DeliveryParty"] = self.delivery_party.model_dump(by_alias=True, exclude_none=True)
        if self.shipment is not None:
            out["Shipment"] = self.shipment.model_dump(by_alias=True, exclude_none=True)
        return out
