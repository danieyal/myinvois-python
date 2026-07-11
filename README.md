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
doc = client.documents.get_details(uuid="...")

# (coming soon) build + sign + submit an invoice
```

## Roadmap

See [AGENTS.md](./AGENTS.md) for the full phased roadmap.

## Disclaimer

`myinvois` is an independent community project and is not affiliated with, or
endorsed by, the Inland Revenue Board of Malaysia (LHDN). "MyInvois" is a
trademark of its respective owner.

## License

MIT
