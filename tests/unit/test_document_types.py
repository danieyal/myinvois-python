"""Tests for myinvois.services.document_types — list/get/version endpoints.

Endpoints (verified against the LHDN MyInvois API):
- GET  /api/v1.0/documenttypes                  -> list of document types
- GET  /api/v1.0/documenttypes/{id}              -> single document type
- GET  /api/v1.0/documenttypes/{id}/versions/{vid}  -> document type version
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url
from myinvois.services.document_types import (
    DocumentType,
    DocumentTypesService,
    DocumentTypeVersion,
)

# -------- fixtures -----------------------------------------------------------


@pytest.fixture
def client(respx_mock: Any) -> Iterator[MyInvoisClient]:
    respx_mock.post(base_identity_url(Environment.SANDBOX)).mock(
        return_value=httpx.Response(200, json={"access_token": "TOK", "expires_in": 3600})
    )
    c = MyInvoisClient("cid", "csecret", environment=Environment.SANDBOX)
    yield c
    c.close()


# -------- models -------------------------------------------------------------


def test_document_type_model_parsing() -> None:
    payload = {
        "id": 1,
        "name": "Invoice",
        "description": "Invoice description",
        "codeNumber": "01",
        "activeSince": "2024-08-01T00:00:00Z",
        "activeTo": None,
    }
    dt = DocumentType.model_validate(payload)
    assert dt.id == 1
    assert dt.name == "Invoice"
    assert dt.code_number == "01"
    assert dt.active_since == "2024-08-01T00:00:00Z"
    assert dt.active_to is None


def test_document_type_version_model_parsing() -> None:
    payload = {
        "id": 1,
        "name": "Version 1.1",
        "description": "Invoice v1.1 structure",
        "versionNumber": "1.1",
        "activeSince": "2024-08-01T00:00:00Z",
        "activeTo": None,
        "schemas": [
            {
                "schemaId": "uuid-1",
                "validFrom": "2024-08-01T00:00:00Z",
                "validTo": None,
            }
        ],
    }
    v = DocumentTypeVersion.model_validate(payload)
    assert v.id == 1
    assert v.name == "Version 1.1"
    assert v.version_number == "1.1"
    assert v.schemas[0].schema_id == "uuid-1"


# -------- list endpoint -------------------------------------------------------


def test_list_document_types(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documenttypes").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {
                        "id": 1,
                        "name": "Invoice",
                        "description": "...",
                        "codeNumber": "01",
                        "activeSince": "2024-08-01T00:00:00Z",
                    }
                ],
                "totalPages": 10,
                "pageSize": 20,
            },
        )
    )

    result = client.document_types.list()
    assert result.total_pages == 10
    assert result.page_size == 20
    assert len(result.result) == 1
    assert result.result[0].name == "Invoice"
    assert result.result[0].code_number == "01"


def test_list_document_types_accepts_pagination_params(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": [], "totalPages": 0, "pageSize": 1})

    respx_mock.get(url__regex=r".*/documenttypes.*").mock(side_effect=_capture)

    client.document_types.list(page_no=3, page_size=5)
    assert "pageNo=3" in captured["url"]
    assert "pageSize=5" in captured["url"]


# -------- get endpoint --------------------------------------------------------


def test_get_document_type(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documenttypes/2").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 2,
                "name": "Credit Note",
                "codeNumber": "02",
                "activeSince": "2024-08-01T00:00:00Z",
            },
        )
    )

    dt = client.document_types.get("2")
    assert dt.name == "Credit Note"
    assert dt.code_number == "02"


# -------- version endpoint ----------------------------------------------------


def test_get_version(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documenttypes/1/versions/9").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 9,
                "name": "Version 1.0",
                "versionNumber": "1.0",
                "schemas": [],
            },
        )
    )

    v = client.document_types.get_version("1", "9")
    assert v.name == "Version 1.0"
    assert v.version_number == "1.0"
    assert v.schemas == []


# -------- service is exposed on client ---------------------------------------


def test_document_types_property_returns_service(client: MyInvoisClient) -> None:
    assert isinstance(client.document_types, DocumentTypesService)
