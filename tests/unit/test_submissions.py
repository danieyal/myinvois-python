"""Tests for myinvois.services.submissions — write endpoints (Phase 5).

Covers:
- POST /api/v1.0/documentsubmissions        -> submit_documents(...)
- GET  /api/v1.0/documentsubmissions/{uid}   -> get_submission(...)

Closely mirrors the response shapes documented at
https://sdk.myinvois.hasil.gov.my/einvoicingapi/02-submit-documents/ and
https://sdk.myinvois.hasil.gov.my/einvoicingapi/06-get-submission/.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url
from myinvois.exceptions import ValidationError
from myinvois.services.documents import DocumentStatus
from myinvois.services.submissions import (
    DocumentSubmissionFormat,
    DocumentSummary,
    GetSubmissionResponse,
    RejectedDocument,
    SubmissionOverallStatus,
    SubmissionsService,
    SubmitDocumentsResponse,
    build_submission_payload,
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


_BASE = base_api_url(Environment.SANDBOX) + "/api/v1.0/documentsubmissions"
_BASE_TRAILING = _BASE + "/"  # POST spec uses the trailing slash form.


# -------- helpers + enums ----------------------------------------------------


def test_format_enum_values() -> None:
    assert DocumentSubmissionFormat.XML.value == "XML"
    assert DocumentSubmissionFormat.JSON.value == "JSON"


def test_overall_status_enum_values() -> None:
    assert SubmissionOverallStatus.IN_PROGRESS.value == "in progress"
    assert SubmissionOverallStatus.VALID.value == "valid"
    assert SubmissionOverallStatus.PARTIALLY_VALID.value == "partially valid"
    assert SubmissionOverallStatus.INVALID.value == "invalid"


# -------- build_submission_payload helper -----------------------------------


def test_build_payload_auto_detects_xml_from_string() -> None:
    payload = build_submission_payload(
        code_number="INV001",
        content="<Invoice xmlns=...></Invoice>",
    )
    assert payload["format"] == "XML"
    assert payload["codeNumber"] == "INV001"
    import base64

    assert payload["document"] == base64.b64encode(b"<Invoice xmlns=...></Invoice>").decode()
    # hash is the lowercase hex sha256 of the bytes
    import hashlib

    assert payload["documentHash"] == hashlib.sha256(b"<Invoice xmlns=...></Invoice>").hexdigest()


def test_build_payload_auto_detects_json_from_string() -> None:
    json_body = '{"Invoice": {"ID": "INV001"}}'
    payload = build_submission_payload(code_number="INV001", content=json_body)
    assert payload["format"] == "JSON"
    assert payload["documentHash"] == __import__("hashlib").sha256(json_body.encode()).hexdigest()


def test_build_payload_accepts_bytes() -> None:
    payload = build_submission_payload(code_number="INV001", content=b"<x/>")
    assert payload["format"] == "XML"
    import base64

    assert payload["document"] == base64.b64encode(b"<x/>").decode()


def test_build_payload_explicit_format_overrides_auto_detect() -> None:
    # user says JSON but content looks like XML -> honour explicit
    payload = build_submission_payload(
        code_number="INV001", content="<Invoice/>", format=DocumentSubmissionFormat.JSON
    )
    assert payload["format"] == "JSON"


def test_build_payload_explicit_format_string_accepted() -> None:
    payload = build_submission_payload(code_number="INV001", content="{}", format="XML")
    assert payload["format"] == "XML"


# -------- submit_documents ---------------------------------------------------


def test_submit_documents_returns_typed_response(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        captured["headers"] = request.headers
        return httpx.Response(
            202,
            json={
                "submissionUID": "SUBMISSION1",
                "acceptedDocuments": [
                    {"uuid": "DOC1", "invoiceCodeNumber": "INV001"},
                    {"uuid": "DOC2", "invoiceCodeNumber": "INV002"},
                ],
                "rejectedDocuments": [],
            },
        )

    respx_mock.post(_BASE_TRAILING).mock(side_effect=_capture)

    response = client.submissions.submit_documents(
        documents=[
            build_submission_payload(code_number="INV001", content="<Invoice1/>"),
            build_submission_payload(code_number="INV002", content='{"A":1}'),
        ]
    )

    assert isinstance(response, SubmitDocumentsResponse)
    assert response.submission_uid == "SUBMISSION1"
    assert [d.uuid for d in response.accepted_documents] == ["DOC1", "DOC2"]
    assert [d.invoice_code_number for d in response.accepted_documents] == ["INV001", "INV002"]
    assert response.rejected_documents == []

    # Body shape: {"documents": [{format, document, documentHash, codeNumber}, ...]}
    import json

    body = json.loads(captured["body"])
    assert set(body.keys()) == {"documents"}
    assert isinstance(body["documents"], list)
    assert body["documents"][0]["codeNumber"] == "INV001"
    assert body["documents"][1]["format"] == "JSON"


def test_submit_documents_accepts_inline_documents_and_dicts(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    # Also accept raw hand-built dicts (i.e. headers don't strictly need the helper).
    respx_mock.post(_BASE_TRAILING).mock(
        return_value=httpx.Response(
            202,
            json={"submissionUID": "S1", "acceptedDocuments": [], "rejectedDocuments": []},
        )
    )
    response = client.submissions.submit_documents(
        documents=[
            {"format": "XML", "document": "PA==", "documentHash": "0" * 64, "codeNumber": "X"}
        ]
    )
    assert response.submission_uid == "S1"


def test_submit_documents_with_rejections(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.post(_BASE_TRAILING).mock(
        return_value=httpx.Response(
            202,
            json={
                "submissionUID": "S2",
                "acceptedDocuments": [],
                "rejectedDocuments": [
                    {
                        "invoiceCodeNumber": "INV001",
                        "error": {"code": "BadStructure", "message": "broken"},
                    }
                ],
            },
        )
    )
    response = client.submissions.submit_documents(
        documents=[build_submission_payload("INV001", "<bad/>")]
    )
    assert response.accepted_documents == []
    rej = response.rejected_documents
    assert len(rej) == 1
    assert isinstance(rej[0], RejectedDocument)
    assert rej[0].invoice_code_number == "INV001"
    assert rej[0].error is not None
    assert rej[0].error.code == "BadStructure"


def test_submit_documents_rejects_empty_list(client: MyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        client.submissions.submit_documents(documents=[])


def test_submit_documents_passes_content_type_header(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(
            202, json={"submissionUID": "s", "acceptedDocuments": [], "rejectedDocuments": []}
        )

    respx_mock.post(_BASE_TRAILING).mock(side_effect=_capture)
    client.submissions.submit_documents([build_submission_payload("X", "<x/>")])
    assert captured["headers"].get("content-type", "").startswith("application/json")


# -------- get_submission -----------------------------------------------------


def test_get_submission_returns_typed_response(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "submissionUid": "HJSD135P2S7D8IU",
                "documentCount": 1,
                "dateTimeReceived": "2015-02-13T14:20:10Z",
                "overallStatus": "valid",
                "documentSummary": [
                    {
                        "uuid": "F9D425P6DS7D8IU",
                        "submissionUid": "HJSD135P2S7D8IU",
                        "longId": "LIJA...",
                        "internalId": "PZ-234-A",
                        "typeName": "invoice",
                        "typeVersionName": "1.0",
                        "issuerTin": "C2584563200",
                        "issuerName": "AMS Setia Jaya",
                        "receiverId": "R1",
                        "receiverName": "Receiver Co",
                        "dateTimeIssued": "2015-02-13T13:15:10Z",
                        "dateTimeReceived": "2015-02-13T13:15:10Z",
                        "dateTimeValidated": "2015-02-13T13:15:10Z",
                        "totalExcludingTax": "10.10",
                        "totalDiscount": "50.00",
                        "totalNetAmount": "100.70",
                        "totalPayableAmount": "124.09",
                        "status": "Valid",
                        "documentStatusReason": None,
                        "createdByUserId": "u1",
                    }
                ],
            },
        )

    respx_mock.get(_BASE + "/HJSD135P2S7D8IU").mock(side_effect=_capture)

    response = client.submissions.get_submission("HJSD135P2S7D8IU")
    assert isinstance(response, GetSubmissionResponse)
    assert response.submission_uid == "HJSD135P2S7D8IU"
    assert response.document_count == 1
    assert response.overall_status == SubmissionOverallStatus.VALID
    assert response.date_time_received == "2015-02-13T14:20:10Z"
    assert len(response.document_summary) == 1
    doc = response.document_summary[0]
    assert isinstance(doc, DocumentSummary)
    assert doc.uuid == "F9D425P6DS7D8IU"
    assert doc.internal_id == "PZ-234-A"
    assert doc.status == DocumentStatus.VALID
    from decimal import Decimal

    assert doc.totals.total_payable_amount == Decimal("124.09")
    assert doc.totals.total_excluding_tax == Decimal("10.10")
    assert doc.totals.total_net_amount == Decimal("100.70")


def test_get_submission_passes_pagination_params(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200, json={"submissionUid": "x", "documentCount": 0, "documentSummary": []}
        )

    respx_mock.get(_BASE + "/X1").mock(side_effect=_capture)
    client.submissions.get_submission("X1", page_no=3, page_size=20)
    assert "pageNo=3" in captured["url"]
    assert "pageSize=20" in captured["url"]


def test_get_submission_defaults_page_no_and_size_omitted(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200, json={"submissionUid": "x", "documentCount": 0, "documentSummary": []}
        )

    respx_mock.get(_BASE + "/X2").mock(side_effect=_capture)
    client.submissions.get_submission("X2")
    # When omitted, no pageNo/pageSize query keys are emitted.
    assert "pageNo" not in captured["url"]
    assert "pageSize" not in captured["url"]


# -------- raw-bytes fallback -------------------------------------------------


def test_submissions_property_returns_service(client: MyInvoisClient) -> None:
    svc = client.submissions
    assert isinstance(svc, SubmissionsService)
    assert svc is client.submissions  # cached
