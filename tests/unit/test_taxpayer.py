"""Tests for myinvois.services.taxpayer — TIN + QR endpoints.

Endpoints (from PHP SDK TaxPayerService / TaxPayersService):
- GET /api/v1.0/taxpayer/validate/{tin}?idType&idValue    : validate TIN
- GET /api/v1.0/taxpayer/search/tin?...                   : search TIN
- GET /api/v1.0/taxpayers/qrcodeinfo/{qrText}            : taxpayer from QR
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url
from myinvois.services.taxpayer import (
    IdType,
    TaxpayerService,
)


@pytest.fixture
def client(respx_mock: Any) -> Iterator[MyInvoisClient]:
    respx_mock.post(base_identity_url(Environment.SANDBOX)).mock(
        return_value=httpx.Response(200, json={"access_token": "TOK", "expires_in": 3600})
    )
    c = MyInvoisClient("cid", "csecret", environment=Environment.SANDBOX)
    yield c
    c.close()


def test_idtype_is_string_enum() -> None:
    assert IdType.NRIC == "NRIC"
    assert IdType.ARMY == "ARMY"
    assert IdType("BRN") is IdType.BRN


# -------- validate -----------------------------------------------------------


def test_validate_tin_valid_returns_true(client: MyInvoisClient, respx_mock: Any) -> None:
    # Per PHP TaxPayerService: empty body with 200 = TIN is valid.
    respx_mock.get(
        base_api_url(Environment.SANDBOX)
        + "/api/v1.0/taxpayer/validate/C2584563222?idType=BRN&idValue=202001234567"
    ).mock(return_value=httpx.Response(200, content=b""))

    result = client.taxpayer.validate_tin(tin="C2584563222", id_type="BRN", id_value="202001234567")
    assert result is True


def test_validate_tin_invalid_returns_false(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(
        base_api_url(Environment.SANDBOX)
        + "/api/v1.0/taxpayer/validate/C2584563222?idType=BRN&idValue=202001234567"
    ).mock(return_value=httpx.Response(200, content=b'{"error": {"message": "Not valid"}}'))

    result = client.taxpayer.validate_tin(
        tin="C2584563222", id_type=IdType.BRN, id_value="202001234567"
    )
    assert result is False


# -------- search tin ---------------------------------------------------------


def test_search_tin(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "taxpayerName": "Foo Bar",
                "tin": "C2584563222",
            },
        )

    respx_mock.get(url__regex=r".*/taxpayer/search/tin.*").mock(side_effect=_capture)

    body = client.taxpayer.search_tin(
        taxpayer_name="Foo Bar", id_type="BRN", id_value="202001234567"
    )
    assert body["tin"] == "C2584563222"
    s = captured["url"]
    assert "taxpayerName=Foo+Bar" in s
    assert "idType=BRN" in s
    assert "idValue=202001234567" in s


# -------- qrcodeinfo ---------------------------------------------------------


def test_get_taxpayer_from_qrcode(client: MyInvoisClient, respx_mock: Any) -> None:
    qr = "MGI4ZDQ2MTMtYzk5NS00OTJiLWJjMWEtYTVmZjQ2NGIyYmFk"
    respx_mock.get(base_api_url(Environment.SANDBOX) + f"/api/v1.0/taxpayers/qrcodeinfo/{qr}").mock(
        return_value=httpx.Response(
            200,
            json={"tin": "C2584563222", "name": "Foo Bar", "address": "..."},
        )
    )

    body = client.taxpayer.get_from_qrcode(qr)
    assert body["tin"] == "C2584563222"
    assert body["name"] == "Foo Bar"


# -------- service registry ---------------------------------------------------


def test_taxpayer_property_returns_service(client: MyInvoisClient) -> None:
    assert isinstance(client.taxpayer, TaxpayerService)
