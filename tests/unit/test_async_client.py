"""Tests for the async client and async services.

Mirrors the sync tests in test_client.py, test_submissions.py,
test_documents.py, test_document_types.py, test_notifications.py, and
test_taxpayer.py — but using ``AsyncMyInvoisClient`` and ``await``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest

from myinvois._async_client import AsyncMyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url
from myinvois.exceptions import ValidationError
from myinvois.services.async_documents import AsyncDocumentsService
from myinvois.services.async_submissions import AsyncSubmissionsService
from myinvois.services.models import DocumentStateChangeResponse, GetSubmissionResponse
from myinvois.services.submissions import (
    SubmissionOverallStatus,
    SubmitDocumentsResponse,
    build_submission_payload,
)

_API = base_api_url(Environment.SANDBOX)
_IDENTITY = base_identity_url(Environment.SANDBOX)


def _token() -> dict[str, Any]:
    return {
        "access_token": "test-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@pytest.fixture
async def client(respx_mock: Any) -> AsyncIterator[AsyncMyInvoisClient]:
    respx_mock.post(_IDENTITY).mock(return_value=httpx.Response(200, json=_token()))
    c = AsyncMyInvoisClient(
        client_id="cid", client_secret="csecret", environment=Environment.SANDBOX
    )
    yield c
    await c.aclose()


# ===== construction =====


async def test_async_client_default_environment_is_sandbox() -> None:
    c = AsyncMyInvoisClient("cid", "csecret")
    assert c.base_api_url.startswith("https://preprod-api.myinvois.hasil.gov.my")
    await c.aclose()


async def test_async_client_production_urls() -> None:
    c = AsyncMyInvoisClient("cid", "csecret", environment=Environment.PRODUCTION)
    assert c.base_api_url.startswith("https://api.myinvois.hasil.gov.my")
    await c.aclose()


async def test_async_client_qr_code_url() -> None:
    c = AsyncMyInvoisClient("cid", "csecret")
    url = c.generate_document_qr_code_url("ABC", "long123")
    assert "preprod.myinvois.hasil.gov.my" in url
    assert "/ABC/share/long123" in url
    await c.aclose()


# ===== auth =====


async def test_async_login_acquires_token(client: AsyncMyInvoisClient) -> None:
    tok = await client.login()
    assert tok == "test-token"
    assert client.access_token == "test-token"


async def test_async_login_with_on_behalf_of(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_token())

    respx_mock.post(_IDENTITY).mock(side_effect=_capture)
    await client.login(on_behalf_of="C1234567890")
    assert captured["headers"].get("onbehalfof") == "C1234567890"


# ===== submissions =====


_SUBMISSION_BODY = {
    "submissionUID": "SUB1",
    "documentCount": 2,
    "dateTimeReceived": "2024-01-01T00:00:00Z",
    "acceptedDocuments": [
        {"uuid": "U1", "invoiceCodeNumber": "INV-001"},
        {"uuid": "U2", "invoiceCodeNumber": "INV-002"},
    ],
    "rejectedDocuments": [],
}


async def test_async_submit_documents(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Request("", "").content  # placeholder
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(202, json=_SUBMISSION_BODY)

    respx_mock.post(f"{_API}/api/v1.0/documentsubmissions/").mock(side_effect=_capture)
    payload = build_submission_payload("INV-001", "<Invoice/>")
    resp = await client.submissions.submit_documents([payload])

    assert isinstance(resp, SubmitDocumentsResponse)
    assert resp.submission_uid == "SUB1"
    assert len(resp.accepted_documents) == 2
    # Trailing slash on submit URL
    assert captured["url"].endswith("/documentsubmissions/")


async def test_async_submit_documents_empty_raises(client: AsyncMyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        await client.submissions.submit_documents([])


async def test_async_get_submission(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    body = {
        "submissionUid": "HJSD135P2S7D8IU",
        "documentCount": 1,
        "dateTimeReceived": "2025-02-13T14:20:10Z",
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
                "dateTimeIssued": "2025-02-13T13:15:10Z",
                "dateTimeReceived": "2025-02-13T13:15:10Z",
                "dateTimeValidated": "2025-02-13T13:15:10Z",
                "totalExcludingTax": "10.10",
                "totalDiscount": "50.00",
                "totalNetAmount": "100.70",
                "totalPayableAmount": "124.09",
                "status": "Valid",
                "documentStatusReason": None,
                "createdByUserId": "u1",
            }
        ],
    }
    respx_mock.get(f"{_API}/api/v1.0/documentsubmissions/HJSD135P2S7D8IU").mock(
        return_value=httpx.Response(200, json=body)
    )
    resp = await client.submissions.get_submission("HJSD135P2S7D8IU")
    assert isinstance(resp, GetSubmissionResponse)
    assert resp.submission_uid == "HJSD135P2S7D8IU"
    assert resp.overall_status == SubmissionOverallStatus.VALID
    assert len(resp.document_summary) == 1
    doc = resp.document_summary[0]
    assert doc.uuid == "F9D425P6DS7D8IU"
    assert doc.totals.total_payable_amount == Decimal("124.09")


async def test_async_get_submission_error_block(
    client: AsyncMyInvoisClient, respx_mock: Any
) -> None:
    """200-with-error-block must populate the error field."""
    respx_mock.get(f"{_API}/api/v1.0/documentsubmissions/REJ1").mock(
        return_value=httpx.Response(
            200,
            json={
                "error": {
                    "code": "OperationPeriodOver",
                    "message": "over.",
                    "target": "submissionUid",
                }
            },
        )
    )
    resp = await client.submissions.get_submission("REJ1")
    assert resp.error is not None
    assert resp.error.code == "OperationPeriodOver"


async def test_async_get_submission_rejects_empty() -> None:
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        GetSubmissionResponse.model_validate({})


# ===== documents (cancel/reject) =====


async def test_async_cancel_document(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.put(f"{_API}/api/v1.0/documents/state/UUID-1/state").mock(
        return_value=httpx.Response(200, json={"uuid": "UUID-1", "status": "Cancelled"})
    )
    resp = await client.documents.cancel_document("UUID-1", reason="wrong amount")
    assert isinstance(resp, DocumentStateChangeResponse)
    assert resp.uuid == "UUID-1"
    assert resp.status == "Cancelled"


async def test_async_reject_document(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.put(f"{_API}/api/v1.0/documents/state/UUID-2/state").mock(
        return_value=httpx.Response(
            200, json={"uuid": "UUID-2", "status": "Requested for Rejection"}
        )
    )
    resp = await client.documents.reject_document("UUID-2", reason="duplicate")
    assert resp.uuid == "UUID-2"
    assert resp.status == "Requested for Rejection"


async def test_async_cancel_reason_too_long(client: AsyncMyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        await client.documents.cancel_document("X", reason="x" * 301)


async def test_async_set_document_state_raw_string(
    client: AsyncMyInvoisClient, respx_mock: Any
) -> None:
    captured: dict[str, Any] = {}

    def _cap(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"uuid": "X9", "status": "Cancelled"})

    respx_mock.put(f"{_API}/api/v1.0/documents/state/X9/state").mock(side_effect=_cap)
    await client.documents.set_document_state("X9", "cancelled", reason="test")
    assert captured["body"]["status"] == "cancelled"
    assert captured["body"]["reason"] == "test"


# ===== document types =====


async def test_async_document_types_list(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(f"{_API}/api/v1.0/documenttypes").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {"id": 1, "name": "Invoice", "description": "Invoice doc type"},
                ],
                "totalPages": 1,
                "pageSize": 20,
            },
        )
    )
    types = await client.document_types.list()
    assert types.total_pages == 1
    assert len(types.result) == 1
    assert types.result[0].name == "Invoice"


async def test_async_document_types_get(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(f"{_API}/api/v1.0/documenttypes/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "name": "Invoice", "description": "Invoice"}
        )
    )
    dt = await client.document_types.get(1)
    assert dt.name == "Invoice"


# ===== notifications =====


async def test_async_get_notifications(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(f"{_API}/api/v1.0/notifications/taxpayer").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [{"id": n} for n in range(3)],
                "metadata": {"totalCount": 3},
            },
        )
    )
    result = await client.notifications.get_notifications(page_size=3)
    assert isinstance(result, dict)
    assert len(result.get("result", [])) == 3


# ===== taxpayer =====


async def test_async_validate_tin_valid(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(url__regex=r".*/taxpayer/validate/.*").mock(
        return_value=httpx.Response(200, json={})
    )
    ok = await client.taxpayer.validate_tin(
        tin="C2584563200", id_type="NRIC", id_value="1234567890"
    )
    assert ok is True


async def test_async_search_tin(client: AsyncMyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(url__regex=r".*/taxpayer/search/tin.*").mock(
        return_value=httpx.Response(200, json={"result": [{"tin": "C123"}]})
    )
    result = await client.taxpayer.search_tin(taxpayer_name="Test Co")
    assert isinstance(result, dict)
    assert len(result["result"]) == 1


# ===== service properties =====


async def test_async_service_properties_cached(client: AsyncMyInvoisClient) -> None:
    svc = client.submissions
    assert isinstance(svc, AsyncSubmissionsService)
    assert svc is client.submissions  # cached

    docs = client.documents
    assert isinstance(docs, AsyncDocumentsService)
    assert docs is client.documents


# ===== context manager =====


async def test_async_context_manager(respx_mock: Any) -> None:
    respx_mock.post(_IDENTITY).mock(return_value=httpx.Response(200, json=_token()))
    async with AsyncMyInvoisClient("cid", "csecret") as c:
        assert c.access_token is None  # not logged in yet
        tok = await c.login()
        assert tok == "test-token"
