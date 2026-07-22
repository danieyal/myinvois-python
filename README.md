# myinvois

Unofficial Python SDK for the Malaysian **MyInvois** (LHDN) e-Invoice system.

> Status: **Beta.** The full pipeline — build → sign → submit → track — is
> implemented and covered by tests, including golden-file tests that pin the
> serialized and signed output byte-for-byte. Not yet verified end-to-end against
> a live LHDN environment — see [Scope and limitations](#scope-and-limitations).
> See [AGENTS.md](./AGENTS.md) for architecture and detailed notes.

## Features

- **Typed client** — sync `MyInvoisClient` and async `AsyncMyInvoisClient`,
  OAuth2 `client_credentials` with proactive token refresh, intermediary
  (`onbehalfof`) support, and a typed error hierarchy mapped to HTTP status.
- **All the read endpoints** — document types, document raw/details/recent/search,
  notifications, TIN validation/search/QR lookup.
- **All eight document types** — invoice, credit/debit/refund notes and their
  self-billed variants, each a named class that fixes its own type code.
- **UBL 2.1 document models** — Pydantic v2, `Decimal` money, LHDN code enums.
- **Serializers** — canonical UBL **JSON** and **XML** envelopes, both pinned
  byte-for-byte by golden-file tests.
- **XAdES signing** — `XmlSigner` / `JsonSigner`, output likewise pinned
  byte-for-byte.
- **Submit + lifecycle** — submit documents, poll submission status, cancel and
  reject.
- **Bundled code tables** — 3,637 rows of LHDN enumerated lists shipped as data.

## Install

```bash
uv add myinvois      # or, with pip: pip install myinvois
```

Requires Python **3.11+**.

## Quickstart

```python
from myinvois import MyInvoisClient, Environment

client = MyInvoisClient(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    environment=Environment.SANDBOX,
)
client.login()                      # OAuth2 client_credentials
print(client.access_token)

# Read-only examples
types = client.document_types.list()
details = client.documents.get_details(uuid="...")
recent = client.documents.get_recent_documents(page_size=50)
results = client.documents.search_documents(
    submission_date_from="2024-01-01T00:00:00Z",
    submission_date_to="2024-01-31T00:00:00Z",
)

# Validate a Tax Identification Number before issuing an invoice
ok = client.taxpayer.validate_tin(tin="C2584563222", id_type="BRN", id_value="202001234567")

# Intermediary / ERP systems submitting on behalf of a taxpayer:
client.login(on_behalf_of="C1234567890")
```

`MyInvoisClient` is a context manager, so `with MyInvoisClient(...) as client:`
closes the underlying `httpx` client for you.

### Async

`AsyncMyInvoisClient` mirrors the sync client one-for-one — same constructor,
same properties, same services. Only the I/O methods are coroutines.

```python
import asyncio
from myinvois import AsyncMyInvoisClient, Environment

async def main() -> None:
    async with AsyncMyInvoisClient(
        client_id="...", client_secret="...", environment=Environment.SANDBOX
    ) as client:
        await client.login()
        recent = await client.documents.get_recent_documents(page_size=50)
        print(recent)

asyncio.run(main())
```

### Build an invoice

UBL documents are Pydantic v2 models with snake_case attributes and exact UBL
element names as serialization aliases. All money is `Decimal`.

```python
from datetime import UTC, datetime
from decimal import Decimal

from myinvois.codes import Currency, DocumentTypeCode, MalaysianState
from myinvois.ubl import (
    AccountingParty, Address, AddressLine, CommodityClassification, Contact,
    Country, Invoice, InvoiceLine, Item, ItemPriceExtension, LegalEntity,
    LegalMonetaryTotal, Party, PartyIdentification, Price, TaxCategory,
    TaxScheme, TaxSubTotal, TaxTotal,
)

address = Address(
    city_name="Kuala Lumpur",
    postal_zone="50480",
    country_subentity_code=MalaysianState.WP_KUALA_LUMPUR,
    address_lines=[AddressLine(line="Lot 66, Bangunan Merdeka")],
    country=Country(identification_code="MYS"),
)

invoice = Invoice(
    id="INV-0001",
    issue_date_time=datetime(2024, 6, 14, 9, 30, tzinfo=UTC),
    invoice_type_code=DocumentTypeCode.INVOICE,
    document_currency_code=Currency.MYR,
    accounting_supplier_party=AccountingParty(
        additional_account_id="CPT-CCN-W-211111-KL-000002",
        party=Party(
            industry_classification_code=("01111", "Agriculture"),
            party_identifications=[PartyIdentification(id="C2584563222", scheme_id="TIN")],
            postal_address=address,
            legal_entity=LegalEntity(registration_name="AMS Setia Jaya Sdn. Bhd."),
            contact=Contact(telephone="+60123456789", electronic_mail="ams@supplier.com"),
        ),
    ),
    accounting_customer_party=AccountingParty(
        party=Party(
            party_identifications=[PartyIdentification(id="C2584563200", scheme_id="TIN")],
            postal_address=address,
            legal_entity=LegalEntity(registration_name="Hebat Group"),
            contact=Contact(telephone="+60123456789", electronic_mail="name@buyer.com"),
        ),
    ),
    tax_total=TaxTotal(
        tax_amount=Decimal("87.63"),
        tax_sub_totals=[
            TaxSubTotal(
                taxable_amount=Decimal("87.63"),
                tax_amount=Decimal("87.63"),
                tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
            )
        ],
    ),
    legal_monetary_total=LegalMonetaryTotal(
        line_extension_amount=Decimal("1436.50"),
        tax_exclusive_amount=Decimal("1436.50"),
        tax_inclusive_amount=Decimal("1524.13"),
        payable_amount=Decimal("1524.13"),
    ),
    invoice_lines=[
        InvoiceLine(
            id="1",
            invoiced_quantity=Decimal("1"),
            line_extension_amount=Decimal("1436.50"),
            item=Item(
                description="Consulting services",
                commodity_classifications=[
                    CommodityClassification(item_classification_code="011", list_id="CLASS")
                ],
            ),
            price=Price(price_amount=Decimal("1436.50")),
            item_price_extension=ItemPriceExtension(amount=Decimal("1436.50")),
            tax_total=TaxTotal(
                tax_amount=Decimal("87.63"),
                tax_sub_totals=[
                    TaxSubTotal(
                        taxable_amount=Decimal("1436.50"),
                        tax_amount=Decimal("87.63"),
                        tax_category=TaxCategory(id="01", tax_scheme=TaxScheme(id="OTH")),
                    )
                ],
            ),
        )
    ],
)
```

The models enforce LHDN's structural rules at construction time — a missing
`commodity_classifications`, `tax_total` or `item_price_extension` on a line
raises a Pydantic `ValidationError` rather than being rejected by the server.

### Document types

All eight MyInvois document types are supported. Each has a named class that
takes the same fields as `Invoice`:

| Class | Code | Purpose |
| --- | --- | --- |
| `Invoice` | `01` | The original document |
| `CreditNote` | `02` | Corrects or reduces an earlier invoice |
| `DebitNote` | `03` | Increases an earlier invoice |
| `RefundNote` | `04` | Records money actually returned |
| `SelfBilledInvoice` | `11` | Issued by the buyer on the supplier's behalf |
| `SelfBilledCreditNote` | `12` | Self-billed equivalent of `02` |
| `SelfBilledDebitNote` | `13` | Self-billed equivalent of `03` |
| `SelfBilledRefundNote` | `14` | Self-billed equivalent of `04` |

```python
from myinvois.ubl import CreditNote

note = CreditNote(id="CN-0001", ...)   # same fields as Invoice
note.invoice_type_code                 # -> DocumentTypeCode.CREDIT_NOTE
```

**Prefer these over setting `invoice_type_code` by hand.** MyInvois carries
every document type on the same `Invoice` envelope, distinguished *only* by
that code — a credit note is byte-identical to an invoice apart from two
characters. `Invoice` defaults the code to `01`, so building a credit note with
`Invoice` and forgetting the field produces a well-formed document that claims
to be an invoice, with nothing in the payload to reveal the mistake. The named
classes supply the right code for you, so omitting the field is safe, and
passing a conflicting one raises.

For self-billed documents the *buyer* issues the document. The classes do not
transpose `accounting_supplier_party` and `accounting_customer_party` for you —
populate them per LHDN's rules; the supplier remains the supplier of the goods
or services.

### Serialize

```python
from myinvois.ubl.builders import JsonEnvelopeBuilder, XmlEnvelopeBuilder

unsigned_json = JsonEnvelopeBuilder(invoice).build_json()  # str
unsigned_xml = XmlEnvelopeBuilder(invoice).build_xml()     # str, C14N-canonical
```

Both emit the canonical LHDN wire form (`_D`/`_A`/`_B`/`_E` namespace keys and
array-of-one element wrapping for JSON; C14N-1.0 inclusive, no XML declaration
and no inter-element whitespace for XML) enabling deterministic, reproducible
signature digest computation. Live validator acceptance remains unverified (see
[Scope and limitations](#scope-and-limitations)).

### Sign (XAdES)

```python
from datetime import UTC, datetime

from myinvois import CertConfig
from myinvois.ubl.signing import JsonSigner, XmlSigner

cert = CertConfig(
    private_key_path="/path/to/private_key.pem",
    certificate_path="/path/to/certificate.base64",  # raw base64-encoded DER, not PEM
)

signed_json = JsonSigner(cert).sign(unsigned_json, signing_time=datetime.now(UTC))  # str
signed_xml = XmlSigner(cert).sign(unsigned_xml, signing_time=datetime.now(UTC))     # bytes
```

Signing embeds the `ext:UBLExtensions` XAdES block and the `cac:Signature`
sibling, and flips `InvoiceTypeCode/@listVersionID` from `1.0` to `1.1`.
Use `.digests(...)` instead of `.sign(...)` if you only need the individual
cryptographic primitives (`SignerDigests`).

### Submit and track

```python
from myinvois.services.submissions import build_submission_payload

payload = build_submission_payload("INV-0001", signed_json)  # format auto-detected
response = client.submissions.submit_documents([payload])
print(response.submission_uid, response.accepted_documents, response.rejected_documents)

# Poll — LHDN validates asynchronously; 3-5s intervals are recommended.
status = client.submissions.get_submission(response.submission_uid)
print(status.overall_status)          # in progress / valid / partially valid / invalid
for doc in status.document_summary:
    print(doc.uuid, doc.status, doc.totals.total_payable_amount)

# QR code URL for a validated document
url = client.generate_document_qr_code_url(id_="INV-0001", long_id="<longId from LHDN>")
```

### Cancel / reject

```python
client.documents.cancel_document(uuid="...", reason="Wrong buyer TIN")   # issuer, 72h window
client.documents.reject_document(uuid="...", reason="Incorrect amount")  # receiver, 72h window
```

Both return a `DocumentStateChangeResponse`. LHDN returns logical rejections
(e.g. `OperationPeriodOver`, `IncorrectState`) with HTTP 200 and a populated
`.error` block — check it. Transport-level failures raise typed
`MyInvoisError` subclasses instead.

### Code tables

The library bundles the LHDN enumerated lists (3,637 rows total):

```python
from myinvois.codes import (
    MalaysianState, TaxType, PaymentMethod, DocumentTypeCode, Currency,
    ClassificationCode, Country, MSIC, UnitCode,
)

TaxType.description_for("02")                       # -> "Service Tax"
DocumentTypeCode.SELF_BILLED_INVOICE.is_self_billed # -> True
DocumentTypeCode.coerce("03")                       # -> DEBIT_NOTE
Country.name_for("MYS")                             # -> "MALAYSIA"
MSIC.row_for("01111")["description"]                # -> "Growing of maize"
```

## Scope and limitations

- **The wire format is reverse-engineered.** LHDN publishes the API and UBL
  specifications but does not ship an official SDK in any language. The
  canonical byte-level details here (JSON envelope shape, XML canonicalisation,
  XAdES digest inputs) were derived from LHDN's documentation and frozen as
  golden fixtures. Those tests prove the output is *deterministic and
  unchanged*, not that LHDN's validator accepts it.
- **Not yet verified against a live LHDN environment.** Submission against the
  preprod sandbox with a real certificate is still outstanding. Treat acceptance
  as unproven until then.
- Signing requires an LHDN-issued certificate; the SDK never reads credentials
  implicitly — you pass a `CertConfig` explicitly.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src/myinvois
```

Live tests are marked `@pytest.mark.live` and skip unless `MYINVOIS_CLIENT_ID`
is set. The project follows TDD, with golden-file tests pinning the UBL and
signature output byte-for-byte.

## Roadmap

Phases 0–6 are complete: scaffold, client + auth, read services, code tables,
UBL models, JSON + XML serializers, XAdES signing, submit + state services, and
the async mirror. See [AGENTS.md](./AGENTS.md) for the full phase-by-phase
record.

Remaining before 1.0:

- Trusted-Publishing release to PyPI. (CI is in place: ruff, mypy and the test
  suite run on Python 3.11–3.13, plus a check that the built wheel and sdist
  ship the code tables and no signing material.)
- Live sandbox verification against the LHDN preprod environment.

## Disclaimer

`myinvois` is an independent community project and is not affiliated with, or
endorsed by, the Inland Revenue Board of Malaysia (LHDN). "MyInvois" is a
trademark of its respective owner.

## License

MIT
