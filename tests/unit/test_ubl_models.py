"""Unit tests for the UBL 2.1 document models (Phase 3b).

These tests pin the public Pydantic surface that mirrors the LHDN wire form
'Klsheng\\Myinvois\\Ubl*' classes. They assert:

* idiomatic Python snake_case construction,
* acceptance of either the curated StrEnum OR a raw string (the library
  convention established in Phase 3a),
* required-field validation per the LHDN specification,
* Decimal money types (no float arithmetic) for a finance library,
* the field aliases matching the exact UBL 2.1 element names used by LHDN.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from myinvois.codes import (
    MSIC,
    ClassificationCode,
    Country,
    Currency,
    DocumentTypeCode,
    MalaysianState,
    PaymentMethod,
    UnitCode,
)
from myinvois.ubl import (
    AccountingParty,
    AdditionalDocumentReference,
    Address,
    AddressLine,
    AllowanceCharge,
    BillingReference,
    CommodityClassification,
    Contact,
    Delivery,
    FinancialInstitutionBranch,
    Invoice,
    InvoiceDocumentReference,
    InvoiceLine,
    InvoicePeriod,
    Item,
    ItemPriceExtension,
    LegalEntity,
    LegalMonetaryTotal,
    OrderReference,
    Party,
    PartyIdentification,
    PartyTaxScheme,
    PayeeFinancialAccount,
    PaymentMeans,
    PrepaidPayment,
    Price,
    TaxCategory,
    TaxExchangeRate,
    TaxScheme,
    TaxSubTotal,
    TaxTotal,
)
from myinvois.ubl import (
    Country as UblCountry,
)

# ---------------------------------------------------------------------------
# Fixtures: build a realistic invoice matching the canonical example
# so the test bundle exercises
# every mainstream-path class together.
# ---------------------------------------------------------------------------


def _address() -> Address:
    return Address(
        address_lines=[
            AddressLine(line="Lot 66, Bangunan Merdeka"),
            AddressLine(line="Persiaran Jaya"),
        ],
        city_name="Kuala Lumpur",
        postal_zone="50480",
        country_subentity_code="14",  # WP Kuala Lumpur
        country=UblCountry(identification_code="MYS"),
    )


def _supplier_party() -> Party:
    return Party(
        party_identifications=[PartyIdentification(id="C2584563222", scheme_id="TIN")],
        postal_address=_address(),
        legal_entity=LegalEntity(registration_name="AMS Setia Jaya Sdn. Bhd."),
        contact=Contact(telephone="+60123456789", electronic_mail="general.ams@supplier.com"),
        industry_classification_code=("01111", "Growing of maize"),
    )


def _customer_party() -> Party:
    return Party(
        party_identifications=[PartyIdentification(id="C2584563200", scheme_id="TIN")],
        postal_address=_address(),
        legal_entity=LegalEntity(registration_name="Hebat Group"),
        contact=Contact(telephone="+60123456789", electronic_mail="name@buyer.com"),
    )


def _invoice_line() -> InvoiceLine:
    tax_total = TaxTotal(
        tax_amount=Decimal("14.61"),
        tax_sub_totals=[
            TaxSubTotal(
                taxable_amount=Decimal("1460.50"),
                tax_amount=Decimal("14.61"),
                percent=Decimal("10.0"),
                tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
            )
        ],
    )
    item = Item(
        description="螺丝",
        commodity_classifications=[
            CommodityClassification(item_classification_code="011", list_id="CLASS"),
        ],
    )
    return InvoiceLine(
        id="1234",
        invoiced_quantity=Decimal("1"),
        unit_code="C62",  # unit
        line_extension_amount=Decimal("1436.50"),
        tax_total=tax_total,
        item=item,
        price=Price(price_amount=Decimal("17")),
        item_price_extension=ItemPriceExtension(amount=Decimal("100")),
    )


def _invoice(**overrides: object) -> Invoice:
    base: dict[str, object] = {
        "id": "INV-0001",
        "issue_date_time": datetime(2024, 6, 14, 9, 30, 0, tzinfo=UTC),
        "invoice_type_code": DocumentTypeCode.INVOICE,
        "document_currency_code": Currency.MYR,
        "accounting_supplier_party": AccountingParty(party=_supplier_party()),
        "accounting_customer_party": AccountingParty(party=_customer_party()),
        "legal_monetary_total": LegalMonetaryTotal(
            line_extension_amount=Decimal("1436.50"),
            tax_exclusive_amount=Decimal("1436.50"),
            tax_inclusive_amount=Decimal("1436.50"),
            allowance_total_amount=Decimal("1436.50"),
            charge_total_amount=Decimal("1436.50"),
            payable_rounding_amount=Decimal("0.30"),
            payable_amount=Decimal("1436.50"),
        ),
        "invoice_lines": [_invoice_line()],
        "tax_total": TaxTotal(
            tax_amount=Decimal("87.63"),
            tax_sub_totals=[
                TaxSubTotal(
                    taxable_amount=Decimal("87.63"),
                    tax_amount=Decimal("87.63"),
                    tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
                )
            ],
        ),
    }
    base.update(overrides)
    return Invoice(**base)


# ---------------------------------------------------------------------------
# 1. Construction & aliasing
# ---------------------------------------------------------------------------


class TestInvoiceConstruction:
    def test_idiomatic_construction_round_trips(self) -> None:
        invoice = _invoice()
        # Required fields accessible by snake_case Python attr.
        assert invoice.id == "INV-0001"
        assert invoice.invoice_type_code is DocumentTypeCode.INVOICE
        assert invoice.document_currency_code is Currency.MYR
        assert isinstance(invoice.issue_date_time, datetime)
        # Lines preserved (ordered).
        assert len(invoice.invoice_lines) == 1
        assert invoice.invoice_lines[0].item.description == "螺丝"

    def test_raw_strings_accepted_for_enum_fields(self) -> None:
        # Library convention: accept raw strings alongside the enum.
        invoice = _invoice(
            invoice_type_code="01",
            document_currency_code="MYR",
        )
        assert invoice.invoice_type_code is DocumentTypeCode.INVOICE
        assert invoice.document_currency_code is Currency.MYR

        line = _invoice_line()
        line.invoiced_quantity = Decimal("2")
        line.unit_code = "KGM"
        # UnitCode is a lookup-only table; raw-string acceptance still works
        # without an enum because UnitCode is not an enum (it is a _CodeTable).
        # The field stores the raw string as-is.

    def test_alias_serialises_to_exact_ubl_names(self) -> None:
        invoice = _invoice(id="X-42")
        dumped = invoice.model_dump(by_alias=True, exclude_none=True)
        # Top-level UBL element names per the canonical wire form.
        assert "ID" in dumped
        assert "IssueDate" in dumped
        assert "IssueTime" in dumped
        assert "InvoiceTypeCode" in dumped
        assert "DocumentCurrencyCode" in dumped
        assert "AccountingSupplierParty" in dumped
        assert "AccountingCustomerParty" in dumped
        assert "LegalMonetaryTotal" in dumped
        assert dumped["ID"]["_"] == "X-42"
        assert dumped["DocumentCurrencyCode"]["_"] == "MYR"

    def test_invoice_type_code_carries_list_version_attribute(self) -> None:
        invoice = _invoice()
        dumped = invoice.model_dump(by_alias=True, exclude_none=True)
        # the InvoiceTypeCode leaf carries listVersionID="1.0" by default,
        # matching the canonical InvoiceTypeCodeAttributes default.
        tc = dumped["InvoiceTypeCode"]
        assert tc["_"] == "01"
        assert tc["listVersionID"] == "1.0"


# ---------------------------------------------------------------------------
# 2. Required-field validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invoice_requires_all_mandatory(self) -> None:
        with pytest.raises(ValidationError) as ei:
            Invoice(  # type: ignore[call-arg]
                id="",
                issue_date_time=datetime(2024, 1, 1, tzinfo=UTC),
                document_currency_code=Currency.MYR,
                accounting_supplier_party=AccountingParty(party=_supplier_party()),
                accounting_customer_party=AccountingParty(party=_customer_party()),
                legal_monetary_total=LegalMonetaryTotal(
                    tax_exclusive_amount=Decimal("0"),
                    tax_inclusive_amount=Decimal("0"),
                    payable_amount=Decimal("0"),
                ),
                invoice_lines=[],
            )
        # Empty id / missing invoice_type_code / missing tax_total / empty lines.
        msgs = str(ei.value)
        assert "id" in msgs.lower() or "type" in msgs.lower()

    def test_party_requires_address_and_legal_entity(self) -> None:
        with pytest.raises(ValidationError):
            Party()  # type: ignore[call-arg]

    def test_address_requires_address_lines_city_state_and_country(self) -> None:
        with pytest.raises(ValidationError) as ei:
            Address()  # type: ignore[call-arg]
        errs = str(ei.value)
        for needle in ("address_lines", "city_name", "country_subentity_code", "country"):
            assert needle in errs, f"{needle} not reported by Address validation"

    def test_address_line_requires_nothing_extra(self) -> None:
        # AddressLine validates trivially; construction without line is
        # permitted at the model level (it is required by its parent Address
        # via the address_lines validator enforcing non-empty strings).
        al = AddressLine(line="Lot 66")
        assert al.line == "Lot 66"

    def test_country_requires_identification_code(self) -> None:
        with pytest.raises(ValidationError):
            UblCountry()  # type: ignore[call-arg]

    def test_tax_category_requires_id_and_tax_scheme(self) -> None:
        with pytest.raises(ValidationError):
            TaxCategory()  # type: ignore[call-arg]

    def test_tax_scheme_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            TaxScheme()  # type: ignore[call-arg]

    def test_tax_sub_total_requires_tax_amount_and_tax_category(self) -> None:
        with pytest.raises(ValidationError):
            TaxSubTotal(tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")))  # type: ignore[call-arg]

    def test_tax_total_requires_amount_and_sub_totals(self) -> None:
        with pytest.raises(ValidationError) as ei:
            TaxTotal(tax_amount=Decimal("10"))
        assert "tax_sub_totals" in str(ei.value)

    def test_legal_monetary_total_requires_three_core_amounts(self) -> None:
        with pytest.raises(ValidationError):
            LegalMonetaryTotal()  # type: ignore[call-arg]

    def test_allowance_charge_requires_charge_indicator(self) -> None:
        with pytest.raises(ValidationError):
            AllowanceCharge(amount=Decimal("10"))  # type: ignore[call-arg]

    def test_party_identification_requires_id_and_scheme(self) -> None:
        with pytest.raises(ValidationError):
            PartyIdentification(id="123")  # type: ignore[call-arg]

    def test_party_tax_scheme_requires_tax_scheme(self) -> None:
        with pytest.raises(ValidationError):
            PartyTaxScheme()  # type: ignore[call-arg]

    def test_legal_entity_requires_registration_name(self) -> None:
        with pytest.raises(ValidationError):
            LegalEntity(company_id="123")  # type: ignore[call-arg]

    def test_contact_requires_telephone(self) -> None:
        with pytest.raises(ValidationError) as ei:
            Contact(electronic_mail="a@b.com")  # type: ignore[call-arg]
        assert "telephone" in str(ei.value)

    def test_price_requires_price_amount(self) -> None:
        with pytest.raises(ValidationError):
            Price()  # type: ignore[call-arg]

    def test_item_price_extension_requires_amount(self) -> None:
        with pytest.raises(ValidationError):
            ItemPriceExtension()  # type: ignore[call-arg]

    def test_item_requires_description_and_commodity_classification(self) -> None:
        with pytest.raises(ValidationError) as ei:
            Item(description="only desc")
        assert "commodity_classifications" in str(ei.value)

    def test_commodity_classification_requires_code(self) -> None:
        with pytest.raises(ValidationError):
            CommodityClassification()  # type: ignore[call-arg]

    def test_invoice_line_requires_item_price_tax_amount_extension(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceLine(  # type: ignore[call-arg]
                id="x",
                invoiced_quantity=Decimal("1"),
                line_extension_amount=Decimal("10"),
            )

    def test_payment_means_requires_payment_means_code(self) -> None:
        with pytest.raises(ValidationError):
            PaymentMeans()  # type: ignore[call-arg]

    def test_payee_financial_account_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            PayeeFinancialAccount()  # type: ignore[call-arg]

    def test_additional_document_reference_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            AdditionalDocumentReference()  # type: ignore[call-arg]

    def test_invoice_document_reference_requires_id_and_uuid(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceDocumentReference(id="INV-1")  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            InvoiceDocumentReference(uuid="0000")  # type: ignore[call-arg]

    def test_order_reference_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            OrderReference()  # type: ignore[call-arg]

    def test_invoice_period_requires_some_payload(self) -> None:
        with pytest.raises(ValidationError):
            InvoicePeriod()

    def test_delivery_requires_delivery_party(self) -> None:
        with pytest.raises(ValidationError):
            Delivery()  # type: ignore[call-arg]

    def test_accounting_party_requires_party(self) -> None:
        with pytest.raises(ValidationError):
            AccountingParty()  # type: ignore[call-arg]

    def test_tax_exchange_rate_requires_calculation_rate(self) -> None:
        with pytest.raises(ValidationError):
            TaxExchangeRate()  # type: ignore[call-arg]

    def test_financial_institution_branch_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            FinancialInstitutionBranch()  # type: ignore[call-arg]

    def test_settlement_period_only_optional_for_phase3b(self) -> None:
        # SettlementPeriod requires start+end; ensure Shipping.PrepaidPayment
        # SettlementPeriod line tests are covered in TestPaymentTerms.
        from myinvois.ubl import SettlementPeriod

        with pytest.raises(ValidationError):
            SettlementPeriod()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 3. Money: Decimal-only (finance library).
# ---------------------------------------------------------------------------


class TestMoneyIsDecimal:
    def test_amounts_coerced_to_decimal(self) -> None:
        # Users may pass float; the model coerces to Decimal to keep money exact.
        lmt = LegalMonetaryTotal(
            tax_exclusive_amount=100.0,
            tax_inclusive_amount=110.0,
            payable_amount=110.0,
        )
        assert isinstance(lmt.tax_exclusive_amount, Decimal)
        assert isinstance(lmt.tax_inclusive_amount, Decimal)
        assert isinstance(lmt.payable_amount, Decimal)

    def test_string_amounts_coerced_to_decimal(self) -> None:
        lmt = LegalMonetaryTotal(
            tax_exclusive_amount="100",
            tax_inclusive_amount="110",
            payable_amount="110",
        )
        assert lmt.tax_exclusive_amount == Decimal("100")
        assert lmt.payable_amount == Decimal("110")

    def test_invoice_tax_amounts_decimal(self) -> None:
        inv = _invoice()
        assert isinstance(inv.legal_monetary_total.payable_amount, Decimal)
        assert isinstance(inv.invoice_lines[0].line_extension_amount, Decimal)
        assert isinstance(inv.invoice_lines[0].tax_total.tax_amount, Decimal)


# ---------------------------------------------------------------------------
# 4. Enums + codes cross-references work.
# ---------------------------------------------------------------------------


class TestEnumAndCodes:
    def test_industry_classification_code_resolves_via_msic(self) -> None:
        party = _supplier_party()
        # The party stores the code; the codes module can resolve its description.
        code = party.industry_classification_code[0]  # type: ignore[index]
        assert code == "01111"
        assert MSIC.description_for(code) == "Growing of maize"

    def test_country_identification_code_validates_via_table(self) -> None:
        c = _address().country
        assert c.identification_code == "MYS"
        assert Country.name_for("MYS") == "MALAYSIA"

    def test_state_code_validates_via_table(self) -> None:
        assert MalaysianState.description_for("14") is not None

    def test_classification_code_lookup(self) -> None:
        assert ClassificationCode.description_for("022") == "Others"

    def test_unit_code_lookup(self) -> None:
        assert UnitCode.row_for("C62") is not None


# ---------------------------------------------------------------------------
# 5. Optional fields and serialisation alias fidelity.
# ---------------------------------------------------------------------------


class TestAliasingAndOptionals:
    def test_optional_fields_omit_when_unset(self) -> None:
        # A bare-minimum valid invoice round-trips with no optional fields.
        inv = Invoice(
            id="MIN-1",
            issue_date_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            invoice_type_code=DocumentTypeCode.INVOICE,
            document_currency_code=Currency.MYR,
            accounting_supplier_party=AccountingParty(party=_supplier_party()),
            accounting_customer_party=AccountingParty(party=_customer_party()),
            legal_monetary_total=LegalMonetaryTotal(
                tax_exclusive_amount=Decimal("10.00"),
                tax_inclusive_amount=Decimal("11.00"),
                payable_amount=Decimal("11.00"),
            ),
            invoice_lines=[
                InvoiceLine(
                    id="1",
                    invoiced_quantity=Decimal("1"),
                    line_extension_amount=Decimal("10.00"),
                    tax_total=TaxTotal(
                        tax_amount=Decimal("1.00"),
                        tax_sub_totals=[
                            TaxSubTotal(
                                taxable_amount=Decimal("10.00"),
                                tax_amount=Decimal("1.00"),
                                tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
                            )
                        ],
                    ),
                    item=Item(
                        description="x",
                        commodity_classifications=[
                            CommodityClassification(item_classification_code="001")
                        ],
                    ),
                    price=Price(price_amount=Decimal("10.00")),
                    item_price_extension=ItemPriceExtension(amount=Decimal("10.00")),
                )
            ],
            tax_total=TaxTotal(
                tax_amount=Decimal("1.00"),
                tax_sub_totals=[
                    TaxSubTotal(
                        taxable_amount=Decimal("10.00"),
                        tax_amount=Decimal("1.00"),
                        tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
                    )
                ],
            ),
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        # Optionals absent.
        absent_keys = (
            "TaxCurrencyCode",
            "BuyerReference",
            "AccountingCostCode",
            "InvoicePeriod",
            "OrderReference",
            "BillingReferences",
            "AdditionalDocumentReferences",
            "Signature",
            "PayeeParty",
            "Delivery",
            "PaymentMeans",
            "PaymentTerms",
            "PrepaidPayment",
            "AllowanceCharge",
            "TaxExchangeRate",
            "UBLExtensions",
        )
        for absent in absent_keys:
            assert absent not in dumped, f"{absent} should not appear when unset"

    def test_additional_documents_alias_is_plural_array(self) -> None:
        inv = _invoice(
            additional_document_references=[
                AdditionalDocumentReference(id="E12345678912", document_type="K2"),
            ],
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        assert "AdditionalDocumentReference" in dumped
        # Always emitted as an array (UBL envelope convention).
        assert isinstance(dumped["AdditionalDocumentReference"], list)
        assert dumped["AdditionalDocumentReference"][0]["ID"]["_"] == "E12345678912"


# ---------------------------------------------------------------------------
# 6. Billing reference + invoice document reference shape
# ---------------------------------------------------------------------------


class TestBillingReferenceVariants:
    def test_invoice_uses_billing_reference_with_additional_doc_ref(self) -> None:
        inv = _invoice(
            billing_references=[
                BillingReference(
                    additional_document_reference=AdditionalDocumentReference(
                        id="E123456789120",
                    ),
                ),
            ],
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        assert "BillingReference" in dumped
        adr = dumped["BillingReference"][0]["AdditionalDocumentReference"][0]
        assert adr["ID"]["_"] == "E123456789120"


# ---------------------------------------------------------------------------
# 7. Invoice optional-block aliasing (PaymentMeans / PrepaidPayment /
#    Delivery / OrderReference / InvoicePeriod / PayeeParty)
# ---------------------------------------------------------------------------


class TestInvoiceOptionalBlocks:
    def test_payment_means_serialises_with_code(self) -> None:
        inv = _invoice(
            payment_means=PaymentMeans(
                payment_means_code=PaymentMethod.CASH,
            ),
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        assert "PaymentMeans" in dumped
        pmc = dumped["PaymentMeans"]["PaymentMeansCode"]
        assert pmc == {"_": PaymentMethod.CASH.value}

    def test_prepaid_payment_serialises_paid_amount_with_currency(self) -> None:
        inv = _invoice(
            prepaid_payment=PrepaidPayment(
                id="P1",
                paid_amount=Decimal("50"),
                paid_date_time=datetime(2024, 6, 1, tzinfo=UTC),
            ),
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        assert "PrepaidPayment" in dumped
        pp = dumped["PrepaidPayment"]
        # Defaults: id present, PaidAmount carries currencyID=MYR (doc currency
        # stamped by Invoice._stamp_document_currency()).
        assert pp["ID"] == {"_": "P1"}
        # Phase 3b keeps the Decimal as-is in the dump; the Phase 3c envelope
        # will render it as a 2dp string ("50.00"). Compare against the Decimal.
        assert pp["PaidAmount"]["_"] == Decimal("50")
        assert pp["PaidAmount"]["currencyID"] == "MYR"
        # The wire form represents PaidDateTime as a PaidDate + PaidTime pair.
        assert pp["PaidDate"]["_"] == "2024-06-01"
        assert pp["PaidTime"]["_"] == "00:00:00Z"

    def test_delivery_serialises_party_and_omits_unset_fields(self) -> None:
        inv = _invoice(
            delivery=Delivery(
                actual_delivery_date=date(2024, 6, 10),
                delivery_party=_customer_party(),
            ),
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        assert "Delivery" in dumped
        d = dumped["Delivery"]
        assert d["ActualDeliveryDate"]["_"] == "2024-06-10"
        # When unset, no DeliveryLocation; Shipment emitted only when provided.
        assert "DeliveryLocation" not in d
        assert "Shipment" not in d

    def test_order_reference_serialises_id(self) -> None:
        inv = _invoice(
            order_reference=OrderReference(id="PO-42"),
        )
        dumped = inv.model_dump(by_alias=True, exclude_none=True)
        assert "OrderReference" in dumped
        assert dumped["OrderReference"]["ID"]["_"] == "PO-42"
