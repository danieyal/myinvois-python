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
- [ ] Phase 3: UBL models + serializers + codes
- [ ] Phase 4: digital signature
- [ ] Phase 5: submit + state services
- [ ] Phase 6: async mirror + polish + publish
