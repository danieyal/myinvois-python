"""MyInvois (LHDN) enumerated code tables.

All tables are loaded lazily from JSON data packaged with the library (see
``_data/``). The data was extracted from LHDN reference
code tables via ``scripts/extract_codes.py``.

Two kinds of tables are exposed:

* **Lookup-only tables** (``ClassificationCode``, ``Country``, ``MSIC``,
  ``UnitCode``) — too many rows or unwieldy descriptions to surface as enum
  members. They are *instances* of ``_CodeTable`` exposing ``all_rows()``,
  ``row_for(code)`` and ``description_for(code)`` (or ``name_for(code)``).

* **Enum + lookup tables** (``MalaysianState``, ``TaxType``,
  ``PaymentMethod``, ``DocumentTypeCode``, ``Currency``) — small / curated
  enough that the values are also available as ``StrEnum`` members, so callers
  get IDE autocomplete and a single source of truth. The same lookup helpers
  (``all_rows`` / ``row_for`` / ``description_for`` / ``name_for``) are
  available as classmethods on the enum, delegating to a JSON-backed loader
  registered at module import time.
"""

from __future__ import annotations

import json
from enum import StrEnum
from importlib import resources

__all__ = [
    "MSIC",
    "ClassificationCode",
    "Country",
    "Currency",
    "DocumentTypeCode",
    "MalaysianState",
    "PaymentMethod",
    "TaxType",
    "UnitCode",
]


# ---------------------------------------------------------------------------
# Generic JSON-backed loader
# ---------------------------------------------------------------------------


class _CodeTable:
    """Loaded lazily from a JSON file in ``myinvois/codes/_data/``.

    Each instance caches its rows and a code→row index so repeat lookups
    are free.
    """

    def __init__(
        self,
        filename: str,
        *,
        code_field: str = "code",
        description_field: str | None = "description",
        name_field: str | None = "name",
    ) -> None:
        self._filename = filename
        self._code_field = code_field
        self._description_field = description_field
        self._name_field = name_field
        self._rows_cache: list[dict[str, str]] | None = None
        self._index_cache: dict[str, dict[str, str]] | None = None

    # --- public API -------------------------------------------------------

    def all_rows(self) -> list[dict[str, str]]:
        return self._rows()

    def row_for(self, code: str) -> dict[str, str] | None:
        return self._index().get(code)

    def description_for(self, code: str) -> str | None:
        if self._description_field is None:
            raise TypeError(f"{self._filename} has no description field")
        row = self._index().get(code)
        return row[self._description_field] if row else None

    def name_for(self, code: str) -> str | None:
        if self._name_field is None:
            raise TypeError(f"{self._filename} has no name field")
        row = self._index().get(code)
        return row[self._name_field] if row else None

    # --- internals --------------------------------------------------------

    def _rows(self) -> list[dict[str, str]]:
        if self._rows_cache is None:
            pkg = "myinvois.codes._data"
            text = resources.files(pkg).joinpath(self._filename).read_text(encoding="utf-8")
            self._rows_cache = json.loads(text)
        return self._rows_cache

    def _index(self) -> dict[str, dict[str, str]]:
        if self._index_cache is None:
            self._index_cache = {row[self._code_field]: row for row in self._rows()}
        return self._index_cache


# ---------------------------------------------------------------------------
# Lookup-only tables (no enum)
# ---------------------------------------------------------------------------

ClassificationCode = _CodeTable(
    "classification.json", description_field="description", name_field=None
)
Country = _CodeTable("countries.json", description_field=None, name_field="name")
MSIC = _CodeTable("msic.json", description_field="description", name_field=None)
UnitCode = _CodeTable("units.json", description_field="description", name_field="name")


def msic_category_for(code: str) -> str | None:
    """Return the MSIC category reference letter (A to U) or ``None``."""
    row = MSIC.row_for(code)
    return row["category_ref"] if row else None


# ---------------------------------------------------------------------------
# Enum tables
# ---------------------------------------------------------------------------

# Registry mapping each enum class -> its loader instance. Populated after
# each enum is defined. We keep this in a module-level dict because Python
# enums forbid adding new class attributes after creation.
_ENUM_LOADERS: dict[type, _CodeTable] = {}


def _enum_loader(enum_cls: type) -> _CodeTable:
    loader = _ENUM_LOADERS.get(enum_cls)
    if loader is None:
        raise LookupError(f"no loader registered for {enum_cls!r}")
    return loader


class _EnumLookupMixin:
    """Lookup helpers shared by the enum code tables.

    Subclassing ``StrEnum`` directly would make any class-body value look
    like an enum member, so the lookup helpers live on this plain mixin and
    delegate to a per-class loader registered in ``_ENUM_LOADERS``.
    """

    @classmethod
    def all_rows(cls) -> list[dict[str, str]]:
        return _enum_loader(cls).all_rows()

    @classmethod
    def row_for(cls, code: str) -> dict[str, str] | None:
        return _enum_loader(cls).row_for(code)

    @classmethod
    def description_for(cls, code: str) -> str | None:
        return _enum_loader(cls).description_for(code)

    @classmethod
    def name_for(cls, code: str) -> str | None:
        return _enum_loader(cls).name_for(code)


class MalaysianState(_EnumLookupMixin, StrEnum):
    """Malaysian state codes (17 incl. 'Not Applicable')."""

    JOHOR = "01"
    KEDAH = "02"
    KELANTAN = "03"
    MELAKA = "04"
    NEGERI_SEMBILAN = "05"
    PAHANG = "06"
    PULAU_PINANG = "07"
    PERAK = "08"
    PERLIS = "09"
    SELANGOR = "10"
    TERENGGANU = "11"
    SABAH = "12"
    SARAWAK = "13"
    WP_KUALA_LUMPUR = "14"
    WP_LABUAN = "15"
    WP_PUTRAJAYA = "16"
    NOT_APPLICABLE = "17"


class TaxType(_EnumLookupMixin, StrEnum):
    """LHDN tax type codes (6 incl. 'Not Applicable')."""

    SALES_TAX = "01"
    SERVICE_TAX = "02"
    TOURISM_TAX = "03"
    HIGH_VALUE_GOODS_TAX = "04"
    SALES_TAX_LOW_VALUE_GOODS = "05"
    NOT_APPLICABLE = "06"


class PaymentMethod(_EnumLookupMixin, StrEnum):
    """LHDN payment method (payment means) codes (8)."""

    CASH = "01"
    CHEQUE = "02"
    BANK_TRANSFER = "03"
    CREDIT_CARD = "04"
    DEBIT_CARD = "05"
    E_WALLET = "06"
    DIGITAL_BANK = "07"
    OTHERS = "08"


class DocumentTypeCode(_EnumLookupMixin, StrEnum):
    """LHDN document type codes (4 invoice-side + 4 self-billed)."""

    INVOICE = "01"
    CREDIT_NOTE = "02"
    DEBIT_NOTE = "03"
    REFUND_NOTE = "04"
    SELF_BILLED_INVOICE = "11"
    SELF_BILLED_CREDIT_NOTE = "12"
    SELF_BILLED_DEBIT_NOTE = "13"
    SELF_BILLED_REFUND_NOTE = "14"

    @property
    def is_self_billed(self) -> bool:
        """True for the 11-14 self-billed document variants."""
        return self.value >= "11"

    @classmethod
    def coerce(cls, value: DocumentTypeCode | str) -> DocumentTypeCode:
        """Accept either the enum or its raw string value."""
        if isinstance(value, cls):
            return value
        return cls(value)


class Currency(_EnumLookupMixin, StrEnum):
    """ISO 4217 currency codes used by LHDN (180).

    Only a handful of the most common currencies are surfaced as enum
    members; everything else is reachable via ``name_for`` / ``row_for``.
    """

    MYR = "MYR"
    USD = "USD"
    SGD = "SGD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CNY = "CNY"
    THB = "THB"
    IDR = "IDR"
    AUD = "AUD"
    INR = "INR"


# ---------------------------------------------------------------------------
# Register loaders for each enum
# ---------------------------------------------------------------------------

_ENUM_LOADERS[MalaysianState] = _CodeTable(
    "states.json", description_field="name", name_field="name"
)
_ENUM_LOADERS[TaxType] = _CodeTable(
    "taxes.json", description_field="description", name_field="description"
)
_ENUM_LOADERS[PaymentMethod] = _CodeTable(
    "payment_means.json", description_field="name", name_field="name"
)
_ENUM_LOADERS[Currency] = _CodeTable("currencies.json", description_field=None, name_field="name")


# DocumentTypeCode has no JSON table (InvoiceTypeCodes has only constants, no
# getItems), so we register a tiny loader that returns synthetic rows built
# from the enum members.
class _SyntheticInvoiceTypeLoader(_CodeTable):
    def _rows(self) -> list[dict[str, str]]:
        if self._rows_cache is None:
            self._rows_cache = [
                {"code": m.value, "name": m.name.replace("_", " ").title()}
                for m in DocumentTypeCode
            ]
        return self._rows_cache


_ENUM_LOADERS[DocumentTypeCode] = _SyntheticInvoiceTypeLoader(
    "invoice_types.json", description_field=None, name_field="name"
)
