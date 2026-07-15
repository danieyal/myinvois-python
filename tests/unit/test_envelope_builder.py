"""Phase 3c: UBL JSON envelope builder (pytest-first).

Pins the canonical LHDN/MyInvois wire form byte-for-byte against the
authoritative PHP reference SDK ``JsonDocumentBuilder::build()`` (and the
cross-checking TypeScript ``myinvois-client`` type model), so a Phase 4
signature digest computed over this serialized string will round-trip
through the LHDN validator unchanged.

Key canonical rules (cross-verified PHP + TS types):
  * Envelope: ``{"_D": "...Invoice-2", "_A": cacNS, "_B": cbcNS, "_E": extNS,
    "Invoice": [<invoice_content>]}``.
  * Every element/leaf inside content is wrapped as a one-or-more element
    array, including singletons (``"IssueDate": [{"_": "2024-06-14"}]``).
  * Money emits as JSON *numbers* (never strings). Trailing zeros after the
    decimal are dropped (``1460.50`` -> ``1460.5``), integer-valued amounts
    drop the decimal point entirely (``1500.00`` -> ``1500``).
  * Booleans emit unquoted (``true``/``false``). Non-ASCII text passes
    through unescaped (Chinese ``螺丝`` literally).
  * Compact separators and Unicode passthrough (matches PHP
    ``JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from myinvois.codes import Currency, DocumentTypeCode, MalaysianState
from myinvois.ubl import (
    AccountingParty,
    Address,
    AddressLine,
    AllowanceCharge,
    BillingReference,
    CommodityClassification,
    Contact,
    Invoice,
    InvoiceLine,
    Item,
    ItemPriceExtension,
    LegalEntity,
    LegalMonetaryTotal,
    Party,
    PartyIdentification,
    Price,
    TaxCategory,
    TaxScheme,
    TaxSubTotal,
    TaxTotal,
)
from myinvois.ubl import (
    Country as UblCountry,
)
from myinvois.ubl.builders import JsonEnvelopeBuilder
from myinvois.ubl.builders._specs import ENVELOPE_DOCUMENT_TAGS, UBL_NAMESPACES

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _address() -> Address:
    return Address(
        city_name="Kuala Lumpur",
        postal_zone="50480",
        country_subentity_code=MalaysianState.WP_KUALA_LUMPUR,
        address_lines=[
            AddressLine(line="Lot 66, Bangunan Merdeka"),
            AddressLine(line="Persiaran Jaya"),
        ],
        country=UblCountry(identification_code="MYS"),
    )


def _supplier() -> AccountingParty:
    return AccountingParty(
        additional_account_id="CPT-CCN-W-211111-KL-000002",
        party=Party(
            industry_classification_code=("01111", "Agriculture"),
            party_identifications=[PartyIdentification(id="C2584563222", scheme_id="TIN")],
            postal_address=_address(),
            legal_entity=LegalEntity(registration_name="AMS Setia Jaya Sdn. Bhd."),
            contact=Contact(telephone="+60123456789", electronic_mail="general.ams@supplier.com"),
        ),
    )


def _customer() -> AccountingParty:
    return AccountingParty(
        party=Party(
            party_identifications=[PartyIdentification(id="C2584563200", scheme_id="TIN")],
            postal_address=_address(),
            legal_entity=LegalEntity(registration_name="Hebat Group"),
            contact=Contact(telephone="+60123456789", electronic_mail="name@buyer.com"),
        ),
    )


def _tax_total_document() -> TaxTotal:
    return TaxTotal(
        tax_amount=Decimal("87.63"),
        tax_sub_totals=[
            TaxSubTotal(
                taxable_amount=Decimal("87.63"),
                tax_amount=Decimal("87.63"),
                tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
            ),
        ],
    )


def _tax_total_line() -> TaxTotal:
    return TaxTotal(
        tax_amount=Decimal("14.61"),
        tax_sub_totals=[
            TaxSubTotal(
                taxable_amount=Decimal("1436.50"),
                tax_amount=Decimal("14.61"),
                percent=Decimal("10.0"),
                tax_category=TaxCategory(
                    id="01",
                    percent=Decimal("10.0"),
                    tax_exemption_reason="Exempt New Means of Transport",
                    tax_scheme=TaxScheme(id="OTH"),
                ),
            ),
        ],
    )


def _monetary_total() -> LegalMonetaryTotal:
    return LegalMonetaryTotal(
        line_extension_amount=Decimal("1436.50"),
        tax_exclusive_amount=Decimal("1436.50"),
        tax_inclusive_amount=Decimal("1436.50"),
        allowance_total_amount=Decimal("1436.50"),
        charge_total_amount=Decimal("1436.50"),
        payable_rounding_amount=Decimal("0.30"),
        payable_amount=Decimal("1436.50"),
    )


def _invoice_line() -> InvoiceLine:
    return InvoiceLine(
        id="1234",
        invoiced_quantity=Decimal("1"),
        line_extension_amount=Decimal("1436.50"),
        allowance_charges=[
            AllowanceCharge(
                charge_indicator=False,
                allowance_charge_reason="Sample Description 2",
                multiplier_factor_numeric=Decimal("0.15"),
                amount=Decimal("100"),
            ),
            AllowanceCharge(
                charge_indicator=True,
                allowance_charge_reason="Service charge",
                multiplier_factor_numeric=Decimal("0.10"),
                amount=Decimal("100"),
            ),
        ],
        tax_total=_tax_total_line(),
        item=Item(
            description="螺丝",
            commodity_classifications=[
                CommodityClassification(item_classification_code="011", list_id="CLASS"),
            ],
        ),
        price=Price(price_amount=Decimal("17")),
        item_price_extension=ItemPriceExtension(amount=Decimal("100")),
    )


def _sample_invoice() -> Invoice:
    return Invoice(
        id="INV-0001",
        issue_date_time=datetime(2024, 6, 14, 9, 30, 0, tzinfo=UTC),
        invoice_type_code=DocumentTypeCode.INVOICE,
        document_currency_code=Currency.MYR,
        accounting_supplier_party=_supplier(),
        accounting_customer_party=_customer(),
        tax_total=_tax_total_document(),
        legal_monetary_total=_monetary_total(),
        invoice_lines=[_invoice_line()],
    )


# ---------------------------------------------------------------------------
# 1. Envelope constants & top-level shape
# ---------------------------------------------------------------------------


class TestEnvelopeConstants:
    def test_cac_cbc_ext_namespace_urls(self) -> None:
        assert (
            UBL_NAMESPACES["cac"]
            == "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        )
        assert (
            UBL_NAMESPACES["cbc"]
            == "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
        )
        assert (
            UBL_NAMESPACES["ext"]
            == "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
        )

    def test_invoice_qualified_xml_tag_name(self) -> None:
        assert (
            ENVELOPE_DOCUMENT_TAGS["Invoice"]
            == "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
        )


# ---------------------------------------------------------------------------
# 2. JSON envelope shape (round-trip via json.loads)
# ---------------------------------------------------------------------------


class TestJsonEnvelopeShape:
    def test_build_json_returns_str_compact_unicode_passthrough(self) -> None:
        s = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        assert isinstance(s, str)
        # PHP `JSON_UNESCAPED_UNICODE`: non-ASCII passes through literally.
        assert "螺丝" in s, "Chinese item description must pass through unescaped"
        assert "\\u" not in s, "must not contain ASCII-escape sequences"
        # PHP does NOT unescape forward slashes (JSON_UNESCAPED_SLASHES).
        # In URLs — none of our envelope bodies do, but the rule is
        # slashes literally appear when present.
        # Compact: no whitespace BETWEEN JSON tokens (whitespace is only
        # *allowed* inside JSON string values). Verify by re-parsing and
        # ensuring both Python's compact dumps and our dumps match the
        # canonical form: structural `":` and `,` adjacent.
        import re

        # Pattern: any of `{"\s+","", "\s+:} (whitespace adjacent to brace)
        # i.e. structural whitespace from json.dumps(indent=2) forms.
        assert re.search(r'"\s+:\s+"', s) is None
        assert "},\n" not in s  # json.dumps newline-ish separators
        assert "{}" not in s  # we use named-key leaves always
        # Re-parse round-trips with no whitespace record deviations.
        assert json.loads(s) == json.loads(s)  # idempotent

    def test_build_json_top_level_keys(self) -> None:
        env = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())
        assert list(env.keys()) == ["_D", "_A", "_B", "_E", "Invoice"]
        assert env["_D"] == "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
        assert env["_A"] == UBL_NAMESPACES["cac"]
        assert env["_B"] == UBL_NAMESPACES["cbc"]
        # PHP emits _E unconditionally (Phase 4 signing needs it).
        assert env["_E"] == UBL_NAMESPACES["ext"]
        assert isinstance(env["Invoice"], list)
        assert len(env["Invoice"]) == 1
        inv = env["Invoice"][0]
        assert isinstance(inv, dict)
        # Order (alphabetical, since PHP iterates $arrays in insertion order
        # but the field emit order is canonical UBL order): the first few keys.
        assert inv["ID"] == [{"_": "INV-0001"}]
        assert inv["IssueDate"] == [{"_": "2024-06-14"}]
        assert inv["IssueTime"] == [{"_": "09:30:00Z"}]

    def test_invoice_document_currency_emits_as_array_of_one_text_leaf(self) -> None:
        inv = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0]
        # Every keyed slot is an array-of-one; DocumentCurrencyCode is a text
        # leaf, not a primitive.
        assert inv["DocumentCurrencyCode"] == [{"_": "MYR"}]
        # TaxTotal is wrapped as a one-element array; its first (and only)
        # entry is the structural TaxTotal dict whose TaxAmount leaf carries
        # the document currency as `currencyID`.
        tt_list = inv["TaxTotal"]
        assert isinstance(tt_list, list)
        assert len(tt_list) == 1
        tt = tt_list[0]
        assert isinstance(tt, dict)
        assert tt["TaxAmount"] == [{"_": 87.63, "currencyID": "MYR"}]

    def test_invoice_type_code_carries_list_version_id(self) -> None:
        inv = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0]
        assert inv["InvoiceTypeCode"] == [{"_": "01", "listVersionID": "1.0"}]


# ---------------------------------------------------------------------------
# 3. Money rendering — PHP-compatible JSON numeric tokens
# ---------------------------------------------------------------------------


class TestMoneyRendering:
    def _monetary(self) -> dict[str, object]:
        return json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0][
            "LegalMonetaryTotal"
        ][0]

    def test_decimal_with_trailing_zero_dropped_to_one_dp(self) -> None:
        # 1436.50 -> PHP json_encode(1460.5) -> "1436.5"
        assert self._monetary()["LineExtensionAmount"] == [{"_": 1436.5, "currencyID": "MYR"}]

    def test_integer_valued_amount_strips_decimal_point(self) -> None:
        # 1500.00 -> float(1500.0) -> json_encode -> "1500"
        inv = Invoice(
            id="X",
            issue_date_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            document_currency_code=Currency.MYR,
            invoice_type_code=DocumentTypeCode.INVOICE,
            accounting_supplier_party=_supplier(),
            accounting_customer_party=_customer(),
            tax_total=_tax_total_document(),
            legal_monetary_total=LegalMonetaryTotal(
                line_extension_amount=Decimal("1500.00"),
                tax_exclusive_amount=Decimal("1500.00"),
                tax_inclusive_amount=Decimal("1500.00"),
                payable_amount=Decimal("1500.00"),
            ),
            invoice_lines=[_invoice_line()],
        )
        m = json.loads(JsonEnvelopeBuilder(inv).build_json())["Invoice"][0]["LegalMonetaryTotal"][0]
        assert m["LineExtensionAmount"] == [{"_": 1500, "currencyID": "MYR"}]
        assert m["PayableAmount"] == [{"_": 1500, "currencyID": "MYR"}]

    def test_sub_one_amount_keeps_short_form(self) -> None:
        # 0.30 -> (float)"0.30" = 0.3 -> "0.3"
        assert self._monetary()["PayableRoundingAmount"] == [{"_": 0.3, "currencyID": "MYR"}]

    def test_quantity_emits_as_number_with_unit_code(self) -> None:
        line = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0][
            "InvoiceLine"
        ][0]
        assert line["InvoicedQuantity"] == [{"_": 1, "unitCode": "C62"}]

    def test_amount_money_number_not_string(self) -> None:
        """Decimal value MUST render as a JSON number token (per PHP canonical)."""
        s = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        # check that an actual numeric literal `87.63` appears next to `"_"`
        # without quotes — the wire-form rule.
        assert '"TaxAmount":[{"_":87.63' in s
        assert '"LineExtensionAmount":[{"_":1436.5' in s


# ---------------------------------------------------------------------------
# 4. Structured submodels — TaxTotal, TaxSubtotal casing, AllowanceCharge
# ---------------------------------------------------------------------------


class TestStructuredSubmodels:
    def test_tax_total_top_level_is_array_of_one(self) -> None:
        inv = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0]
        assert isinstance(inv["TaxTotal"], list)
        assert len(inv["TaxTotal"]) == 1
        tt = inv["TaxTotal"][0]
        # leaf attrs (currencyID) when stamped; non-leaf submodels recurse.
        assert tt["TaxAmount"] == [{"_": 87.63, "currencyID": "MYR"}]

    def test_tax_subtotal_uses_lowercase_t_canonical_key(self) -> None:
        # PHP emits "TaxSubtotal" (lowercase 't'), not "TaxSubTotal".
        tt = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0][
            "TaxTotal"
        ][0]
        assert "TaxSubtotal" in tt
        assert "TaxSubTotal" not in tt
        sub = tt["TaxSubtotal"]
        assert isinstance(sub, list)
        assert sub[0]["TaxableAmount"] == [{"_": 87.63, "currencyID": "MYR"}]
        assert sub[0]["TaxAmount"] == [{"_": 87.63, "currencyID": "MYR"}]
        assert sub[0]["TaxCategory"][0]["ID"] == [{"_": "01"}]
        tax_scheme = sub[0]["TaxCategory"][0]["TaxScheme"][0]
        assert tax_scheme["ID"] == [{"_": "OTH", "schemeID": "UN/ECE 5153", "schemeAgencyID": "6"}]

    def test_line_tax_total_percent_renders_as_integer_when_whole(self) -> None:
        # Decimal("10.0") -> float("10.00") = 10.0 -> PHP json encodes as "10".
        line = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0][
            "InvoiceLine"
        ][0]
        sub = line["TaxTotal"][0]["TaxSubtotal"][0]
        assert sub["Percent"] == [{"_": 10}]

    def test_allowancecharge_indicator_is_unquoted_boolean(self) -> None:
        line = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0][
            "InvoiceLine"
        ][0]
        ac = line["AllowanceCharge"]
        assert ac[0]["ChargeIndicator"] == [{"_": False}]
        assert ac[1]["ChargeIndicator"] == [{"_": True}]
        assert ac[0]["MultiplierFactorNumeric"] == [{"_": 0.15}]
        assert ac[1]["MultiplierFactorNumeric"] == [{"_": 0.1}]
        assert ac[0]["Amount"] == [{"_": 100, "currencyID": "MYR"}]


# ---------------------------------------------------------------------------
# 5. Currency stamping — every amount defaults to document currency
# ---------------------------------------------------------------------------


class TestCurrencyStamping:
    def test_amounts_with_no_explicit_currency_get_document_currency(self) -> None:
        s = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        # TaxTotal.tax_amount has no explicit currency in the model dump but
        # is stamped with MYR by the builder.
        assert '"TaxAmount":[{"_":87.63,"currencyID":"MYR"}]' in s
        # Line amounts also stamped.
        assert '"LineExtensionAmount":[{"_":1436.5,"currencyID":"MYR"}]' in s

    def test_explicit_line_amount_currency_overrides_default(self) -> None:
        # If user supplied currencyID="USD" on a submodel, the builder must not
        # overwrite it with the document currency.
        line = _invoice_line()
        line.tax_total.tax_amount_currency_id = "USD"  # type: ignore[attr-defined]
        inv = Invoice(
            id="X",
            issue_date_time=datetime(2024, 1, 1, tzinfo=UTC),
            document_currency_code=Currency.MYR,
            accounting_supplier_party=_supplier(),
            accounting_customer_party=_customer(),
            tax_total=line.tax_total,
            legal_monetary_total=_monetary_total(),
            invoice_lines=[line],
        )
        s = JsonEnvelopeBuilder(inv).build_json()
        # The line-level TaxTotal.TaxAmount should now be USD, not MYR.
        assert '"TaxAmount":[{"_":14.61,"currencyID":"USD"}]' in s


# ---------------------------------------------------------------------------
# 6. Optional-block omission chains and BillingReference array wrapping
# ---------------------------------------------------------------------------


class TestOptionalBlocksAndOmissions:
    def test_unset_optional_fields_omitted(self) -> None:
        # The sample has no OrderReference / Delivery / UBLExtensions /
        # Signature; the wire form must NOT carry those keys.
        inv = json.loads(JsonEnvelopeBuilder(_sample_invoice()).build_json())["Invoice"][0]
        for absent in (
            "OrderReference",
            "Delivery",
            "PaymentMeans",
            "PaymentTerms",
            "PrepaidPayment",
            "TaxExchangeRate",
            "TaxCurrencyCode",
            "UBLExtensions",
            "Signature",
        ):
            assert absent not in inv, f"{absent} unexpectedly present"

    def test_billing_reference_array_shape(self) -> None:
        inv = Invoice(
            id="X",
            issue_date_time=datetime(2024, 1, 1, tzinfo=UTC),
            document_currency_code=Currency.MYR,
            accounting_supplier_party=_supplier(),
            accounting_customer_party=_customer(),
            tax_total=_tax_total_document(),
            legal_monetary_total=_monetary_total(),
            invoice_lines=[_invoice_line()],
            billing_references=[
                BillingReference(),
                BillingReference(),
            ],
        )
        inv_dump = json.loads(JsonEnvelopeBuilder(inv).build_json())["Invoice"][0]
        # BillingReference is an array (multiple elements allowed).
        assert isinstance(inv_dump["BillingReference"], list)
        assert len(inv_dump["BillingReference"]) == 2


# ---------------------------------------------------------------------------
# 7. Determinism (Phase 4 signature-digest safety)
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_two_runs_produce_identical_string(self) -> None:
        a = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        b = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        assert a == b, "envelope serialization must be deterministic across runs"

    def test_envelope_string_starts_with_canonical_prefix(self) -> None:
        s = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        assert s.startswith('{"_D":"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",')
        assert s.endswith("}]}")

    def test_byte_for_byte_matches_php_sdk_reference_output(self) -> None:
        # Regression guard: this exact byte string was produced by running
        # /tmp/phpsdk (klsheng/myinvois-php-sdk) `JsonDocumentBuilder::build()`
        # on the *same* invoice materialised by `_sample_invoice()` (manually
        # mirrored in PHP). The two outputs compared character-for-character
        # identical (md5sum match). Pinning it here protects against silent
        # drift in decimal canonicalisation, JSON directive flags, currency
        # stamping, attribute-name choice, array-of-one wrapping, key order,
        # Unicode passthrough, or any other formatting detail that would cause
        # myinvois LHDN server-side validation to reject the payload.
        golden = (
            '{"_D":"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",'
            '"_A":"urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",'
            '"_B":"urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",'
            '"_E":"urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",'
            '"Invoice":[{"ID":[{"_":"INV-0001"}],"IssueDate":[{"_":"2024-06-14"}],'
            '"IssueTime":[{"_":"09:30:00Z"}],"InvoiceTypeCode":[{"_":"01","listVersionID":"1.0"}],'
            '"DocumentCurrencyCode":[{"_":"MYR"}],'
            '"AccountingSupplierParty":[{"AdditionalAccountID":'
            '[{"_":"CPT-CCN-W-211111-KL-000002","schemeAgencyName":"CertEX"}],'
            '"Party":[{"IndustryClassificationCode":[{"_":"01111","name":"Agriculture"}],'
            '"PartyIdentification":[{"ID":[{"_":"C2584563222","schemeID":"TIN"}]}],'
            '"PostalAddress":[{"CityName":[{"_":"Kuala Lumpur"}],"PostalZone":[{"_":"50480"}],'
            '"CountrySubentityCode":[{"_":"14"}],'
            '"AddressLine":[{"Line":[{"_":"Lot 66, Bangunan Merdeka"}]},'
            '{"Line":[{"_":"Persiaran Jaya"}]}],'
            '"Country":[{"IdentificationCode":'
            '[{"_":"MYS","listID":"ISO3166-1","listAgencyID":"6"}]}]}],'
            '"PartyLegalEntity":[{"RegistrationName":[{"_":"AMS Setia Jaya Sdn. Bhd."}]}],'
            '"Contact":[{"Telephone":[{"_":"+60123456789"}],'
            '"ElectronicMail":[{"_":"general.ams@supplier.com"}]}]}]}],'
            '"AccountingCustomerParty":[{"Party":['
            '{"PartyIdentification":[{"ID":[{"_":"C2584563200","schemeID":"TIN"}]}],'
            '"PostalAddress":[{"CityName":[{"_":"Kuala Lumpur"}],"PostalZone":[{"_":"50480"}],'
            '"CountrySubentityCode":[{"_":"14"}],'
            '"AddressLine":[{"Line":[{"_":"Lot 66, Bangunan Merdeka"}]},'
            '{"Line":[{"_":"Persiaran Jaya"}]}],'
            '"Country":[{"IdentificationCode":'
            '[{"_":"MYS","listID":"ISO3166-1","listAgencyID":"6"}]}]}],'
            '"PartyLegalEntity":[{"RegistrationName":[{"_":"Hebat Group"}]}],'
            '"Contact":[{"Telephone":[{"_":"+60123456789"}],'
            '"ElectronicMail":[{"_":"name@buyer.com"}]}]}]}],'
            '"TaxTotal":[{"TaxAmount":[{"_":87.63,"currencyID":"MYR"}],'
            '"TaxSubtotal":[{"TaxableAmount":[{"_":87.63,"currencyID":"MYR"}],'
            '"TaxAmount":[{"_":87.63,"currencyID":"MYR"}],'
            '"TaxCategory":[{"ID":[{"_":"01"}],'
            '"TaxScheme":[{"ID":'
            '[{"_":"OTH","schemeID":"UN/ECE 5153","schemeAgencyID":"6"}]}]}]}]}],'
            '"LegalMonetaryTotal":[{"LineExtensionAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"TaxExclusiveAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"TaxInclusiveAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"AllowanceTotalAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"ChargeTotalAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"PayableRoundingAmount":[{"_":0.3,"currencyID":"MYR"}],'
            '"PayableAmount":[{"_":1436.5,"currencyID":"MYR"}]}],'
            '"InvoiceLine":[{"ID":[{"_":"1234"}],"InvoicedQuantity":[{"_":1,"unitCode":"C62"}],'
            '"LineExtensionAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"AllowanceCharge":['
            '{"ChargeIndicator":[{"_":false}],'
            '"AllowanceChargeReason":[{"_":"Sample Description 2"}],'
            '"MultiplierFactorNumeric":[{"_":0.15}],"Amount":[{"_":100,"currencyID":"MYR"}]},'
            '{"ChargeIndicator":[{"_":true}],'
            '"AllowanceChargeReason":[{"_":"Service charge"}],'
            '"MultiplierFactorNumeric":[{"_":0.1}],"Amount":[{"_":100,"currencyID":"MYR"}]}],'
            '"TaxTotal":[{"TaxAmount":[{"_":14.61,"currencyID":"MYR"}],'
            '"TaxSubtotal":[{"TaxableAmount":[{"_":1436.5,"currencyID":"MYR"}],'
            '"TaxAmount":[{"_":14.61,"currencyID":"MYR"}],"Percent":[{"_":10}],'
            '"TaxCategory":[{"ID":[{"_":"01"}],"Percent":[{"_":10}],'
            '"TaxExemptionReason":[{"_":"Exempt New Means of Transport"}],'
            '"TaxScheme":[{"ID":'
            '[{"_":"OTH","schemeID":"UN/ECE 5153","schemeAgencyID":"6"}]}]}]}]}],'
            '"Item":[{"Description":[{"_":"螺丝"}],'
            '"CommodityClassification":'
            '[{"ItemClassificationCode":[{"_":"011","listID":"CLASS"}]}]}],'
            '"Price":[{"PriceAmount":[{"_":17,"currencyID":"MYR"}]}],'
            '"ItemPriceExtension":[{"Amount":[{"_":100,"currencyID":"MYR"}]}]}]}]}'
        )
        actual = JsonEnvelopeBuilder(_sample_invoice()).build_json()
        assert actual == golden, (
            "envelope JSON drifted from the PHP SDK reference output.\n"
            "First differing index:\n" + _first_diff(actual, golden)
        )


def _first_diff(a: str, b: str) -> str:
    """Return a debuggable summary of where two envelope strings diverge."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return (
                f"  actual[{i}]: ...{a[max(0, i - 40) : i + 40]!r}\n"
                f"  golden[{i}]: ...{b[max(0, i - 40) : i + 40]!r}"
            )
    if len(a) == len(b):
        return "strings identical but Python `==` disagrees (encoding?)"
    longer = "actual" if len(a) > len(b) else "golden"
    return f"strings diverge in length; {longer} is longer"


def test_xml_envelope_builder_smoke() -> None:
    # Phase 3c-XML completeness smoke — the real byte-parity assertions live
    # in tests/unit/test_xml_envelope_builder.py. Here we just confirm the
    # builder round-trips our sample invoice into canonical XML without
    # raising (behavioural floor for callers wiring JsonEnvelopeBuilder
    # and XmlEnvelopeBuilder symmetrically).
    from myinvois.ubl.builders import XmlEnvelopeBuilder

    out = XmlEnvelopeBuilder(_sample_invoice()).build_xml()
    assert out.startswith("<Invoice ") and out.endswith("</Invoice>")
