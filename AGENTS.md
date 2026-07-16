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
- [x] Phase 3c: UBL **JSON** serializer (envelope builder) — VERIFIED BYTE-FOR-BYTE PARITY with `klsheng/myinvois-php-sdk` `JsonDocumentBuilder::build()`. Concrete SW fix: `Party.industry_classification_code` now serialises the description as attribute keyed `"name"` (PHP's `setIndustryClassificationCode(code, $name=null)`), NOT `listID="MSIC"`. All `*_currency_id` model fields default to `"MYR"` (matches PHP per-class `$taxAmountAttributes = [UblAttributes::CURRENCY_ID => CurrencyCodes::MYR]`). Pinned by `TestDeterminism::test_byte_for_byte_matches_php_sdk_reference_output`. PHP SDK reference repo cloned at `/tmp/phpsdk` with `composer install --prefer-dist` (sabre/xml 4.1 required for canonical output).
- [x] Phase 3c (XML half): `XmlEnvelopeBuilder` — VERIFIED BYTE-FOR-BYTE PARITY with `klsheng/myinvois-php-sdk` `XmlDocumentBuilder::build()`. Implementation: lxml-built tree post-processed via `etree.tostring(method='c14n', exclusive=False, with_comments=False)` — inclusive C14N-1.0 (PHP's `DOMDocument::C14N()` default args), keeps all four xmlns declarations on root invoice element. Element namespace prefix mapping dispatched via auto-generated `src/myinvois/ubl/builders/_prefixes.py` (137 entries, scanned from PHP `XmlSchema::CBC|CAC|EXT . '<Name>'` occurrences + 10 manually-named dynamic-composition keys including the `LegalMonetaryTotal` amount keys and `InvoiceLine`/`InvoicedQuantity` from `$xmlTagName`/`$quantityLabel` interpolations). Number text format uses new `format_as_php_xml_token()` (2dp fixed, trailing zeros preserved — differs from `format_as_php_float_token()` which strips trailing zeros for JSON). Pinned by `TestPhpSdkByteParity::test_byte_for_byte_matches_php_sdk_reference_xml_output` against `tests/fixtures/golden_invoice_unsigned.xml` (5027 bytes, md5-diffed against PHP output at fixture-population).
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
- [x] Phase 3c (JSON half): UBL JSON envelope builder — byte-for-byte parity with PHP SDK verified (md5sum match)
- [x] Phase 3c (XML half): UBL XML envelope builder + canonicalisation prep — byte-for-byte parity with PHP SDK verified (md5sum match)
- [ ] Phase 4: digital signature
- [ ] Phase 5: submit + state services
- [ ] Phase 6: async mirror + polish + publish

## PHASE 4 — Digital signature (TDD, in flight)

### Phase 4.1 — Golden fixtures (DONE)
- `scripts/gen_signed_golden.php` regenerates `tests/fixtures/golden_invoice_signed.{xml,json}` using a forked copy of `_sample_invoice()` from `tests/unit/test_envelope_builder.py`. Run via `php scripts/gen_signed_golden.php` (needs `/tmp/phpsdk` PHP SDK and `composer install`). Produces:
  - `golden_invoice_signed.xml` — md5 `f36a659302dff7d7de0a0df725e43ad6` (5027-source `golden_invoice_unsigned.xml` + sign-block, listVersionID flipped 1.0→1.1)
  - `golden_invoice_signed.json` — md5 `18e7920ae3fdd812d03f76e37b513a21`
- Signing time is **deterministic**: `2024-01-15T10:00:00Z` via `DeterministicXmlDocumentBuilder::createSignature()` overriding the upstream `getPropsDigestHash()` caller chain to call `setSigningTime()` on `SigningCertificate` before hashing. Without this override, openssl_gettimeofday-based signing time would make every run different.
- Test cert + keypair at `tests/fixtures/cert/dummy_signing_{cert,key}.pem` (4096-bit RSA, SHA256WithRSA), serial `0x10D75D74EB922AEE2774FACA060AC339BE6AC425`. Issuer DN string: `emailAddress=test@example.com, CN=Test LHDN Signing, OU=MyInvoice Unit, O=Test Org, C=MY` (matches LHDN reorder spec).

### PHASE 4 — Canonical facts discovered (the wire truth)
PHP-side audit from `/tmp/phpsdk/src/Ubl/Builder/*.php` confirmed by byte-level probe against `golden_invoice_signed.xml`:

#### PHP API quirks (corrected in gen_signed_golden.php)
- `Invoice::setTaxTotal(TaxTotal)` — singular (NOT addTaxTotal). Same on InvoiceLine.
- `Invoice` and `InvoiceLine` have NO constructor — must call setters explicitly (e.g. `setId('INV-0001')`).
- `TaxScheme::setId($id, $schemeID=null, $schemeAgencyID=null, ...)` — note arg order vs XML attribute order. Default `idAttributes = ['schemeID' => 'UN/ECE 5153', 'schemeAgencyID' => '6']`. So `setId('OTH')` alone preserves defaults; `setId('OTH', '6', 'UN/ECE 5153')` would *swap* `schemeID`←"6", `schemeAgencyID`←"UN/ECE 5153" — WRONG order. Mirroring `_sample_invoice()` requires just `setId('OTH')`.
- `AllowanceCharge::setChargeIndicator($val)` — stores raw but xmlSerialize does PHP-truthy `? 'true':'false'`. Therefore `setChargeIndicator('false')` → emits `'true'` (string is truthy). To match Python `_sample_invoice()` which uses native `bool False`, PHP must use `setChargeIndicator(false)` (PHP-false) or `setChargeIndicator(true)`. The existing `golden_invoice_unsigned.xml` has `<cbc:ChargeIndicator>false</cbc:ChargeIndicator>` for the first AC — produced by `setChargeIndicator(false)`.
- Backward-flag: in JSON, `AllowanceCharge::jsonSerialize` emits `'_': $this->chargeIndicator` — PHP `false === bool false`, encoded by `json_encode` to bareword `false`. Confirmed in `golden_invoice_signed.json` (`"ChargeIndicator": [{"_": false}]`).
- `AbstractDocumentBuilder::$document` is private — subclass must use `getDocument()` to mutate via mutators (e.g. `$this->getDocument()->setInvoiceTypeCode(...)`).
- `setSignInfo()`, `setKeyInfo()`, `setSignatureObject()`, `setSignatureValue()`, `getRawContent()` on `AbstractDocumentBuilder` are **private**. Subclassers overriding `createSignature()` must inline their logic. `getPropsDigestHash()` is protected on `XmlDocumentBuilder`, so reusing it from a subclass works.
- PHP `http_build_query($issuerArray, '', ', ')` builds `emailAddress=...,CN=...,OU=...,O=...,C=MY` with URL-encode values but `urldecode($s)` decodes the `@` and spaces back. Issuer-key reorder spec: `['CN', 'E', 'OU', 'O', 'C']` (LHDN requirement). But `openssl_x509_parse` returns `emailAddress` as `'emailAddress'` key (NOT `'E'`), so the reorder loop using `'E'` is dead — the issuer-name always follows the original natural order which happens to be `CN` (or `emailAddress` first if it sorts first — depends on openssl version). Our test cert's parse order is `CN=..., emailAddress=..., OU=..., O=..., C=MY`, but the reorder to `['CN','E','OU','O','C']` puts `CN` before `emailAddress` leaving the final order `CN=..., emailAddress=..., OU=..., O=..., C=MY` — wait actually our `golden_invoice_signed.xml` shows `emailAddress=..., CN=..., OU=..., O=..., C=MY` (no reorder applied, since `E` is missing). Net: the test cert's emitted issuer name is `emailAddress=..., CN=Test LHDN Signing, OU=MyInvoice Unit, O=Test Org, C=MY`.
- `IssuerSerial::setSerialNumber('0x' . strtoupper(dechex($data['serialNumber'])))` — note PHP `openssl_x509_parse` may return serial as already-prefixed hex; `strtoupper` enforces uppercase. Our fixture: `0x10D75D74EB922AEE2774FACA060AC339BE6AC425`.

#### Topology — wire byte-for-byte (XML, JSON)
**XML signed invoice** (single root + UBLExtensions FIRST):
- `<ext:UBLExtensions><ext:UBLExtension><ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI><ext:ExtensionContent><sig:UBLDocumentSignatures xmlns:sac=... xmlns:sbc=... xmlns:sig=...>`
- Inside: `<sac:SignatureInformation><cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID><sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID><ds:Signature xmlns:ds=... Id="signature">`
- `<ds:SignedInfo><ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"></ds:CanonicalizationMethod><ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"></ds:SignatureMethod>`
- **Reference 1 ("id-doc-signed-data")**: `<ds:Reference Id="id-doc-signed-data" URI=""><ds:Transforms><ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath></ds:Transform><ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath></ds:Transform><ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></ds:Transform></ds:Transforms><ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" xmlns:ds=...></ds:DigestMethod><ds:DigestValue xmlns:ds=...>YtB0oeTpmTm7tBNDEaYt+wn+mvYjwzCQqXaxdqR8sjU=</ds:DigestValue></ds:Reference>`
  - Reference1.DigestValue = `base64(SHA256(golden_invoice_unsigned.xml bytes))`. Verify with `python3 -c "import hashlib, base64; ..."`. Matches PHP byte-for-byte.
- **Reference 2 ("#id-xades-signed-props")**: `<ds:Reference Type="http://uri.etsi.org/01903/v1.3.2#SignedProperties" URI="#id-xades-signed-props"><ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" xmlns:ds=...></ds:DigestMethod><ds:DigestValue xmlns:ds=...>YcW987MWbZLRt0NDwjbU746lTtKStZ0grXZlak/X+xE=</ds:DigestValue></ds:Reference>` — no Transforms.
  - Reference2.DigestValue = `base64(SHA256(propsDigestString))` where `propsDigestString` = result of step (5) below.
- `<ds:SignatureValue>bst+LG...GPG==</ds:SignatureValue>` — `openssl_sign($unsignedXmlBytes, ..., OPENSSL_ALGO_SHA256)` = RSA-PKCS1v15-SHA256. Python `cryptography` equivalent: `key.sign($unsignedXmlBytes, padding.PKCS1v15(), hashes.SHA256())`. PROVEN byte-for-byte equal.
- `<ds:KeyInfo><ds:X509Data><ds:X509Certificate>...cert-as-base64-bytes-without-PEM-headers/Footers...</ds:X509Certificate></ds:X509Data></ds:KeyInfo>` — note: PHP `getRawContent()` strips just the BEGIN/END lines, *concatenates the rest* including any `\r`-normalized '\n'. Python equivalent: `re.split('-----.*?-----', cert_pem)` then `''.join(segments)` (whitespace including `\n` is preserved between segments). PROVEN byte-identical to PHP.
- `<ds:Object><xades:QualifyingProperties xmlns:xades=... Target="signature"><xades:SignedProperties Id="id-xades-signed-props" xmlns:xades=...><xades:SignedSignatureProperties><xades:SigningTime>2024-01-15T10:00:00Z</xades:SigningTime><xades:SigningCertificate><xades:Cert><xades:CertDigest><ds:DigestMethod Algorithm=... xmlns:ds=...></ds:DigestMethod><ds:DigestValue xmlns:ds=...>UlhmSPmya4BK8Vd+VPdKdOxUAiLXC4F1uc1EB+NlaRM=</ds:DigestValue></xades:CertDigest><xades:IssuerSerial><ds:X509IssuerName xmlns:ds=...>emailAddress=..., CN=..., OU=..., O=..., C=MY</ds:X509IssuerName><ds:X509SerialNumber xmlns:ds=...>0x10D75D74EB922AEE2774FACA060AC339BE6AC425</ds:X509SerialNumber></xades:IssuerSerial></xades:Cert></xades:SigningCertificate></xades:SignedSignatureProperties></xades:SignedProperties></xades:QualifyingProperties></ds:Object>`
- CertDigest `UlhmSP...aRM=` = `base64(SHA256(cert_der))`. Python equivalent: `cert.fingerprint(hashes.SHA256())` from `cryptography.x509`. PROVEN byte-identical.

**JSON signed invoice** (different shape — PHP JsonDocumentBuilder divergences):
- `{"_D": Invoice-2ns, "_A": cacNS, "_B": cbcNS, "_E": extNS, "Invoice": [{...}]}`
- `UBLExtensions > UBLExtension > [ExtensionURI, ExtensionContent > UBLDocumentSignatures > [SignatureInformation > [{ID, ReferencedSignatureID, Signature > {...}}]]]`
- JSON `Signature` block (inner): `{Id: "signature", SignedInfo: [{SignatureMethod: [{_:"", Algorithm}], Reference: [{Id, URI, DigestMethod: [{_:"", Algorithm}], DigestValue: [{_: ...}]}]}], SignatureValue: [{_: ...}], KeyInfo: [{X509Data: [{X509Certificate: [{_: cert}], X509SubjectName: [{_: issuerNameString}], X509IssuerSerial: [{X509IssuerName: [{_: ...}], X509SerialNumber: [{_: ...}]}]}]}], Object: [{QualifyingProperties: [{Target, SignedProperties: [{Id, SignedSignatureProperties: [{SigningTime: [{_: ...}], SigningCertificate: [{Cert: [{CertDigest: [{DigestMethod, DigestValue}], IssuerSerial: [{X509IssuerName, X509SerialNumber}]}]}]}]}]}]}]}]}`
- **Notable JSON-only divergences from XML**:
  - `SignedInfo` has NO `CanonicalizationMethod`.
  - `Reference` has NO `Transforms` array — only `DigestMethod` + `DigestValue` plus the top-level attrs (`Id`/`URI`/`Type`).
  - `X509Data` adds extra `X509SubjectName` (= issuerNameString) BEFORE `X509IssuerSerial`. XML omits this.
  - The `Reference`'s `Type` attribute is `"http://uri.etsi.org/01903/v1.3.2#SignedProperties"` (underscore-vs-hash correctness verified — it's the URI fragment prefix `#SignedProperties`).
  - `DigestMethod` is `{"_": "", "Algorithm": "<alog>"}` — note the leading `_` empty-value placeholder (PHP/BCT Sabre/XML convention, leaf is `_`).
  - `ChargeIndicator`, `MultiplierFactorNumeric`, `InvoicedQuantity`, etc. are native JSON types (bool, number) — NOT strings. Note `JSONEncoder.PRESERVE_KEY_ORDER` is irrelevant as PHP `jsonSerialize()` builds associative arrays in correct order.
- `Country.IdentificationCode` attribute order in JSON: `listID` THEN `listAgencyID` (XML has the opposite attribute order, but both share the same VALUE positions).

#### PHASE 4 — Crypto primitives PROVEN to match PHP byte-for-byte
1. **Document digest** = `base64(SHA256(unsigned_xml_bytes))` (no transform/canonicalization applied to the document — it is already C14N-clean from XmlEnvelopeBuilder). Matches Reference1.DigestValue.
2. **Cert digest** = `base64(SHA256(cert_der))` via `cryptography.x509.Certificate.fingerprint(SHA256())`. Matches CertDigest.
3. **Props digest** — multi-step byte transformation:
   - **Step A**: PHP writes QualifyingProperties (the SignedProperties-only subtree — QualifyingProperties drops its own wrapper via `QualifyingProperties::xmlSerialize()` only emitting SignedProperties inside) wrapped in a temporary `<xades:root xmlns:ds=... xmlns:xades=...>` root. Namespace map: `['http://uri.etsi.org/01903/v1.3.2#' => 'xades', 'http://www.w3.org/2000/09/xmldsig#' => 'ds']`. Sabre XML writer's output XML: `<?xml version="1.0"?>\n<xades:root xmlns:xades=... xmlns:ds=...>\n <xades:SignedProperties Id="id-xades-signed-props"> ...`
   - **Step B**: `DOMDocument->C14N()` — note this is C14N-1.0 inclusive (PHP default). Alphabetically reorders root xmlns decls to `xmlns:ds=... xmlns:xades=...` (ds sorts before xades). Removes whitespace,<?xml?> declaration preserved? **No** — actually C14N-1.0 by spec does NOT emit the XML declaration. The `<?xml version="1.0"?>` is stripped at step C. C14N-1.0 collapses the tree without comments.
   - **Step C**: `str_replace("\n|\t|\r", '')` — strip trailing newlines/tabs/CR. The PHP `str_replace` is byte-not-regex.
   - **Step D**: `str_replace("<?xml version=\"1.0\"?>", '')` — strip `<?xml?>` if it survived. (Doesn't hurt if absent.)
   - **Step E**: Strip the `<xades:root ...>` opening tag and the `</xades:root>` closing tag. Result: `<xades:SignedProperties Id="id-xades-signed-props"><xades:SignedSignatureProperties>...<ds:X509SerialNumber>0x...</ds:X509SerialNumber></xades:IssuerSerial></xades:Cert></xades:SigningCertificate></xades:SignedSignatureProperties></xades:SignedProperties>`
   - **Step F** (replaceCommonAttributes — 5 string injections):
     1. `<xades:SignedProperties Id="id-xades-signed-props">` → `<xades:SignedProperties Id="id-xades-signed-props" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">`
     2. `<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></ds:DigestMethod>` → `<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" xmlns:ds="http://www.w3.org/2000/09/xmldsig#"></ds:DigestMethod>`
     3. `<ds:X509SerialNumber>` → `<ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
     4. `<ds:X509IssuerName>` → `<ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
     5. `<ds:DigestValue>` → `<ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
   - **Step G**: `base64(SHA256(result))` → Reference2.DigestValue.
   - Python implementation: `lxml.etree.tostring(root, method='c14n', exclusive=False, with_comments=False)` on a freshly-built `<xades:root>` tree produces byte-identical C14N-1.0 inclusive output to `DOMDocument->C14N()`. PROVEN.
4. **SignatureValue** = RSA-PKCS1v15-SHA256 over the unsigned XML bytes. Python `cryptography.hazmat.primitives.asymmetric.padding.PKCS1v15()` + `hashes.SHA256()` produces identically-sized (`256`-byte for 4096-bit RSA) and bit-identical output to PHP `openssl_sign($data, $sig, $key, OPENSSL_ALGO_SHA256)`. PROVEN byte-for-byte.

#### PHASE 4 — Remaining Python implementation work (TODO)
1. **Pydantic XAdES Extension tree** (`src/myinvois/ubl/signing/_models.py`): `SignInfo`, `SignInfoReference`, `SignInfoTransform`, `KeyInfoX509Data`, `IssuerSerial`, `QualifyingProperties`, `SignedProperties`, `SignedSignatureProperties`, `SigningCertificate`, `Cert`, `CertDigest`, `Signature`, `SignatureInformation`, `UBLDocumentSignatures`, `UBLExtensionItem`, `UBLExtensions`. Each class covers XML `xmlSerialize` and JSON `jsonSerialize` Symfony-style (i.e., two emission paths). Use Pydantic v2 with `model_serializer` per-class, NO `BaseModel.dict()` reliance.
2. **`_cert.py`** — `cert = CertConfig(path=<path>, bytes=<bytes>)` dataclass; `load_pem_x509_certificate` + `load_pem_private_key`; helpers `cert_pem_raw_content(pem_str)`, `issuer_name_string(cert,issuer_keys=['CN','E','OU','O','C'])`, `serial_number_hex(cert)`, `cert_digest_b64(cert)`. Issuer-name string uses PHP quirk: `'\n' + ', '` separator joining `'key=value'` for query-build style, but using `urldecode(http_build_query(...))`-style leaves already-decoded values. Python: `', '.join(f'{k}={v}' for k,v in issuer_dict.items())` where order matches drop-in PHP's `_key_by_OpenSSL_value_tracker`. **Critical**: PHP preserves OpenSSL's iteration order which for our cert is `emailAddress=..., CN=..., OU=..., O=..., C=MY`. Therefore Python must preserve this exact string (no sorting) — easier: parse x509 cert's `Subject.rfc4514_string()` and `openssl_x509_parse` order. Verified string matches.
3. **`_signer_xml.py`** (`XmlSigner`): API `XmlSigner(DbLeadConfig).sign(unsigned_xml_bytes, signing_time=datetime) -> signed_xml_bytes`. Steps:
   - Parse `unsigned_xml_bytes` (already canonical from XmlEnvelopeBuilder).
   - Build the QualifyingProperties tree → Step A..F bytes for `propsDigestString` → `propsDigestRef2 = base64(sha256(propsDigest_string))`.
   - Compute `docDigestRef1 = base64(sha256(unsigned_xml_bytes))`.
   - Insert UBLExtensions with signing-time burst in SignedSignatureProperties.
   - Mutate root `<cbc:InvoiceTypeCode listVersionID="1.1">` (set listVersionID to "1.1").
   - Compute `signatureValue = base64(rsa_pkcs1v15_sha256(unsigned_xml_bytes))` — sign over the UNSIGNED bytes (before UBLExtensions insertion — already done). PROVEN.
   - Compose final XML using lxml programmatically (inserting UBLExtensions sub-tree at the head of root).
4. **`_signer_json.py`** (`JsonSigner`): equivalent but builds the JSON shape. NOTABLE differences: NO CanonicalizationMethod, NO Transforms, ADD X509SubjectName. JSON signature uses digest of the *JSON-string-bytes-of-unsigned-invoice* (not a separate canonical XML form). Verify whether JSON's DigestValue uses SHA-256 of JSON-string-bytes-of-unsigned-invoice or SHA-256 of an XML reconstruction.
5. **Byte-for-byte parity tests** — pinned to fixture files:
   - `tests/unit/test_signer_xml.py::TestXmlSignerGolden::test_signed_xml_bytes_match_fixture` — assert `XmlSigner().sign(unsigned_xml, cert, key, signing_time=datetime(...)) == open('golden_invoice_signed.xml','rb').read()`.
   - Same for Reference1/Reference2/SignatureValue/CertDigest standalone assertions (so failure points localize).
   - `tests/unit/test_signer_json.py::TestJsonSignerGolden::test_signed_json_bytes_match_fixture`.
6. **`CERTIFY_BEFORE_PUBLIC`**: ensure fixtures aren't shipped on PyPI (commit cert + private key to /tests/fixtures/cert/ for now, but exclude from wheel). Document that real users supply their own CertConfig.

### PHASE 4.2 — JSON crypto parity PROVEN byte-for-byte (Python ↔ PHP)
The JSON side wants a *completely different* set of digest/signature inputs vs XML. Now PROVEN against `golden_invoice_signed.json`:

| Primitive | Input bytes | Fixture value (matches Python) |
|---|---|---|
| Ref1 DocDigest | `base64(SHA256(unsigned_json_string.encode("utf-8")))` | `RtAd1kuIdq57qY6MwyftOts3pS83ODOm2OmCbygGBHg=` |
| Ref2 PropsDigest | `base64(SHA256(json.dumps(qp, separators=(",", ":"), ensure_ascii=False).encode("utf-8")))` — **no whitespace stripping**, no namespace replacement. `qp` = the QualifyingProperties dict ONLY (no `<xades:root>` wrapping, no C14N, no `replaceCommonAttributes` — direct JSON serialization of the QualifyingProperties structure as PHP `json_encode(...JSON_UNESCAPED_UNICODE\|JSON_UNESCAPED_SLASHES)`) | `a7a5p9SC7birTE1+vkMSEFB/ILTWp9aWR7SSfW1pTF0=` |
| CertDigest | `base64(SHA256(cert_der))` — **identical** to XML cert digest (independent of XML vs JSON layout) | `UlhmSPmya4BK8Vd+VPdKdOxUAiLXC4F1uc1EB+NlaRM=` |
| SignatureValue | `base64(RSA-PKCS1v15-SHA256(unsigned_json_string.encode("utf-8")))` — signs over the **JSON-string** bytes, not XML bytes. PROVEN identical to PHP `openssl_sign(jsonContent, $sig, $key, OPENSSL_ALGO_SHA256)` | `R//cvLKAAF73nRogLgFhStZVJPLJZTfZyFexFwiGjMNxfbRqSYpZNsu+cHCG...` |

#### PHASE 4.2 — cert PEM content + issuer-name string PROVEN byte-for-byte (Python ↔ PHP)
PHP `getRawContent(pem_str)` algorithm:
1. `str_replace("\r", "")` — strip CRs (no-op for Unix-pem).
2. `split("\n")` then `del arr[0]` (drop `-----BEGIN ...-----`) AND pop trailing empty lines (`while arr[-1] == ""`).
3. `arr.pop()` — drop `-----END ...-----`.
4. `"".join(arr)` — concatenate remaining lines **WITHOUT separator** (no `\n` between base64 chunks in output).

PROVEN: Python equivalent `def cert_pem_raw_content(pem: str) -> str` matches byte-for-byte.

PHP issuer-name string algorithm (`AbstractDocumentBuilder::createSignature`):
- `$issuerArray = openssl_x509_parse($certContent)['issuer']` — natural openssl-iteration order.
- `$issuerKeys = ['CN', 'E', 'OU', 'O', 'C']` — desired reorder spec (note `'E'` is dead — openssl returns `'emailAddress'` not `'E'` as override key, so this step is effectively `[CN, OU, O, C]` reorder).
- For each `$key` in `$issuerKeys`: if the key exists, `unset` it and `append` to end (so it lands in the desired order at end after preserving others first).
- `urldecode(http_build_query($issuerArray, '', ', '))` — builds `k1=v1, k2=v2, ...` URL-encoded then immediately URL-decoded (so `@` and spaces and `+` stay as-is — for our cert produces `emailAddress=test@example.com, CN=Test LHDN Signing, OU=MyInvoice Unit, O=Test Org, C=MY`).

PROVEN Python equivalent: replicate the exact unset/append loop on an OrderedDict keyed with `openssl_x509_parse`-equivalent keys (`'CN'`, `'emailAddress'`, `'OU'`, `'O'`, `'C'`) — for our test cert the final string equals the fixture's exactly.

PHP serial-number string: `openssl_x509_parse` returns `$data['serialNumber']` *already* as `"0x10D75D74EB922AEE2774FACA060AC339BE6AC425"` (prefix + uppercase hex). PHP's `IssuerSerial::setSerialNumber()` stores this verbatim; no `dechex`/`strtoupper` post-processing. **Python equivalent**: `'0x' + format(cert.serial_number, 'X')` where `cert.serial_number` is the int from `cryptography.x509.load_pem_x509_certificate(...).serial_number` → PROVEN byte-for-byte equal to the fixture's serial-number string.

Note: the LHDN sample uses leading zeros in hex; PHP's `0x{UPPER_HEX}` is what they canonicalize on. Python matches because `format(n, 'X')` does NOT pad with leading zeros (and our cert serial has no leading zeros, so it's straightforward). EDGE CASE: if a real cert has serial with leading `0x0...` then `format()` may shorten it. Need to verify with a separate test eventually.

### PHASE 4.5 — Reference2 "PropsDigest" target discovered (XML+JSON)

The propsDigestHash input (XML) is **`<xades:SignedProperties Id="id-xades-signed-props">...</xades:SignedProperties>`**
— NOT the `<xades:QualifyingProperties Target="signature">` wrapper. The wrapper
only appears in the FINAL serialized output (added by
`SignatureObject::xmlSerialize` which wraps the bare QualifyingProperties model).
The `$service->write('{http://uri.etsi.org/01903/v1.3.2#}root',
$signature->getObject()->getQualifyingProperties())` call in
`XmlDocumentBuilder::getPropsDigestHash` passes the QualifyingProperties object
directly to Sabre — whose `QualifyingProperties::xmlSerialize` itself only emits
`<xades:SignedProperties>` (with NO Target attribute). Hence the hashing chunk
is `SignedProperties`, not `QualifyingProperties`.

Verified empirically by patching the PHP `XmlDocumentBuilder::getPropsDigestHash`
to capture the bytes-to-hash to a file, then computing `SHA256` over its raw bytes
externally gives **`YcW987MWbZLRt0NDwjbU746lTtKStZ0grXZlak/X+xE=`** (matches the
fixture's Reference2 `<ds:DigestValue>` byte-for-byte).

Revised XML PropsDigest algorithm (now verified end-to-end):
1. Build QualifyingProperties model with just `SignedProperties` — NO `Target`
   attribute (Target is added by SnapshotObject wrapper at FINAL serialization time).
2. Serialize Sabre-style: wrap in
   `<xades:root xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">`
   with ONLY `<xades:SignedProperties Id="id-xades-signed-props">...</xades:SignedProperties>` inside.
3. `DOMDocument::C14N()` — Python equivalent: `lxml.etree.tostring(tree, method='c14n')` byte-for-byte.
4. Strip XML prolog (`<?xml version="1.0"?>`) and the wrapper (`<xades:root ...>`, `</xades:root>`).
5. Apply `replaceCommonAttributes` — INJECT 5 xmlns declarations:
   - `<xades:SignedProperties Id="id-xades-signed-props">` → `... xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">`
   - `<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256">` → `... xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
   - `<ds:X509SerialNumber>` → `<ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
   - `<ds:X509IssuerName>` → `<ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
   - `<ds:DigestValue>` → `<ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">`
   (This step is what makes the hash match — the FINAL XML has these baked in via
   the same replaceAttributes function on the whole signed doc, hence propsDigestHash
   must replicate.)
6. Strip whitespace control chars: `\n`, `\t`, `\r`.
7. `SHA256(bytes)` → base64 → Reference2 DigestValue.

### PHASE 4.5 — Reference1 "DocDigest" + SignatureValue

- Reference1 DocDigest = `base64(SHA256(unsigned_xml_bytes))`.
  - `unsigned_xml_bytes` = `XmlDocumentBuilder::build()` output: pre-UBLExtensions
    serialized XML (C14N'd, no ext/sig blocks injected).
  - The XPath transforms `not(//ancestor-or-self::ext:UBLExtensions)` and
    `not(//ancestor-or-self::cac:Signature)` listed in `<ds:Transform>` are a
    forward PROMISE — only actuated by LHDN's validator at verify-time. They are
    NOT applied at the Python sign time (the PHP sign computation also does NOT
    apply them — it just SHA256s the raw unsigned_xml bytes).
- SignatureValue = `base64(RSA-PKCS1v15-SHA256(unsigned_xml_bytes))` (PHP's
  `openssl_sign($documentString, ..., OPENSSL_ALGO_SHA256)`).
- SigningTime format = `Y-m-d\TH:i:s\Z` → e.g. `2024-01-15T10:00:00Z` (PHP literal
  escape of T and Z, no fractional seconds).
- Final XML signing pipeline (Pseudocode):
  ```
  unsigned_xml = XmlEnvelopeBuilder(internal_model).build()  # bytes (already C14N'd)
  doc_digest_b64 = base64(SHA256(unsigned_xml))
  signature_value = base64(RSA-PKCS1v15-SHA256(unsigned_xml, privkey))
  qp = build_qualifying_properties(signing_time, cert_digest, issuer_name, serial_number)
  props_digest_b64 = base64(SHA256(replace_common_attributes(c14n(qp))))
  final_xml = unsigned_xml_with(UBLExtensions_full_block_inserted_after_open_tag)
  final_xml = final_xml.replace("listVersionID=\"1.0\"", "listVersionID=\"1.1\"")
  final_xml = external_replace_common_attributes(final_xml)  # one more pass on full doc
  return final_xml
  ```

### PHASE 4.5 — JSON signing pipeline (more substantial than XML)

JSON variant:
- SignedInfo has NO `<ds:CanonicalizationMethod>` (canonicalization is XML-only).
- Reference has NO `<ds:Transforms>` (transforms are XML-only; XPath is XML-only).
- Reference2's `Type` attribute = `http://www.w3.org/2000/09/xmldsig#SignatureProperties`
  at first serialization; then PHP post-replace flips it to
  `http://uri.etsi.org/01903/v1.3.2#SignedProperties` via str_replace.
- KeyInfo has `X509SubjectName` (in addition to `X509Certificate` + `X509IssuerSerial`).
- Both a `UBLExtensions` AND a `Signature` sibling top-level inside the Invoice
  JSON (mimicking the UBL 2.1 model which puts `cac:Signature` as a sibling to
  the `ext:UBLExtensions` block).
- propsDigestHash = `base64(SHA256(json.dumps(
    qualifying_properties_array_form,
    separators=(",",":"),
    ensure_ascii=False
  ).encode()))`.
  - `JSON_UNESCAPED_SLASHES` in PHP = no `\/` backslash-escape → mirrors Python default.
  - `JSON_UNESCAPED_UNICODE` in PHP = no `\uXXXX` escape → `ensure_ascii=False`.
  - PHP `json_encode` default has NO whitespace → `separators=(",",":")`.
- The QualifyingProperties JSON structure is:
  ```json
  {"Target":"signature","SignedProperties":[{"Id":"id-xades-signed-props",
      "SignedSignatureProperties":[{"SigningTime":[{"_":"2024-01-15T10:00:00Z"}],
          "SigningCertificate":[{"Cert":[{"CertDigest":[{"DigestMethod":[{"_":"","Algorithm":"http://www.w3.org/2001/04/xmlenc#sha256"}],"DigestValue":[{"_":"<b64>"}]}],"IssuerSerial":[{"X509IssuerName":[{"_":"<issuer>"}],"X509SerialNumber":[{"_":"<serial>"}]}]}]}]}]}]}
  ```
- `InvoiceTypeCode.listVersionID 1.0 → 1.1` flip is STILL applied (same as XML).

### PHASE 4.6+4.7 — Implementation is RED-to-GREEN jump-ready

Helper tests GREEN: the next jump-to-green is `XmlSigner.sign()` and
`JsonSigner.sign()` — the entire XAdES-extension-building logic in plain Python
string templates (no lxml-level model trees, since PHP itself uses string-surgery
for the 5 inject steps — emulating exactly with `str.replace` is cleaner than
Pydantic-tree templates).



Module `src/myinvois/ubl/signing/_cert.py` provides the byte-extracting helpers; `LoadedCert` dataclass bundles everything the signer needs from a `CertConfig`. All helpers are PROVEN byte-for-byte against the PHP fixtures:

| Helper | Verified output (test) |
|---|---|
| `cert_pem_raw_content(pem_str)` | matches `<ds:X509Certificate>...</ds:X509Certificate>` in `golden_invoice_signed.xml` |
| `issuer_name_string(cert)` | matches `<ds:X509IssuerName xmlns:ds=...>emailAddress=..., CN=..., OU=..., O=..., C=MY</ds:...>` in fixture |
| `serial_number_string(cert)` | matches `0x10D75D74EB922AEE2774FACA060AC339BE6AC425` in fixture |
| `cert_digest_b64(cert)` | matches `<ds:DigestValue xmlns:ds=...>UlhmSP...aRM=</ds:...>` in CertDigest block |
| `load_x509` / `load_private_key` / `load_cert_config` | Bundle resolved lazily on demand (no import-time I/O) |
| `sign_sha256(data, key)` | RSA-PKCS1v15-SHA256 — will be exercised by the XmlSigner / JsonSigner tests in Phase 4.7/4.8 |

RED tests status:
- `tests/unit/test_signer_cert.py` — 8 assertions GREEN (EXPECT_IMPLEMENTED=True, Phase 4.4 done).
- `tests/unit/test_signer_xml.py` — 9 assertions xfail-strict (EXPECT_IMPLEMENTED=False; XmlSigner pending Phase 4.7).
- `tests/unit/test_signer_json.py` — 11 assertions xfail-strict (EXPECT_IMPLEMENTED=False; JsonSigner pending Phase 4.8).
- Plus two un-xfail sanity assertions in `TestXmlInputSanityPreSign` that pin the *unsigned* XML fixture md5 `099e266ef6bb24d064261f155c2bc38c`.

Total: 212 passed, 20 skipped. `ruff` clean, `mypy src` clean.

Jump-to-green workflow:
- For each signer (XmlSigner, JsonSigner), flip `EXPECT_IMPLEMENTED = True` at the top of the matching `tests/unit/test_signer_xml.py` / `test_signer_json.py` file.
- Implement the signer in `src/myinvois/ubl/signing/_xml.py` / `_json.py`.
- Run `uv run pytest tests/unit/test_signer_xml.py tests/unit/test_signer_json.py -v` — any failure localises to a single primitive or the byte-for-byte golden comparison.
- Last guard against silent drift: the byte-for-byte assertion gives md5/length diagnostics in the failure message — these surface in CI.

Public API surface pinned by the tests:
```python
class XmlSigner:
    def __init__(self, cert: CertConfig): ...
    def digests(self, unsigned_xml: bytes | str, signing_time: datetime) -> SignerDigests: ...
    def sign(self, unsigned_xml: bytes | str, signing_time: datetime) -> bytes: ...

@dataclass(frozen=True, slots=True)
class SignerDigests:
    reference_1_value: str  # DocDigest b64 (XML → C14N bytes; JSON → UTF-8 str bytes)
    reference_2_value: str  # PropsDigest b64
    cert_digest: str       # CertDigest b64
    signature_value: str   # base64(RSA-PKCS1v15-SHA256(...)) (only when fully signed)

class JsonSigner:
    def __init__(self, cert: CertConfig): ...
    def digests(self, unsigned_json: bytes | str, signing_time: datetime) -> SignerDigests: ...
    def sign(self, unsigned_json: bytes | str, signing_time: datetime) -> str: ...
```


## PHASE 4 — DONE (32/32 signer tests green, byte-for-byte parity)

Both `XmlSigner.sign()` and `JsonSigner.sign()` produce byte-for-byte identical
output to the PHP-generated golden fixtures. Final test run: **232 passed in 2s**,
`ruff` clean, `mypy src` clean.

### Module layout (8 files under `src/myinvois/ubl/signing/`)

| File | Role |
|---|---|
| `__init__.py` | Re-exports `XmlSigner`, `JsonSigner`, `SignerDigests`. |
| `_digests.py` | `@dataclass(frozen=True, slots=True) SignerDigests`. |
| `_cert.py` | Cert bundle loader + primitives (issuer-reorder, serial-as-hex, cert-digest, PKCS1v15 sign). Already GREEN before Phase 4.6. |
| `_common_attrs.py` | PHP `replaceCommonAttributes` byte-for-byte (5 `xmlns:ds`/`xmlns:xades` str-replacements). |
| `_propsdigest_xml.py` | XML PropsDigest: build `<xades:SignedProperties>` block -> c14n -> strip `<xades:root>` wrapper -> apply common-attrs replacement -> SHA256-base64. |
| `_propsdigest_json.py` | JSON PropsDigest: build QualifyingProperties dict -> `json.dumps(separators=(",",":"), ensure_ascii=False)` -> SHA256-base64. |
| `_xml_block.py` | UBLExtensions block + cac:Signature sibling templates (constant-only). |
| `_xml.py` | `XmlSigner` class. |
| `_json.py` | `JsonSigner` class. |

### Pipeline summary (see class docstrings for the canonical reference)

**`XmlSigner.sign(unsigned_xml_bytes, *, signing_time) -> bytes`**
1. Resolve cert once via `load_cert_config` (cached on the signer instance).
2. `doc_digest = base64(SHA256(unsigned_xml_bytes))`.
3. `signature_value = base64(RSA-PKCS1v15-SHA256(unsigned_xml_bytes))` -- verified byte-identical to PHP `openssl_sign($data,$sig,$key,OPENSSL_ALGO_SHA256)`.
4. `cert_digest = base64(SHA256(cert_DER_bytes))`.
5. `props_digest = compute_props_digest_xml(...)` (see `_propsdigest_xml.py`).
6. Splice `<ext:UBLExtensions>...</ext:UBLExtensions>` block right after the `<Invoice xmlns=...>` opening tag.
7. Splice `<cac:Signature>...</cac:Signature>` sibling right after `</cbc:DocumentCurrencyCode>`.
8. Mutate `InvoiceTypeCode['listVersionID']` from `"1.0"` to `"1.1"`.

**`JsonSigner.sign(unsigned_json_str, *, signing_time) -> str`**
1. Steps 1-5 mirror the XML flow (digests and signing primitives identical).
2. Build the deep signature dict following PHP `Signature/KeyInfoX509Data/QualifyingProperties::jsonSerialize`.
3. Splice `"UBLExtensions"` key at the head of `Invoice` dict, `"Signature"` sibling key right after `"DocumentCurrencyCode"`.
4. Flip InvoiceTypeCode's `listVersionID` attr from `"1.0"` to `"1.1"`.
5. `json.dumps(separators=(",",":"), ensure_ascii=False)` and strip `\r\n` (PHP's `str_replace`).
6. Final `str_replace` flips `Reference2.Type` from `http://www.w3.org/2000/09/xmldsig#SignatureProperties` -> `http://uri.etsi.org/01903/v1.3.2#SignedProperties`.

### Verified byte-level assertions

| Verifiable | Value (PHP-generated golden fixture) | Match |
|---|---|---|
| XML signed bytes md5  | `f36a659302dff7d7de0a0df725e43ad6` | identical md5 |
| JSON signed bytes md5 | `18e7920ae3fdd812d03f76e37b513a21` | identical md5 |
| XML PropsDigest b64   | `YcW987MWbZLRt0NDwjbU746lTtKStZ0grXZlak/X+xE=` | identical b64 |
| JSON PropsDigest b64  | `a7a5p9SC7birTE1+vkMSEFB/ILTWp9aWR7SSfW1pTF0=` | identical b64 |
| DocDigest (XML+JSON)  | 43-char b64 (different XML vs JSON due to different source bytes) | identical b64 |
| SignatureValue (XML+JSON) | 344-char b64 prefix identical to PHP `openssl_sign` output | identical |

### Why no Pydantic-tree / lxml-based XML emission?

PHP SDK itself uses `str_replace`-based string surgery for the 5
`xmlns:ds`/`xmlns:xades` injections (see
`XmlDocumentBuilder::replaceCommonAttributes`). Earlier attempts at tree-level
lxml-side namespace manipulation produced hash mismatches during
reverse-engineering. Emulating PHP exactly via templated string-concatenation
gives byte-for-byte parity and is simpler to audit.

### Idempotency guard

Both signers raise `ValueError` if the input already contains the signed
extension (XML: `<ext:UBLExtensions>` substring; JSON: `"UBLExtensions"` key).
The PHP SDK silently re-applies on top -- we only match that behaviour if
explicitly requested.


