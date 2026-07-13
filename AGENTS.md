# AGENTS.md — persistent memory for the `myinvois` Python SDK

## Project context
- **Goal**: First Python SDK for the Malaysian MyInvois (LHDN) e-Invoice system on PyPI.
- **Package name**: `myinvois` (run/namespace). Public API is sync-first; an `AsyncMyInvoisClient` mirror is offered.
- **Python support**: `>=3.11` (modern typing, `StrEnum`, `Self`, structural pattern matching). NOT targeting <3.11.
- **Build/env**: `uv` + PEP 621 `pyproject.toml`. Tests via `uv run pytest`. Lint via `uv run ruff`; types via `uv run mypy`.
- **Approach**: TDD. Write failing test → minimal impl → refactor. Golden-file tests for UBL byte-exactness.

## Architecture (mirrors `klsheng/myinvois-php-sdk` spirit; modernized with Pydantic v2)
```
src/myinvois/
  __init__.py            # public re-exports
  client.py              # MyInvoisClient (sync) + AsyncMyInvoisClient
  _async_client.py       # async variant
  auth.py                # OAuth2 token acquisition + in-memory cache + auto-refresh
  config.py              # Environment/sandbox/prod URLs, CertConfig dataclass
  exceptions.py          # MyInvoisError hierarchy mapped to HTTP status
  services/
    documents.py         # raw/details/recent/search/cancel/reject
    submissions.py       # submit + get submission
    document_types.py    # list/get/version
    notifications.py
    taxpayer.py          # validate/search TIN + qrcodeinfo
  ubl/
    models.py            # Pydantic v2 models for the 8 document types + components
    builders/
      json_builder.py    # UBL-JSON (_D/_A/_B/_E + [{...}] repeats)
      xml_builder.py     # lxml-based, C14N-1.1 ready
    signing/
      signer.py          # XAdES enveloped signature
      canonical.py       # C14N 1.1 + LHDN namespace hacks
  codes/
    __init__.py          # enum exports
    states.py, taxes.py, payment_means.py, document_types.py,
    msic.py, classification.py, countries.py, units.py, currencies.py
  py.typed
tests/
  unit/                  # mocked with respx
  fixtures/              # golden files (sample invoices, signed JSONs)
  live/                  # @pytest.mark.live; skip without creds env vars
```

## MyInvois API facts (verified from PHP SDK + gateway; reference for ports)
- Sandbox API: `https://preprod-api.myinvois.hasil.gov.my`
- Prod API: `https://api.myinvois.hasil.gov.my`
- Auth: `POST /connect/token` — OAuth2 `client_credentials`, scope `InvoicingAPI`. Intermediaries pass header `onbehalfof: <TIN>`.
- API path prefix: `/api/v1.0/...`
- Tokens carry `expires_in`; refresh proactively.
- Portal base URL for QR codes: `https://preprod.myinvois.hasil.gov.my` / `https://myinvois.hasil.gov.my`.

## Endpoints
- Auth: `POST /connect/token`
- Document Types: `GET /api/v1.0/documenttypes` · `/{id}` · `/{id}/versions/{vid}`
- Documents: `GET /api/v1.0/documents/{id}/raw` · `/details`; `GET /recent`; `GET /search` (requires date pair)
- State: `PUT /api/v1.0/documents/state/{id}/state` body `{status,reason}` — status ∈ {`cancelled`,`rejected`}
- Submissions: `POST /api/v1.0/documentsubmissions` body `{documents:[...]}`; `GET /api/v1.0/documentsubmissions/{id}`
- Notifications: `GET /api/v1.0/notifications/taxpayer`
- Taxpayer: `GET /api/v1.0/taxpayer/validate/{tin}?idType&idValue`; `GET /api/v1.0/taxpayer/search/tin`
- Taxpayers: `GET /api/v1.0/taxpayers/qrcodeinfo/{qrText}`

## Document types (8 — UBL 2.1 based)
- `01` Invoice, `02` Credit Note, `03` Debit Note, `04` Refund Note
- `11` Self-billed Invoice, `12` Self-billed Credit Note, `13` Self-billed Debit Note, `14` Self-billed Refund Note
- Self-billed swap supplier/customer roles via a single builder function (do NOT duplicate models).
- `1.0` = unsigned, `1.1` = signed.

## Submission payload item (from `MyInvoisHelper::getInternalSubmitDocument`)
```json
{ "format": "json"|"xml", "document": "<base64>", "codeNumber": "<type>", "documentHash": "<sha256-hex-of-content>" }
```

## Digital signature (HARD — XAdES enveloped over UBL)
Steps (mirror PHP `AbstractDocumentBuilder::createSignature` exactly):
1. Build UBL without `UBLExtensions`/`Signature`; canonicalize (XML: C14N 1.1; JSON: minify + strip `\r\n`); SHA-256 → `documentHash`.
2. `RSA-PKCS1-v1_5` sign the content with SHA-256 → `SignatureValue` (base64).
3. `SignInfo`: Ref 1 digest=`documentHash`, transforms exclude `ext:UBLExtensions`+`cac:Signature` then C14N 1.1; Ref 2 `Type=...#SignedProperties` digest=SHA-256(serialized `SignedProperties`).
4. Embed `UBLExtensions` containing the signature.
- JSON variant: namespace keys `_D/_A/_B/_E`, replace SignatureProperties `Type` URI after signing.
- XML variant: `replaceCommonAttributes` to inject local namespaces (LHDN validator quirk).
- Cert digest = SHA-256(cert DER bytes); issuer/serial from X.509 parse (issuer key order: CN, E, OU, O, C — LHDN-specific).

## Key reference files (in workspace)
- `/tmp/myinvois-php-sdk/src/Ubl/Builder/AbstractDocumentBuilder.php` — signature algorithm
- `/tmp/myinvois-php-sdk/src/Ubl/Builder/{Json,Xml}DocumentBuilder.php` — serializers
- `/tmp/myinvois-php-sdk/src/Ubl/Invoice.php` — Invoice model (jsonSerialize + xmlSerialize)
- `/tmp/myinvois-php-sdk/src/Ubl/Constant/*.php` — code tables
- `/tmp/myinvois-gateway/src/schemes/common.ts` — TypeBox schemas (the field-by-field Pydantic spec)
- `/tmp/myinvois-gateway/src/schemes/documents/*.schema.ts` — per-document schemas

## Conventions
- TDD: write failing test → minimal impl → refactor. No tests for trivial data classes.
- Sync-first; async mirror lives in `_async_client.py` and shares service contracts.
- Credentials/certs: file path + bytes + a `CertConfig` dataclass. NEVER hardcode or accept from repo context.
- Tests mock HTTP with `respx`. Live tests are `@pytest.mark.live` and skip if `MYINVOIS_CLIENT_ID` is unset.
- Do NOT push or PR unless the user explicitly asks.

## Progress
- [x] Phase 0: scaffold
- [x] Phase 1: client + auth
- [x] Phase 2: read services (document_types, documents raw/details/recent/search, notifications, taxpayer validate/search TIN + qrcodeinfo)
- [x] Phase 3a: code tables (StrEnum + JSON-backed loaders for states/taxes/payment_means/document_types/currency/classification/country/MSIC/units; py.typed PEP 561 marker; uv build ships `_data/*.json`)
- [x] Phase 3b: UBL document models (Invoice-first) — see DESIGN DECISION notes above
  - DESIGN DECISION: model the **canonical UBL 2.1 envelope** (the form LHDN's public API actually accepts), NOT the gateway-style snake_case wrapper (that is the `myinvois-gateway` repo's *own* intermediate shape — LHDN rejects it; the gateway translates it server-side).
  - The envelope JSON = `{"_D": "urn:...Invoice-2", "_A": cacNS, "_B": cbcNS, "_E": extNS, "Invoice": [<nested UBL structure with every leaf as {"_": value, <attrs>...} and every repeatable element as an array-of-one-or-more>]}` (see `JsonDocumentBuilder::build()` in PHP SDK).
  - Phase 3b scope = Pydantic domain models holding structured typed data + `validate()` semantics ported from PHP `IValidator::validate()` as `@model_validator`. Phase 3c emits the envelope from these models.
  - Field naming: Python snake_case attrs with `serialization_alias = ExactUblElementName` (e.g. `id -> "ID"`, `issue_date -> "IssueDate"`, `invoice_type_code -> "InvoiceTypeCode"`). Pydantic `populate_by_name=True` + per-field alias so construction is idiomatic; serialization is byte-aligned to UBL.
  - Money: `Decimal` everywhere (finance lib; no float arithmetic). Per-amount `currencyID` attribute defaults to the document's `DocumentCurrencyCode` in the Phase 3c serializer; Phase 3b exposes optional `_currency_id` only where the SDK declared explicit Attrs fields.
  - Enums reused from `myinvois.codes`: `DocumentTypeCode` (invoice_type_code with `.coerce`), `Currency` (document_currency_code, tax_currency_code), `UnitCode` (line.invoiced_quantity unitCode), `TaxType` (tax_category.id), `Country` (country.identification_code), `MalaysianState` (address.country_subentity_code), `ClassificationCode` (item.commodity_classification item_classification_code), `MSIC` (party.industry_classification_code).
  - Phase 3b ships the Invoice (doc type 01) mainstream path only: Invoice, AccountingParty, Party, PartyIdentification, PartyTaxScheme, LegalEntity, Contact, Address, AddressLine, Country, InvoiceLine, Item, CommodityClassification, Price, ItemPriceExtension, TaxTotal, TaxSubTotal, TaxCategory, TaxScheme, AllowanceCharge, LegalMonetaryTotal, PaymentMeans, PayeeFinancialAccount, PaymentTerms, AdditionalDocumentReference, InvoiceDocumentReference, BillingReference, OrderReference, InvoicePeriod, PrepaidPayment, Delivery, Shipment, TaxExchangeRate, Attachment, SettlementPeriod, FinancialInstitutionBranch. Deferred to later: CreditNote/DebitNote/RefundNote variants + SelfBilled variants (02/03/04/11/12/13/14), and UBLExtensions/Signature (Phase 4).
  - Module layout: `src/myinvois/ubl/` → `__init__.py`, `address.py`, `party.py`, `line.py`, `tax.py`, `monetary.py`, `payment.py`, `reference.py`, `common.py`, `invoice.py` (top-level Invoice).
- [ ] Phase 3c: UBL JSON + XML serializers (envelope builder + XML via lxml)
- [ ] Phase 4: digital signature
- [ ] Phase 5: submit + state services
- [ ] Phase 6: async mirror + polish + publish

## CURRENT_STATE
Phase 0/1/2 + Phase 3a done and committed (commit `eafb615`). 103 tests passing. `ruff` + `mypy src` + `mypy tests` all clean.

## CODE_STATE
- `src/myinvois/codes/__init__.py` NOW IMPLEMENTED. Design = `_CodeTable` loader instances (caching rows + index) + curated `StrEnum(_EnumLookupMixin)` tables (`MalaysianState`, `TaxType`, `PaymentMethod`, `DocumentTypeCode`[`.is_self_billed`/`.coerce`], `Currency`) + lookup-only singletons (`ClassificationCode`, `Country`, `MSIC`, `UnitCode`). `msic_category_for()` helper. Enums get lookup classmethods from a module-level `_ENUM_LOADERS` registry (because enum class bodies forbid post-creation setattr and treat bare string assignments as members).
- `src/myinvois/codes/_data/*.json`: 8 tables = 3,637 rows. states(17) taxes(6) payment_means(8) classification(45) countries(253) currencies(180) msic(1174) units(1834).
- `scripts/extract_codes.py`: regex extractor with `php_consts()` resolution (`CurrencyCodes::CODE` => `CurrencyCodes::MYR`) and per-code dedup (`UnitCodes` `KGM` dups removed). Re-run with `uv run python scripts/extract_codes.py`.

## TESTS
103 passing (was 80). New `tests/unit/test_codes.py` has 23 tests. Test fixtures annotated `Iterator[...]`; StrEnum equality assertions use `.value` to satisfy strict mypy (comparison-overlap otherwise).

## VERSION_CONTROL_STATUS
Phase 3a commit = `eafb615` on `master` (note: branch is `master` not `main`). 33 files tracked. Working tree clean.

## CHANGES
- `pyproject.toml` now has `[tool.uv.build-backend]` `data-includes` shipping `py.typed` + `_data/*.json` (verified via fresh-venv `importlib.resources` runtime import). PEP 561 `py.typed` marker added.
- Codes symbols re-exported from top-level `myinvois/__init__.py`.

## PENDING
- [x] Phase 3b: UBL document models (Invoice-first)
- [ ] Phase 3c: UBL JSON + XML serializers
- [ ] Phase 4: digital signature
- [ ] Phase 5: submit + state services
- [ ] Phase 6: async mirror + polish + publish
