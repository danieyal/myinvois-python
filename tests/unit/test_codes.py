"""Tests for myinvois.codes — LHDN enumerated code tables.

All tables are loaded lazily from JSON data packaged with the library
(extracted from reference code tables via
``scripts/extract_codes.py``). The small / curated tables (Malaysian states,
tax types, payment means, document types, currency) are also exposed as
``StrEnum`` members; the larger tables (classification, country, MSIC, unit)
are exposed only via lookup helpers since inlining thousands of entries into
source would bloat the package.
"""

from __future__ import annotations

from typing import Protocol

import pytest

from myinvois.codes import (
    MSIC,
    ClassificationCode,
    Country,
    Currency,
    DocumentTypeCode,
    MalaysianState,
    PaymentMethod,
    TaxType,
    UnitCode,
)


class _HasAllRows(Protocol):
    def all_rows(self) -> list[dict[str, str]]: ...


# ---- enums ---------------------------------------------------------------


def test_malaysian_state_enum() -> None:
    assert MalaysianState.JOHOR.value == "01"
    assert MalaysianState.WP_KUALA_LUMPUR.value == "14"
    assert MalaysianState.NOT_APPLICABLE.value == "17"
    assert str(MalaysianState.JOHOR) == "01"


def test_tax_type_enum() -> None:
    assert TaxType.SALES_TAX.value == "01"
    assert TaxType.SERVICE_TAX.value == "02"
    assert TaxType.TOURISM_TAX.value == "03"
    assert TaxType.NOT_APPLICABLE.value == "06"


def test_payment_method_enum() -> None:
    assert PaymentMethod.CASH.value == "01"
    assert PaymentMethod.BANK_TRANSFER.value == "03"
    assert PaymentMethod.OTHERS.value == "08"


def test_document_type_enum_covers_all_8() -> None:
    expected = {"01", "02", "03", "04", "11", "12", "13", "14"}
    assert {member.value for member in DocumentTypeCode} == expected


def test_document_type_is_self_billed_helper() -> None:
    assert DocumentTypeCode.INVOICE.is_self_billed is False
    assert DocumentTypeCode.SELF_BILLED_INVOICE.is_self_billed is True
    assert DocumentTypeCode.SELF_BILLED_REFUND_NOTE.is_self_billed is True


def test_classification_code_lookup_only_no_enum() -> None:
    # Classification codes have long free-text descriptions that don't map
    # cleanly to Python identifiers, so the table is lookup-only (no enum).
    assert ClassificationCode.description_for("001") == "Breastfeeding equipment"
    assert ClassificationCode.description_for("022") == "Others"
    assert ClassificationCode.description_for("999") is None


def test_currency_enum_has_myr() -> None:
    assert Currency.MYR.value == "MYR"


# ---- loaders (all tables) ------------------------------------------------


_LOADERS: list[tuple[_HasAllRows, int]] = [
    (MalaysianState, 17),
    (TaxType, 6),
    (PaymentMethod, 8),
    (ClassificationCode, 45),
    (Currency, 180),
    (Country, 253),
    (MSIC, 1174),
    (UnitCode, 1834),
]


@pytest.mark.parametrize(("loader", "expected_len"), _LOADERS)
def test_table_loads_all_known_rows(loader: _HasAllRows, expected_len: int) -> None:
    rows = loader.all_rows()
    assert len(rows) == expected_len


def test_lookup_by_code_returns_description() -> None:
    assert MalaysianState.description_for("01") == "Johor"
    assert TaxType.description_for("02") == "Service Tax"
    assert PaymentMethod.description_for("06") == "e-Wallet / Digital Wallet"
    assert Country.name_for("MYS") == "MALAYSIA"
    assert Currency.name_for("MYR") == "Malaysian Ringgit"
    assert ClassificationCode.description_for("001") == "Breastfeeding equipment"


def test_lookup_returns_none_for_unknown_code() -> None:
    assert MalaysianState.description_for("99") is None
    assert Country.name_for("ZZZ") is None


def test_msic_lookup_has_all_three_fields() -> None:
    # MSIC 01111 = "Growing of maize", category A.
    row = MSIC.row_for("01111")
    assert row is not None
    assert row["description"] == "Growing of maize"
    assert row["category_ref"] == "A"


def test_unit_lookup_has_name_and_description() -> None:
    row = UnitCode.row_for("KGM")
    assert row is not None
    assert row["name"] == "kilogram"
    # KGM has a real description text.
    assert row["description"] == "A unit of mass equal to one thousand grams."


def test_enum_has_convenience_value_property() -> None:
    # All exposed enums must be StrEnum so `== "01"` works at runtime.
    assert isinstance(MalaysianState.JOHOR, str)
    assert MalaysianState.JOHOR.value == "01"


def test_table_is_cached_after_first_load() -> None:
    a = MalaysianState.all_rows()
    b = MalaysianState.all_rows()
    # Same cached instance — no re-decoding on every call.
    assert a is b


def test_document_type_str_or_enum_accepted() -> None:
    # Library convention: services accept either the enum or the raw str.
    assert DocumentTypeCode("01") is DocumentTypeCode.INVOICE
    assert DocumentTypeCode.coerce("01") is DocumentTypeCode.INVOICE
    assert DocumentTypeCode.coerce(DocumentTypeCode.INVOICE) is DocumentTypeCode.INVOICE


def test_msic_category_helper() -> None:
    from myinvois.codes import msic_category_for

    assert msic_category_for("01111") == "A"
    assert msic_category_for("00000") is not None
    assert msic_category_for("zzzzz") is None
