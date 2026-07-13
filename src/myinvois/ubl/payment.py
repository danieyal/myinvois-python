"""Payment-related UBL components: PaymentMeans, PayeeFinancialAccount,
PaymentTerms, PrepaidPayment.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from myinvois.codes import PaymentMethod

from ._base import _leaf, _money, _UblModel
from .common import SettlementPeriod  # placeholder import to satisfy forward reference
from .party import FinancialInstitutionBranch


class PayeeFinancialAccount(_UblModel):
    """`cac:PayeeFinancialAccount` — bank account details."""

    id: str = Field(serialization_alias="ID")
    name: str | None = Field(default=None, serialization_alias="Name")
    financial_institution_branch: FinancialInstitutionBranch | None = Field(
        default=None, serialization_alias="FinancialInstitutionBranch"
    )

    @model_validator(mode="after")
    def _must_have_id(self) -> PayeeFinancialAccount:
        if not self.id:
            raise ValueError("PayeeFinancialAccount.id is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ID": _leaf(self.id)}
        if self.name is not None:
            out["Name"] = _leaf(self.name)
        if self.financial_institution_branch is not None:
            out["FinancialInstitutionBranch"] = self.financial_institution_branch.model_dump(
                by_alias=True, exclude_none=True
            )
        return out


class PaymentMeans(_UblModel):
    """`cac:PaymentMeans` — payment channel (cash, card, bank transfer, etc.)."""

    payment_means_code: PaymentMethod | str = Field(serialization_alias="PaymentMeansCode")
    payment_due_date: date | None = Field(default=None, serialization_alias="PaymentDueDate")
    instruction_id: str | None = Field(default=None, serialization_alias="InstructionID")
    instruction_note: str | None = Field(default=None, serialization_alias="InstructionNote")
    payment_id: str | None = Field(default=None, serialization_alias="PaymentID")
    payee_financial_account: PayeeFinancialAccount | None = Field(
        default=None, serialization_alias="PayeeFinancialAccount"
    )

    @field_validator("payment_means_code", mode="before")
    @classmethod
    def _coerce_code(cls, v: object) -> object:
        if isinstance(v, str) and v:
            try:
                return PaymentMethod(v)
            except ValueError:
                return v
        return v

    @model_validator(mode="after")
    def _must_have_code(self) -> PaymentMeans:
        if not self.payment_means_code:
            raise ValueError("PaymentMeans.payment_means_code is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        code = (
            self.payment_means_code.value
            if isinstance(self.payment_means_code, PaymentMethod)
            else self.payment_means_code
        )
        out: dict[str, Any] = {"PaymentMeansCode": _leaf(code)}
        if self.payment_due_date is not None:
            out["PaymentDueDate"] = _leaf(self.payment_due_date.isoformat())
        if self.instruction_id is not None:
            out["InstructionID"] = _leaf(self.instruction_id)
        if self.instruction_note is not None:
            out["InstructionNote"] = _leaf(self.instruction_note)
        if self.payment_id is not None:
            out["PaymentID"] = _leaf(self.payment_id)
        if self.payee_financial_account is not None:
            out["PayeeFinancialAccount"] = self.payee_financial_account.model_dump(
                by_alias=True, exclude_none=True
            )
        return out


class PaymentTerms(_UblModel):
    """`cac:PaymentTerms` — payment conditions note / settlement discount."""

    note: str | None = Field(default=None, serialization_alias="Note")
    settlement_discount_percent: Decimal | None = Field(
        default=None, serialization_alias="SettlementDiscountPercent"
    )
    amount: Decimal | None = Field(default=None, serialization_alias="Amount")
    amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)
    settlement_period: SettlementPeriod | None = Field(
        default=None, serialization_alias="SettlementPeriod"
    )

    @field_validator("amount", "settlement_discount_percent", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.note is not None:
            out["Note"] = _leaf(self.note)
        if self.settlement_discount_percent is not None:
            out["SettlementDiscountPercent"] = _leaf(self.settlement_discount_percent)
        if self.amount is not None:
            out["Amount"] = _leaf(self.amount, currencyID=self.amount_currency_id)
        if self.settlement_period is not None:
            out["SettlementPeriod"] = self.settlement_period.model_dump(
                by_alias=True, exclude_none=True
            )
        return out


class PrepaidPayment(_UblModel):
    """`cac:PrepaidPayment` — prepayment already received."""

    id: str | None = Field(default=None, serialization_alias="ID")
    paid_amount: Decimal | None = Field(default=None, serialization_alias="PaidAmount")
    paid_amount_currency_id: str | None = Field(default=None, exclude=True, repr=False)
    paid_date_time: datetime | None = Field(default=None, serialization_alias="PaidDateTime")

    @field_validator("paid_amount", mode="before")
    @classmethod
    def _to_decimal(cls, v: Any) -> Any:
        return _money(v)

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.id is not None:
            out["ID"] = _leaf(self.id)
        if self.paid_amount is not None:
            out["PaidAmount"] = _leaf(self.paid_amount, currencyID=self.paid_amount_currency_id)
        if self.paid_date_time is not None:
            out["PaidDate"] = _leaf(self.paid_date_time.date().isoformat())
            out["PaidTime"] = _leaf(self.paid_date_time.strftime("%H:%M:%SZ"))
        return out
