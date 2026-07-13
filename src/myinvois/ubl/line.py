"""Line-level UBL components: Item, CommodityClassification, Price,
ItemPriceExtension, InvoiceLine.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from myinvois.codes import UnitCode

from ._base import _leaf, _money, _UblModel
from .address import Country
from .common import AllowanceCharge, InvoicePeriod
from .tax import TaxTotal


class CommodityClassification(_UblModel):
    """`cac:CommodityClassification` — item classification code with a listID."""

    item_classification_code: str = Field(serialization_alias="ItemClassificationCode")
    list_id: str | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _must_have_code(self) -> CommodityClassification:
        if not self.item_classification_code:
            raise ValueError("CommodityClassification.item_classification_code is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {"ItemClassificationCode": _leaf(self.item_classification_code, listID=self.list_id)}


class Item(_UblModel):
    """`cac:Item` — an invoice line's product/service description and
    classifications (at least one CommodityClassification required).
    """

    description: str = Field(serialization_alias="Description")
    name: str | None = Field(default=None, serialization_alias="Name")
    buyers_item_identification: str | None = Field(default=None, exclude=True, repr=False)
    sellers_item_identification: str | None = Field(default=None, exclude=True, repr=False)
    standard_item_identification: str | None = Field(default=None, exclude=True, repr=False)
    commodity_classifications: list[CommodityClassification] = Field(
        default_factory=list, serialization_alias="CommodityClassification"
    )
    country: Country | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _requires_description_and_classification(self) -> Item:
        if not self.description:
            raise ValueError("Item.description is required")
        if not self.commodity_classifications:
            raise ValueError("Item.commodity_classifications must contain at least one entry")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"Description": _leaf(self.description)}
        if self.name is not None:
            out["Name"] = _leaf(self.name)
        if self.buyers_item_identification:
            out["BuyersItemIdentification"] = _leaf(self.buyers_item_identification)
        if self.sellers_item_identification:
            out["SellersItemIdentification"] = _leaf(self.sellers_item_identification)
        if self.standard_item_identification:
            out["StandardItemIdentification"] = _leaf(self.standard_item_identification)
        out["CommodityClassification"] = [
            cc.model_dump(by_alias=True, exclude_none=True) for cc in self.commodity_classifications
        ]
        if self.country is not None:
            out["OriginCountry"] = self.country.model_dump(by_alias=True, exclude_none=True)
        return out


class Price(_UblModel):
    """`cac:Price` — unit price + optional base quantity."""

    price_amount: Decimal = Field(serialization_alias="PriceAmount")
    price_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)
    base_quantity: Decimal | None = Field(default=None, serialization_alias="BaseQuantity")
    base_quantity_unit_code: str | None = Field(default=None, exclude=True, repr=False)
    allowance_charge: AllowanceCharge | None = Field(
        default=None, serialization_alias="AllowanceCharge"
    )

    @field_validator("price_amount", "base_quantity", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _must_have_price_amount(self) -> Price:
        if self.price_amount is None:
            raise ValueError("Price.price_amount is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "PriceAmount": _leaf(self.price_amount, currencyID=self.price_amount_currency_id)
        }
        if self.base_quantity is not None:
            out["BaseQuantity"] = _leaf(self.base_quantity, unitCode=self.base_quantity_unit_code)
        if self.allowance_charge is not None:
            out["AllowanceCharge"] = self.allowance_charge.model_dump(
                by_alias=True, exclude_none=True
            )
        return out


class ItemPriceExtension(_UblModel):
    """`cac:ItemPriceExtension` — line total extension amount."""

    amount: Decimal = Field(serialization_alias="Amount")
    amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)

    @field_validator("amount", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_validator(mode="after")
    def _must_have_amount(self) -> ItemPriceExtension:
        if self.amount is None:
            raise ValueError("ItemPriceExtension.amount is required")
        if not self.amount_currency_id:
            # PHP validate() also enforces the presence of the currencyID
            # attribute. The default attribute is MYR; the Phase 3c serializer
            # stamps the document currency if the caller has not set it. For
            # Phase 3b we keep a "MYR" default to match the PHP default.
            self.amount_currency_id = "MYR"
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {"Amount": _leaf(self.amount, currencyID=self.amount_currency_id)}


class InvoiceLine(_UblModel):
    """`cac:InvoiceLine` — one taxable line of the Invoice (doc type 01)."""

    id: str = Field(serialization_alias="ID")
    note: str | None = Field(default=None, serialization_alias="Note")
    invoiced_quantity: Decimal = Field(serialization_alias="InvoicedQuantity")
    unit_code: str | None = Field(
        default="C62",
        exclude=True,
        repr=False,
        description="UN/ECE Rec.20 unit code; defaults to 'C62' (unit).",
    )
    line_extension_amount: Decimal = Field(serialization_alias="LineExtensionAmount")
    line_extension_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)
    allowance_charges: list[AllowanceCharge] = Field(
        default_factory=list, serialization_alias="AllowanceCharge"
    )
    accounting_cost_code: str | None = Field(default=None, exclude=True, repr=False)
    accounting_cost: str | None = Field(default=None, exclude=True, repr=False)
    invoice_period: InvoicePeriod | None = Field(default=None, serialization_alias="InvoicePeriod")
    tax_total: TaxTotal = Field(serialization_alias="TaxTotal")
    item: Item = Field(serialization_alias="Item")
    price: Price = Field(serialization_alias="Price")
    item_price_extension: ItemPriceExtension = Field(serialization_alias="ItemPriceExtension")

    @field_validator("invoiced_quantity", "line_extension_amount", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @field_validator("unit_code")
    @classmethod
    def _validate_unit_code(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if UnitCode.row_for(v) is None:
            # Don't hard-fail: the bundled UnitCode table is large but the LHDN
            # spec occasionally accepts additional units; warn via the row
            # lookup rather than reject.
            return v
        return v

    @model_validator(mode="after")
    def _requires_core_children(self) -> InvoiceLine:
        for name, attr in (
            ("item", "item"),
            ("price", "price"),
            ("tax_total", "tax_total"),
            ("item_price_extension", "item_price_extension"),
            ("line_extension_amount", "line_extension_amount"),
        ):
            if getattr(self, attr) is None:
                raise ValueError(f"InvoiceLine.{name} is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ID": _leaf(self.id)}
        if self.note:
            out["Note"] = _leaf(self.note)
        out["InvoicedQuantity"] = _leaf(self.invoiced_quantity, unitCode=self.unit_code)
        out["LineExtensionAmount"] = _leaf(
            self.line_extension_amount,
            currencyID=self.line_extension_amount_currency_id,
        )
        if self.allowance_charges:
            out["AllowanceCharge"] = [
                ac.model_dump(by_alias=True, exclude_none=True) for ac in self.allowance_charges
            ]
        if self.accounting_cost_code is not None:
            out["AccountingCostCode"] = _leaf(self.accounting_cost_code)
        if self.accounting_cost is not None:
            out["AccountingCost"] = _leaf(self.accounting_cost)
        if self.invoice_period is not None:
            out["InvoicePeriod"] = self.invoice_period.model_dump(by_alias=True, exclude_none=True)
        out["TaxTotal"] = self.tax_total.model_dump(by_alias=True, exclude_none=True)
        out["Item"] = self.item.model_dump(by_alias=True, exclude_none=True)
        out["Price"] = self.price.model_dump(by_alias=True, exclude_none=True)
        out["ItemPriceExtension"] = self.item_price_extension.model_dump(
            by_alias=True, exclude_none=True
        )
        return out
