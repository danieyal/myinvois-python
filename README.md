# myinvois

Unofficial Python SDK for the Malaysian **MyInvois** (LHDN) e-Invoice system.

> Status: **Alpha.** Work in progress. See [AGENTS.md](./AGENTS.md) for the
> architecture and roadmap.

## Goals

- A clean, well-typed Python library to talk to the MyInvois API
  (authentication, document submission, validation, search, TIN lookup, …).
- Build UBL 2.1 documents (XML and JSON) accepted by the MyInvois validator.
- Optional **XAdES** digital signing of documents before submission.
- Sync-first public API, with an `AsyncMyInvoisClient` for async users.

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

# Read-only example
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

# (coming soon) build + sign + submit an invoice
```

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
MSIC.row_for("01111")["description"]               # -> "Growing of maize"
```

## Roadmap

See [AGENTS.md](./AGENTS.md) for the full phased roadmap.

### Done

- **Phase 0** — project scaffold (`uv`, `pyproject`, ruff, mypy strict, pytest).
- **Phase 1** — sync `MyInvoisClient`: OAuth2 (`client_credentials`) token
  manager with in-memory cache + proactive refresh; `onbehalfof` intermediary
  header; typed error hierarchy mapped to HTTP status codes; QR URL helper.
- **Phase 2** — read-only services: `document_types` (list/get/version),
  `documents` (raw/details/recent/search with the LHDN date-pair invariant
  enforced in the request model), `notifications`, `taxpayer`
  (validate_tin/search_tin/get_from_qrcode).
- **Phase 3a** — code tables (lazy JSON-backed loaders + curated StrEnums for
  states/taxes/payment_means/document_types/currency/classification/country/
  MSIC/units). 3,637 rows deduped & shipped as wheel data; PEP 561 `py.typed`.

### TODO

- **Phase 3b** — UBL 2.1 document models (Invoice-first).
- **Phase 3c** — JSON + XML serializers.
- **Phase 4** — XAdES digital signing (the hardest part).
- **Phase 5** — submit + document state (cancel/reject) services.
- **Phase 6** — async mirror (`AsyncMyInvoisClient`), docs, publish to PyPI.

## Disclaimer

`myinvois` is an independent community project and is not affiliated with, or
endorsed by, the Inland Revenue Board of Malaysia (LHDN). "MyInvois" is a
trademark of its respective owner.

## License

MIT
