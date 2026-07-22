"""Tests for myinvois.services.documents state-mutation endpoints (Phase 5).

Covers the cancel/reject state-change API:
- PUT /api/v1.0/documents/state/{uuid}/state {status: cancelled, reason}
- PUT /api/v1.0/documents/state/{uuid}/state {status: rejected, reason}

Spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/03-cancel-document/ and
      https://sdk.myinvois.hasil.gov.my/einvoicingapi/04-reject-document/

The LHDN API uses lowercase ``status`` values ("cancelled", "rejected") and a
``reason`` field with a 300-char limit (documented at the cancel endpoint).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url
from myinvois.exceptions import ValidationError
from myinvois.services.documents import (
    DocumentStateChangeResponse,
    DocumentStateChangeStatus,
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


_BASE = base_api_url(Environment.SANDBOX) + "/api/v1.0/documents"


# -------- enum ---------------------------------------------------------------


def test_document_state_change_status_enum() -> None:
    assert DocumentStateChangeStatus.CANCELLED.value == "cancelled"
    assert DocumentStateChangeStatus.REJECTED.value == "rejected"
    # the LHDN API accepts lowercase only


# -------- cancel_document ----------------------------------------------------


def test_cancel_document_sends_correct_payload(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read()
        return httpx.Response(200, json={"uuid": "U1", "status": "Cancelled"})

    respx_mock.put(_BASE + "/state/U1/state").mock(side_effect=_capture)
    resp = client.documents.cancel_document("U1", "Customer cancelled")
    assert isinstance(resp, DocumentStateChangeResponse)
    assert resp.uuid == "U1"
    assert resp.status == "Cancelled"
    assert resp.error is None
    assert captured["url"] == _BASE + "/state/U1/state"
    import json

    body = json.loads(captured["body"])
    assert body == {"status": "cancelled", "reason": "Customer cancelled"}


def test_cancel_document_default_reason_empty_string(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"uuid": "U2", "status": "Cancelled"})

    respx_mock.put(_BASE + "/state/U2/state").mock(side_effect=_capture)
    client.documents.cancel_document("U2")
    body = __import__("json").loads(captured["body"])
    assert body == {"status": "cancelled", "reason": ""}


def test_cancel_document_rejects_reason_over_300_chars(client: MyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        client.documents.cancel_document("U", "x" * 301)


# -------- reject_document ----------------------------------------------------


def test_reject_document_sends_correct_payload(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"uuid": "U3", "status": "Requested for Rejection"})

    respx_mock.put(_BASE + "/state/U3/state").mock(side_effect=_capture)
    resp = client.documents.reject_document("U3", "Wrong buyer details")
    assert isinstance(resp, DocumentStateChangeResponse)
    assert resp.uuid == "U3"
    assert resp.status == "Requested for Rejection"
    body = __import__("json").loads(captured["body"])
    assert body == {"status": "rejected", "reason": "Wrong buyer details"}


def test_reject_document_rejects_reason_over_300_chars(client: MyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        client.documents.reject_document("U", "x" * 301)


# -------- set_document_state generic ---------------------------------------


def test_set_document_state_accepts_enum(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"uuid": "U4", "status": "Cancelled"})

    respx_mock.put(_BASE + "/state/U4/state").mock(side_effect=_capture)
    client.documents.set_document_state("U4", DocumentStateChangeStatus.CANCELLED, reason="ok")
    body = __import__("json").loads(captured["body"])
    assert body == {"status": "cancelled", "reason": "ok"}


def test_set_document_state_accepts_lowercase_string(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    respx_mock.put(_BASE + "/state/U5/state").mock(
        return_value=httpx.Response(200, json={"uuid": "U5", "status": "Cancelled"})
    )
    client.documents.set_document_state("U5", "cancelled", reason="ok")
    # success — no assertion needed; the request was sent with status="cancelled"


def test_set_document_state_rejects_unknown_status(client: MyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        client.documents.set_document_state("U", "approved")


def test_set_document_state_rejects_reason_over_300(client: MyInvoisClient) -> None:
    with pytest.raises(ValidationError):
        client.documents.set_document_state(
            "U", DocumentStateChangeStatus.REJECTED, reason="x" * 301
        )


# -------- error passthrough -------------------------------------------------


def test_state_change_error_response_carries_error(client: MyInvoisClient, respx_mock: Any) -> None:
    # The LHDN API can return 200 + an `error` object in the body when the
    # state change is logically rejected (e.g. time window passed).
    respx_mock.put(_BASE + "/state/U6/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "U6",
                "status": "Valid",
                "error": {"code": "OperationPeriodOver", "message": "too late"},
            },
        )
    )
    resp = client.documents.cancel_document("U6", "x")
    assert resp.uuid == "U6"
    assert resp.status == "Valid"
    assert resp.error is not None
    assert resp.error.code == "OperationPeriodOver"
    # `message` is Optional; asserting it first turns a missing message into a
    # clear failure rather than a TypeError from `in` on None.
    assert resp.error.message is not None
    assert "too late" in resp.error.message


def test_state_change_400_raises_validation_error(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.put(_BASE + "/state/U7/state").mock(
        return_value=httpx.Response(
            400,
            json={"error": {"code": "IncorrectState", "message": "bad state"}},
        )
    )
    with pytest.raises(ValidationError):
        client.documents.cancel_document("U7", "x")
