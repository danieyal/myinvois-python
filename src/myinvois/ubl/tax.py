"""Tax components: TaxScheme, TaxCategory, TaxSubTotal, TaxTotal."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from myinvois.codes import TaxType

from ._base import _leaf, _money, _UblModel


class TaxScheme(_UblModel):
    """`cac:TaxScheme` — e.g. `OTH` (Other / Malaysian tax scheme)."""

    id: str = Field(serialization_alias="ID")
    name: str | None = Field(default=None, serialization_alias="Name")
    tax_type_code: str | None = Field(default=None, serialization_alias="TaxTypeCode")
    currency_code: str | None = Field(default=None, serialization_alias="CurrencyCode")
    # Default attributes per PHP SDK TaxScheme.idAttributes.
    scheme_id: str = Field(default="UN/ECE 5153", exclude=True, repr=False)
    scheme_agency_id: str = Field(default="6", exclude=True, repr=False)

    @model_validator(mode="after")
    def _must_have_id(self) -> TaxScheme:
        if not self.id:
            raise ValueError("TaxScheme.id is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ID": _leaf(self.id, schemeID=self.scheme_id, schemeAgencyID=self.scheme_agency_id)
        }
        if self.name is not None:
            out["Name"] = _leaf(self.name)
        if self.tax_type_code is not None:
            out["TaxTypeCode"] = _leaf(self.tax_type_code)
        if self.currency_code is not None:
            out["CurrencyCode"] = _leaf(self.currency_code)
        return out


class TaxCategory(_UblModel):
    """`cac:TaxCategory` — pairs a TaxType code (01..06) with a TaxScheme."""

    id: TaxType | str = Field(serialization_alias="ID")
    name: str | None = Field(default=None, serialization_alias="Name")
    percent: Decimal | None = Field(default=None, serialization_alias="Percent")
    tax_exemption_reason_code: str | None = Field(
        default=None, serialization_alias="TaxExemptionReasonCode"
    )
    tax_exemption_reason: str | None = Field(default=None, serialization_alias="TaxExemptionReason")
    tax_scheme: TaxScheme = Field(serialization_alias="TaxScheme")
    # Default empty idAttributes in PHP SDK.
    id_scheme_id: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        if isinstance(v, str) and v:
            try:
                return TaxType(v)
            except ValueError:
                # Unknown tax-type code: keep the raw string rather than reject;
                # the table can lag the spec. Validated downstream when needed.
                return v
        return v

    @model_validator(mode="after")
    def _must_have_id_and_tax_scheme(self) -> TaxCategory:
        if not self.id:
            raise ValueError("TaxCategory.id is required")
        if self.tax_scheme is None:
            raise ValueError("TaxCategory.tax_scheme is required")
        return self

    @property
    def is_exempt(self) -> bool:
        """True when the tax category declares an exemption."""
        return bool(self.tax_exemption_reason or self.tax_exemption_reason_code)

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ID": _leaf(str(self.id.value if isinstance(self.id, TaxType) else self.id))
        }
        if self.name is not None:
            out["Name"] = _leaf(self.name)
        if self.percent is not None:
            out["Percent"] = _leaf(self.percent)
        if self.tax_exemption_reason_code is not None:
            out["TaxExemptionReasonCode"] = _leaf(self.tax_exemption_reason_code)
        if self.tax_exemption_reason is not None:
            out["TaxExemptionReason"] = _leaf(self.tax_exemption_reason)
        out["TaxScheme"] = self.tax_scheme.model_dump(by_alias=True, exclude_none=True)
        return out


class TaxSubTotal(_UblModel):
    """`cac:TaxSubtotal` — one row of the tax breakdown for a category."""

    taxable_amount: Decimal = Field(serialization_alias="TaxableAmount")
    tax_amount: Decimal = Field(serialization_alias="TaxAmount")
    percent: Decimal | None = Field(default=None, serialization_alias="Percent")
    tax_category: TaxCategory = Field(serialization_alias="TaxCategory")
    per_unit_amount: Decimal | None = Field(default=None, serialization_alias="PerUnitAmount")
    base_unit_measure: Decimal | None = Field(default=None, serialization_alias="BaseUnitMeasure")
    # Per-amount currencyID defaults come from the document currency; in the
    # PHP SDK the per-amount Attributes default to MYR but the serializer is
    # responsible for stamping the right currencyID in Phase 3c. Phase 3b
    # exposes optional overrides here.
    taxable_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)
    tax_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator(
        "taxable_amount",
        "tax_amount",
        "percent",
        "per_unit_amount",
        "base_unit_measure",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _must_have_amount_and_category(self) -> TaxSubTotal:
        if self.tax_amount is None:
            raise ValueError("TaxSubTotal.tax_amount is required")
        if self.tax_category is None:
            raise ValueError("TaxSubTotal.tax_category is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "TaxableAmount": _leaf(self.taxable_amount, currencyID=self.taxable_amount_currency_id),
            "TaxAmount": _leaf(self.tax_amount, currencyID=self.tax_amount_currency_id),
        }
        if self.percent is not None:
            out["Percent"] = _leaf(self.percent)
        out["TaxCategory"] = self.tax_category.model_dump(by_alias=True, exclude_none=True)
        if self.per_unit_amount is not None:
            out["PerUnitAmount"] = _leaf(self.per_unit_amount)
        if self.base_unit_measure is not None:
            out["BaseUnitMeasure"] = _leaf(self.base_unit_measure)
        return out


class TaxTotal(_UblModel):
    """`cac:TaxTotal` — total tax for the document (or one line)."""

    tax_amount: Decimal = Field(serialization_alias="TaxAmount")
    tax_sub_totals: list[TaxSubTotal] = Field(
        default_factory=list, serialization_alias="TaxSubtotal"
    )
    rounding_amount: Decimal | None = Field(default=None, serialization_alias="RoundingAmount")
    tax_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)
    rounding_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("tax_amount", "rounding_amount", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _must_have_amount_and_subtotals(self) -> TaxTotal:
        if self.tax_amount is None:
            raise ValueError("TaxTotal.tax_amount is required")
        if not self.tax_sub_totals:
            raise ValueError("TaxTotal.tax_sub_totals must contain at least one TaxSubTotal")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "TaxAmount": _leaf(self.tax_amount, currencyID=self.tax_amount_currency_id),
        }
        out["TaxSubtotal"] = [
            ts.model_dump(by_alias=True, exclude_none=True) for ts in self.tax_sub_totals
        ]
        if self.rounding_amount is not None:
            out["RoundingAmount"] = _leaf(
                self.rounding_amount, currencyID=self.rounding_amount_currency_id
            )
        return out
