"""Auto-extracted UBL 2.1 element namespace-prefix map.

Each key is the UBL element local-name as emitted by the per-class
_ser() serializers (e.g. 'PostalAddress', 'PriceAmount'). Each value
is the XML namespace prefix used by the PHP SDK XmlDocumentBuilder:
  * 'cbc' -- CommonBasicComponents-2
  * 'cac' -- CommonAggregateComponents-2
  * 'ext' -- CommonExtensionComponents-2

Auto-derived from src/Ubl/**/*.php occurrences of
`XmlSchema::<NS> . '<Name>'` in klsheng/myinvois-php-sdk. Treat as
authoritative -- errors here cause XAdES digest mismatch.
"""

from __future__ import annotations

__all__ = ["ELEMENT_PREFIXES"]


# ---------------------------------------------------------------------------
# Dynamic-composition sites in the PHP SDK.
# ---------------------------------------------------------------------------
#
# The PHP scanner missed a small set of elements whose tag is composed at
# runtime via `XmlSchema::CBC . $key` (variable interpolation) rather than a
# literal string. These are all `cbc:` records by UBL 2.1 XSD location:
#
# - `LegalMonetaryTotal.xmlSerialize()` uses `writeXmlAmount($writer, $key, …)`
#   where `$key` is one of: LineExtensionAmount (already mapped), TaxExclusiveAmount,
#   TaxInclusiveAmount, AllowanceTotalAmount, PrepaidAmount, ChargeTotalAmount,
#   PayableRoundingAmount, PayableAmount.
# - `InvoiceLine.xmlSerialize()` uses `XmlSchema::CBC . $this->quantityLabel`;
#   `quantityLabel` defaults to `'InvoicedQuantity'` — added to the explicit
#   `_EXTRA_CBC_KEYS` list below. Other UBL basic-component labels derived from
#   this property (e.g. `'BaseQuantity'`, `'DebitedQuantity'`, `'CreditedQuantity'`
#   in the various *Line subclasses) share the same cbc prefix and are added
#   alongside.
#
# `Invoice.xmlSerialize()` also dynamically composes the invoice-line tag via
# `XmlSchema::CAC . $invoiceLine->xmlTagName` (line 794) — `InvoiceLine::$xmlTagName`
# defaults to the literal 'InvoiceLine'. There's no other site composing this
# element name, so we register it explicitly here (cac namespace).
_EXTRA_CBC_KEYS = (
    "TaxExclusiveAmount",
    "TaxInclusiveAmount",
    "AllowanceTotalAmount",
    "PrepaidAmount",
    "ChargeTotalAmount",
    "PayableRoundingAmount",
    "PayableAmount",
    # From XmlSchema::CBC . $this->quantityLabel in InvoiceLine / DebitNoteLine /
    # CreditNoteLine — the *Line subclasses default the property to literals
    # that export these basic-component local-names. All are cbc in UBL 2.1.
    "InvoicedQuantity",
    "DebitedQuantity",
    "CreditedQuantity",
)

# Aggregate (cac) keys composed via $variable interpolation in the PHP SDK's
# per-class xmlSerialize() methods — currently only InvoiceLine.
_EXTRA_CAC_KEYS = (
    "InvoiceLine",  # XmlSchema::CAC . $invoiceLine->xmlTagName
)


ELEMENT_PREFIXES: dict[str, str] = {
    "AccountingCost": "cbc",
    "AccountingCostCode": "cbc",
    "AccountingCustomerParty": "cac",
    "AccountingSupplierParty": "cac",
    "ActualDeliveryDate": "cbc",
    "AdditionalAccountID": "cbc",
    "AdditionalDocumentReference": "cac",
    "AdditionalStreetName": "cbc",
    "Address": "cac",
    "AddressLine": "cac",
    "AllowanceCharge": "cac",
    "AllowanceChargeReason": "cbc",
    "Amount": "cbc",
    "Attachment": "cac",
    "BaseQuantity": "cbc",
    "BaseUnitMeasure": "cbc",
    "BillingReference": "cac",
    "BuildingNumber": "cbc",
    "BuyerReference": "cbc",
    "BuyersItemIdentification": "cac",
    "CalculationRate": "cbc",
    "ChargeIndicator": "cbc",
    "CityName": "cbc",
    "CommodityClassification": "cac",
    "CompanyID": "cbc",
    "Contact": "cac",
    "Country": "cac",
    "CountrySubentityCode": "cbc",
    "CurrencyCode": "cbc",
    "CustomerAssignedAccountID": "cbc",
    "Delivery": "cac",
    "DeliveryLocation": "cac",
    "DeliveryParty": "cac",
    "Description": "cbc",
    "DocumentCurrencyCode": "cbc",
    "DocumentDescription": "cbc",
    "DocumentType": "cbc",
    "DurationMeasure": "cbc",
    "ElectronicMail": "cbc",
    "EmbeddedDocumentBinaryObject": "cbc",
    "EndDate": "cbc",
    "EndpointID": "cbc",
    "ExtensionContent": "ext",
    "ExtensionURI": "ext",
    "ExternalReference": "cac",
    "FinancialInstitutionBranch": "cac",
    "FreightAllowanceCharge": "cac",
    "ID": "cbc",
    "IdentificationCode": "cbc",
    "IndustryClassificationCode": "cbc",
    "InstructionID": "cbc",
    "InstructionNote": "cbc",
    "InvoiceDocumentReference": "cac",
    "InvoicePeriod": "cac",
    "InvoiceTypeCode": "cbc",
    "IssueDate": "cbc",
    "IssueTime": "cbc",
    "Item": "cac",
    "ItemClassificationCode": "cbc",
    "ItemPriceExtension": "cac",
    "LegalMonetaryTotal": "cac",
    "Line": "cbc",
    "LineExtensionAmount": "cbc",
    "MultiplierFactorNumeric": "cbc",
    "Name": "cbc",
    "Note": "cbc",
    "OrderReference": "cac",
    "OriginCountry": "cac",
    "PaidAmount": "cbc",
    "PaidDate": "cbc",
    "PaidTime": "cbc",
    "Party": "cac",
    "PartyIdentification": "cac",
    "PartyLegalEntity": "cac",
    "PartyName": "cac",
    "PartyTaxScheme": "cac",
    "PayeeFinancialAccount": "cac",
    "PayeeParty": "cac",
    "PaymentDueDate": "cbc",
    "PaymentID": "cbc",
    "PaymentMeans": "cac",
    "PaymentMeansCode": "cbc",
    "PaymentTerms": "cac",
    "PerUnitAmount": "cbc",
    "Percent": "cbc",
    "PhysicalLocation": "cac",
    "PostalAddress": "cac",
    "PostalZone": "cbc",
    "PrepaidPayment": "cac",
    "Price": "cac",
    "PriceAmount": "cbc",
    "RegistrationName": "cbc",
    "SalesOrderID": "cbc",
    "SellersItemIdentification": "cac",
    "SettlementDiscountPercent": "cbc",
    "SettlementPeriod": "cac",
    "Shipment": "cac",
    "Signature": "cac",
    "SignatureMethod": "cbc",
    "SourceCurrencyBaseRate": "cbc",
    "SourceCurrencyCode": "cbc",
    "StandardItemIdentification": "cac",
    "StartDate": "cbc",
    "StreetName": "cbc",
    "SupplierAssignedAccountID": "cbc",
    "TargetCurrencyBaseRate": "cbc",
    "TargetCurrencyCode": "cbc",
    "TaxAmount": "cbc",
    "TaxCategory": "cac",
    "TaxCurrencyCode": "cbc",
    "TaxExchangeRate": "cac",
    "TaxExemptionReason": "cbc",
    "TaxExemptionReasonCode": "cbc",
    "TaxScheme": "cac",
    "TaxSubtotal": "cac",
    "TaxTotal": "cac",
    "TaxTypeCode": "cbc",
    "TaxableAmount": "cbc",
    "Telefax": "cbc",
    "Telephone": "cbc",
    "UBLExtension": "ext",
    "UBLExtensions": "ext",
    "URI": "cbc",
    "UUID": "cbc",
}

# Insert the dynamic-composition keys verified above. Each entry overrides
# the empty default so `_key_to_tag()` no longer falls through to the
# unprefixed branch (which would emit `<TaxExclusiveAmount>…` ouside the
# `cbc` namespace and break C14N byte-parity).
for _extra_name in _EXTRA_CBC_KEYS:
    ELEMENT_PREFIXES[_extra_name] = "cbc"
for _extra_name in _EXTRA_CAC_KEYS:
    ELEMENT_PREFIXES[_extra_name] = "cac"
del _extra_name
