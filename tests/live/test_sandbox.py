"""Live tests against the LHDN MyInvois **preprod sandbox**.

Everything else in this suite is mocked. These are the only tests that prove
the library talks to the real thing -- that the golden fixtures, byte-parity
work and signing pipeline produce something LHDN actually accepts, rather than
something merely deterministic.

Nothing here runs by default. Each test skips unless the credentials it needs
are present, so ``uv run pytest`` stays green on a machine with no secrets, and
CI deselects the whole module with ``-m "not live"``.

Required environment
--------------------

``MYINVOIS_CLIENT_ID`` / ``MYINVOIS_CLIENT_SECRET``
    Sandbox API credentials from the MyInvois portal.
``MYINVOIS_TIN``
    The taxpayer TIN the credentials belong to. Used as the supplier TIN, and
    for the TIN-validation check.
``MYINVOIS_BRN``
    The taxpayer's registration number (BRN/NRIC/PASSPORT/ARMY), needed to
    validate the TIN.
``MYINVOIS_CERT_PATH`` / ``MYINVOIS_KEY_PATH``
    Signing certificate and private key. Only needed for the submission test.

Two-stage safety
----------------

The read-only tests create nothing and can be run freely -- they exercise auth,
document-type lookup and TIN validation.

**The submission test creates a real document in LHDN's system.** A submitted
sandbox document consumes a document number, appears in the taxpayer's records
and cannot be deleted -- only cancelled, and only inside a 72-hour window. So
it needs a second, deliberate opt-in beyond the credentials:

    MYINVOIS_LIVE_SUBMIT=1

Having credentials configured is *not* consent to submit. Anyone running
``pytest -m live`` to check connectivity would otherwise file a tax document as
a side effect.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from myinvois import CertConfig, Environment, MyInvoisClient
from myinvois.codes import Currency, MalaysianState
from myinvois.services.submissions import build_submission_payload
from myinvois.ubl import (
    AccountingParty,
    Address,
    AddressLine,
    CommodityClassification,
    Contact,
    Country,
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
from myinvois.ubl.builders import XmlEnvelopeBuilder
from myinvois.ubl.signing import XmlSigner

pytestmark = pytest.mark.live


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value else None


_CLIENT_ID = _env("MYINVOIS_CLIENT_ID")
_CLIENT_SECRET = _env("MYINVOIS_CLIENT_SECRET")
_TIN = _env("MYINVOIS_TIN")
_BRN = _env("MYINVOIS_BRN")
_CERT_PATH = _env("MYINVOIS_CERT_PATH")
_KEY_PATH = _env("MYINVOIS_KEY_PATH")

requires_credentials = pytest.mark.skipif(
    not (_CLIENT_ID and _CLIENT_SECRET),
    reason="set MYINVOIS_CLIENT_ID and MYINVOIS_CLIENT_SECRET to run live tests",
)
requires_taxpayer = pytest.mark.skipif(
    not (_TIN and _BRN), reason="set MYINVOIS_TIN and MYINVOIS_BRN"
)
requires_signing = pytest.mark.skipif(
    not (_CERT_PATH and _KEY_PATH), reason="set MYINVOIS_CERT_PATH and MYINVOIS_KEY_PATH"
)
requires_submit_optin = pytest.mark.skipif(
    _env("MYINVOIS_LIVE_SUBMIT") != "1",
    reason="submitting files a real document in LHDN; set MYINVOIS_LIVE_SUBMIT=1 to opt in",
)


@pytest.fixture(scope="module")
def client() -> Iterator[MyInvoisClient]:
    assert _CLIENT_ID and _CLIENT_SECRET  # guarded by requires_credentials
    with MyInvoisClient(
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        environment=Environment.SANDBOX,
    ) as c:
        # These tests submit documents and validate real TINs. Targeting
        # production would file live tax records. The environment is hardcoded
        # above with no override path, and this keeps it that way if someone
        # later makes it configurable.
        assert "preprod" in c.base_api_url, (
            f"live tests must run against preprod, got {c.base_api_url!r}"
        )
        yield c


# ---------------------------------------------------------------------------
# Stage 1 -- read-only. Creates nothing.
# ---------------------------------------------------------------------------


@requires_credentials
def test_login_returns_a_token(client: MyInvoisClient) -> None:
    token = client.login()
    assert token
    assert client.access_token == token


@requires_credentials
def test_document_types_are_listed(client: MyInvoisClient) -> None:
    """Proves a signed-in GET round-trips and parses into our models."""
    client.login()
    types = client.document_types.list()
    assert types, "sandbox returned no document types"


@requires_credentials
@requires_taxpayer
def test_own_tin_validates(client: MyInvoisClient) -> None:
    """The strongest read-only signal: LHDN agrees this TIN/BRN pair is real."""
    client.login()
    assert _TIN and _BRN
    assert client.taxpayer.validate_tin(tin=_TIN, id_type="BRN", id_value=_BRN) is True


# ---------------------------------------------------------------------------
# Stage 2 -- creates a real document. Double opt-in required.
# ---------------------------------------------------------------------------


def _minimal_invoice(supplier_tin: str, supplier_brn: str) -> Invoice:
    """The smallest invoice LHDN should accept, issued to ourselves.

    Self-addressed so the submission does not involve a third party's TIN.
    """
    now = datetime.now(UTC).replace(microsecond=0)
    address = Address(
        city_name="Kuala Lumpur",
        postal_zone="50480",
        country_subentity_code=MalaysianState.WP_KUALA_LUMPUR,
        address_lines=[AddressLine(line="Lot 1, Jalan Test")],
        country=Country(identification_code="MYS"),
    )
    party = Party(
        industry_classification_code=("01111", "Agriculture"),
        party_identifications=[
            PartyIdentification(id=supplier_tin, scheme_id="TIN"),
            PartyIdentification(id=supplier_brn, scheme_id="BRN"),
        ],
        postal_address=address,
        legal_entity=LegalEntity(registration_name="Live Sandbox Test"),
        contact=Contact(telephone="+60123456789", electronic_mail="test@example.com"),
    )
    amount = Decimal("1.00")
    # Second-level precision alone is not enough: a retry or a parallel run
    # inside the same second would reuse the document ID, and these documents
    # persist in the taxpayer's records. The random suffix keeps every
    # submission distinguishable after the fact.
    unique = f"{now:%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
    return Invoice(
        id=f"LIVE-{unique}",
        issue_date_time=now,
        document_currency_code=Currency.MYR,
        accounting_supplier_party=AccountingParty(
            additional_account_id="CPT-CCN-W-211111-KL-000002", party=party
        ),
        accounting_customer_party=AccountingParty(party=party),
        tax_total=TaxTotal(
            tax_amount=Decimal("0.00"),
            tax_sub_totals=[
                TaxSubTotal(
                    taxable_amount=amount,
                    tax_amount=Decimal("0.00"),
                    tax_category=TaxCategory(id="06", tax_scheme=TaxScheme(id="OTH")),
                )
            ],
        ),
        legal_monetary_total=LegalMonetaryTotal(
            line_extension_amount=amount,
            tax_exclusive_amount=amount,
            tax_inclusive_amount=amount,
            payable_amount=amount,
        ),
        invoice_lines=[
            InvoiceLine(
                id="1",
                invoiced_quantity=Decimal("1"),
                line_extension_amount=amount,
                item=Item(
                    description="Connectivity test line",
                    commodity_classifications=[
                        CommodityClassification(item_classification_code="022", list_id="CLASS")
                    ],
                ),
                price=Price(price_amount=amount),
                item_price_extension=ItemPriceExtension(amount=amount),
                tax_total=TaxTotal(
                    tax_amount=Decimal("0.00"),
                    tax_sub_totals=[
                        TaxSubTotal(
                            taxable_amount=amount,
                            tax_amount=Decimal("0.00"),
                            tax_category=TaxCategory(id="06", tax_scheme=TaxScheme(id="OTH")),
                        )
                    ],
                ),
            )
        ],
    )


@requires_credentials
@requires_taxpayer
@requires_signing
@requires_submit_optin
def test_submit_signed_invoice(client: MyInvoisClient) -> None:
    """The end-to-end claim: build -> sign -> submit -> LHDN accepts.

    A rejection here is still a useful result -- it means the wire format is
    wrong in a way no amount of golden-fixture parity could reveal. Assert on
    the response rather than merely that the call returned.
    """
    assert _TIN and _BRN and _CERT_PATH and _KEY_PATH
    client.login()

    invoice = _minimal_invoice(_TIN, _BRN)
    unsigned = XmlEnvelopeBuilder(invoice).build_xml()
    signed = XmlSigner(CertConfig(certificate_path=_CERT_PATH, private_key_path=_KEY_PATH)).sign(
        unsigned, signing_time=datetime.now(UTC)
    )

    payload = build_submission_payload(invoice.id, signed)
    response = client.submissions.submit_documents([payload])

    assert response.rejected_documents == [], (
        f"LHDN rejected the document: {response.rejected_documents}"
    )
    assert response.accepted_documents, "no accepted documents and no rejections"
    assert response.submission_uid

    status = client.submissions.get_submission(response.submission_uid)
    assert status.submission_uid == response.submission_uid
