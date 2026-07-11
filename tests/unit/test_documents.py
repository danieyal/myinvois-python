"""Tests for myinvois.services.documents — read endpoints.

Phase 2 covers read endpoints only:
- GET /api/v1.0/documents/{uuid}/raw      -> source XML/JSON + metadata
- GET /api/v1.0/documents/{uuid}/details   -> full doc + validation results
- GET /api/v1.0/documents/recent            -> recent (last 30 days), paginated
- GET /api/v1.0/documents/search            -> full search (needs date pair)

The cancel/reject PUT-state calls live in Phase 5 (`submissions`).

The `search_documents` invariant — at least one of (submission-date pair) or
(issue-date pair) must be supplied — is enforced in the request model so
callers cannot accidentally send an LHDN-rejecting 400.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url
from myinvois.exceptions import ValidationError
from myinvois.services.documents import (
    DocumentDirection,
    DocumentsService,
    DocumentStatus,
    RecentDocumentsQuery,
    SearchDocumentsQuery,
)

# -------- fixtures -----------------------------------------------------------


@pytest.fixture
def client(respx_mock: Any) -> MyInvoisClient:
    respx_mock.post(base_identity_url(Environment.SANDBOX)).mock(
        return_value=httpx.Response(200, json={"access_token": "TOK", "expires_in": 3600})
    )
    c = MyInvoisClient("cid", "csecret", environment=Environment.SANDBOX)
    yield c
    c.close()


# -------- enums ---------------------------------------------------------------


def test_enums_string_values() -> None:
    assert DocumentDirection.SENT == "Sent"
    assert DocumentDirection.RECEIVED == "Received"
    assert DocumentStatus.VALID == "Valid"
    assert DocumentStatus.CANCELLED == "Cancelled"


# -------- get_raw -------------------------------------------------------------


def test_get_document_raw(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documents/UUID1/raw").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "UUID1",
                "status": "Valid",
                "issuedDate": "2024-08-01T00:00:00Z",
                "invoiceTypeCode": "01",
                "source": "<Invoice>...</Invoice>",
                "format": "xml",
            },
        )
    )

    doc = client.documents.get_raw("UUID1")
    assert doc["uuid"] == "UUID1"
    assert doc["format"] == "xml"


# -------- get_details ---------------------------------------------------------


def test_get_document_details(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documents/UUID2/details").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "UUID2",
                "status": "Invalid",
                "dateTimeReceived": "2024-08-01T10:00:00Z",
                "validationResults": [{"error": {"code": "X", "message": "bad"}}],
            },
        )
    )

    details = client.documents.get_details("UUID2")
    assert details["uuid"] == "UUID2"
    assert details["status"] == "Invalid"


# -------- recent --------------------------------------------------------------


def test_recent_documents_passes_filters(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": [], "totalPages": 0, "pageSize": 20})

    respx_mock.get(url__regex=r".*/documents/recent.*").mock(side_effect=_capture)

    client.documents.get_recent_documents(
        page_no=2,
        page_size=50,
        invoice_direction=DocumentDirection.SENT,
        status=DocumentStatus.VALID,
        document_type="01",
    )
    s = captured["url"]
    assert "pageNo=2" in s
    assert "pageSize=50" in s
    assert "invoiceDirection=Sent" in s
    assert "status=Valid" in s
    assert "documentType=01" in s


def test_recent_documents_accepts_datetime_args_and_serializes_utc(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": []})

    respx_mock.get(url__regex=r".*/documents/recent.*").mock(side_effect=_capture)

    client.documents.get_recent_documents(
        submission_date_from=datetime(2024, 1, 1, tzinfo=UTC),
        submission_date_to=datetime(2024, 1, 31, tzinfo=UTC),
    )
    s = captured["url"]
    assert "submissionDateFrom=2024-01-01T00%3A00%3A00Z" in s
    assert "submissionDateTo=2024-01-31T00%3A00%3A00Z" in s


def test_recent_documents_query_model_skips_none() -> None:
    q = RecentDocumentsQuery(page_no=1, page_size=20)
    params = q.to_params()
    assert params == {"pageNo": "1", "pageSize": "20"}


def test_recent_documents_query_model_string_dates() -> None:
    q = RecentDocumentsQuery(submission_date_from="2024-01-01T00:00:00Z")
    params = q.to_params()
    assert params["submissionDateFrom"] == "2024-01-01T00:00:00Z"


# -------- search ---------------------------------------------------------------


def test_search_db_test_calls(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": [], "totalPages": 0, "pageSize": 100})

    respx_mock.get(url__regex=r".*/documents/search.*").mock(side_effect=_capture)

    client.documents.search_documents(
        submission_date_from=datetime(2024, 1, 1, tzinfo=UTC),
        submission_date_to=datetime(2024, 1, 31, tzinfo=UTC),
        page_no=1,
        page_size=100,
        invoice_direction=DocumentDirection.RECEIVED,
        status=DocumentStatus.SUBMITTED,
        document_type="02",
    )
    s = captured["url"]
    assert "invoiceDirection=Received" in s
    assert "status=Submitted" in s
    assert "documentType=02" in s
    assert "pageNo=1" in s
    assert "pageSize=100" in s


def test_search_requires_at_least_one_date_pair() -> None:
    with pytest.raises(ValidationError):
        SearchDocumentsQuery()  # no dates at all → invalid


def test_search_partial_date_pair_rejected() -> None:
    # submitted-from without -to → not a complete pair → not enough alone
    with pytest.raises(ValidationError):
        SearchDocumentsQuery(submission_date_from="2024-01-01T00:00:00Z")


def test_search_complete_submission_pair_ok() -> None:
    q = SearchDocumentsQuery(
        submission_date_from="2024-01-01T00:00:00Z",
        submission_date_to="2024-01-31T00:00:00Z",
    )
    params = q.to_params()
    assert "submissionDateFrom" in params
    assert "submissionDateTo" in params


def test_search_complete_issue_pair_ok() -> None:
    q = SearchDocumentsQuery(
        issue_date_from="2024-01-01T00:00:00Z",
        issue_date_to="2024-01-31T00:00:00Z",
    )
    params = q.to_params()
    assert "issueDateFrom" in params
    assert "issueDateTo" in params


def test_search_passes_uuid_and_freeform_query(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": []})

    respx_mock.get(url__regex=r".*/documents/search.*").mock(side_effect=_capture)

    client.documents.search_documents(
        submission_date_from="2024-01-01T00:00:00Z",
        submission_date_to="2024-01-31T00:00:00Z",
        uuid="ABC",
        search_query="buyerName:Foo",
    )
    s = captured["url"]
    assert "uuid=ABC" in s
    assert "searchQuery=buyerName" in s


# -------- service registry ---------------------------------------------------


def test_documents_property_returns_service(client: MyInvoisClient) -> None:
    assert isinstance(client.documents, DocumentsService)
