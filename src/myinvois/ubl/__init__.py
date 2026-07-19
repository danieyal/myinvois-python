"""UBL 2.1 document models for the MyInvois (LHDN) e-Invoice system.

This subpackage models the canonical LHDN JSON envelope's body — i.e. the
nested UBL structure with leaves as `{"_": value, **attrs}` — ready to be
wrapped by the Phase 3c envelope builder.

The representations produce the canonical wire form so signatures computed
downstream (Phase 4) match server-side.
"""

from __future__ import annotations

from ._base import _UblModel
from .address import Address, AddressLine, Country
from .common import (
    AllowanceCharge,
    Delivery,
    InvoicePeriod,
    SettlementPeriod,
    Shipment,
    TaxExchangeRate,
)
from .invoice import Invoice
from .line import (
    CommodityClassification,
    InvoiceLine,
    Item,
    ItemPriceExtension,
    Price,
)
from .monetary import LegalMonetaryTotal
from .party import (
    AccountingParty,
    Contact,
    FinancialInstitutionBranch,
    LegalEntity,
    Party,
    PartyIdentification,
    PartyTaxScheme,
)
from .payment import PayeeFinancialAccount, PaymentMeans, PaymentTerms, PrepaidPayment
from .reference import (
    AdditionalDocumentReference,
    Attachment,
    BillingReference,
    InvoiceDocumentReference,
    OrderReference,
)
from .tax import TaxCategory, TaxScheme, TaxSubTotal, TaxTotal

__all__ = [
    "AccountingParty",
    "AdditionalDocumentReference",
    "Address",
    "AddressLine",
    "AllowanceCharge",
    "Attachment",
    "BillingReference",
    "CommodityClassification",
    "Contact",
    "Country",
    "Delivery",
    "FinancialInstitutionBranch",
    "Invoice",
    "InvoiceDocumentReference",
    "InvoiceLine",
    "InvoicePeriod",
    "Item",
    "ItemPriceExtension",
    "LegalEntity",
    "LegalMonetaryTotal",
    "OrderReference",
    "Party",
    "PartyIdentification",
    "PartyTaxScheme",
    "PayeeFinancialAccount",
    "PaymentMeans",
    "PaymentTerms",
    "PrepaidPayment",
    "Price",
    "SettlementPeriod",
    "Shipment",
    "TaxCategory",
    "TaxExchangeRate",
    "TaxScheme",
    "TaxSubTotal",
    "TaxTotal",
    "_UblModel",
]
