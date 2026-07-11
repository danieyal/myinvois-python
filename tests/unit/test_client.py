"""Tests for myinvois.client — MyInvoisClient request plumbing.

The MyInvoisClient wires an OAuth2 token manager, a base API URL per
environment, an optional `onbehalfof` header (intermediary mode), and a
`.request()` helper that injects the bearer token and maps HTTP errors
to typed exceptions.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_api_url, base_identity_url, base_portal_url
from myinvois.exceptions import NotFoundError, ValidationError

# -------- helpers -----------------------------------------------------------


def _token(access_token: str = "TOK", expires_in: int = 3600) -> dict[str, Any]:
    return {"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"}


@pytest.fixture
def client(respx_mock: Any) -> MyInvoisClient:
    # The `/connect/token` route must always exist for any auth attempt.
    respx_mock.post(base_identity_url(Environment.SANDBOX)).mock(
        return_value=httpx.Response(200, json=_token())
    )
    c = MyInvoisClient(client_id="cid", client_secret="csecret", environment=Environment.SANDBOX)
    yield c
    c.close()


# -------- construction ------------------------------------------------------


def test_client_construct_with_environment() -> None:
    c = MyInvoisClient(client_id="cid", client_secret="csecret", environment=Environment.PRODUCTION)
    # URLs derive from the chosen environment.
    assert c.base_api_url == base_api_url(Environment.PRODUCTION)
    assert c.base_portal_url == base_portal_url(Environment.PRODUCTION)
    c.close()


def test_client_default_environment_is_sandbox() -> None:
    c = MyInvoisClient(client_id="cid", client_secret="csecret")
    assert c.base_api_url.startswith("https://preprod-api.myinvois.hasil.gov.my")
    c.close()


def test_client_does_not_login_on_construction() -> None:
    c = MyInvoisClient(client_id="cid", client_secret="csecret", environment=Environment.SANDBOX)
    assert c.access_token is None
    c.close()


# -------- login -------------------------------------------------------------


def test_login_acquires_access_token(client: MyInvoisClient) -> None:
    client.login()
    assert client.access_token == "TOK"


def test_login_accepts_onbehalf_of_tin(client: MyInvoisClient, respx_mock: Any) -> None:
    seen_headers: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json=_token("TOK-OBO"))

    respx_mock.post(base_identity_url(Environment.SANDBOX)).mock(side_effect=_capture)

    client.login(on_behalf_of="C1234567890")
    assert client.access_token == "TOK-OBO"
    assert seen_headers["onbehalfof"] == "C1234567890"


def test_set_onbehalf_of_adds_header_to_subsequent_requests(
    client: MyInvoisClient, respx_mock: Any
) -> None:
    seen: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documenttypes").mock(
        side_effect=_capture
    )

    client.login()
    client.set_on_behalf_of("IG23486228090")
    client.request("GET", "/api/v1.0/documenttypes")

    assert seen["authorization"] == "Bearer TOK"
    assert seen["onbehalfof"] == "IG23486228090"


# -------- request() ----------------------------------------------------------


def test_request_adds_bearer_token_header(client: MyInvoisClient, respx_mock: Any) -> None:
    seen: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"result": []})

    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documenttypes").mock(
        side_effect=_capture
    )

    client.login()
    body = client.request("GET", "/api/v1.0/documenttypes")

    assert seen["authorization"] == "Bearer TOK"
    assert body == {"result": []}


def test_request_returns_parsed_json(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documents/X/details").mock(
        return_value=httpx.Response(200, json={"uuid": "X", "status": "Valid"})
    )

    client.login()
    body = client.request("GET", "/api/v1.0/documents/X/details")
    assert body == {"uuid": "X", "status": "Valid"}


def test_request_auto_logs_in_if_not_logged_yet(client: MyInvoisClient, respx_mock: Any) -> None:
    # Only the documenttypes route is mocked; the /connect/token route was set
    # up by the `client` fixture so an auto-login should be transparent.
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documenttypes").mock(
        return_value=httpx.Response(200, json=[])
    )

    # No explicit login().
    body = client.request("GET", "/api/v1.0/documenttypes")
    assert body == []
    assert client.access_token == "TOK"


def test_request_maps_400_to_validation_error(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documents").mock(
        return_value=httpx.Response(400, json={"error": {"code": "Bad", "message": "Bad"}})
    )

    client.login()
    with pytest.raises(ValidationError):
        client.request("GET", "/api/v1.0/documents")


def test_request_maps_404_to_not_found_error(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(base_api_url(Environment.SANDBOX) + "/api/v1.0/documents/nope/details").mock(
        return_value=httpx.Response(404, json={"error": "missing"})
    )

    client.login()
    with pytest.raises(NotFoundError):
        client.request("GET", "/api/v1.0/documents/nope/details")


def test_request_passes_query_params(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={})

    respx_mock.get(url__regex=r".*/documents/search.*").mock(side_effect=_capture)

    client.login()
    client.request(
        "GET",
        "/api/v1.0/documents/search",
        params={"pageNo": 2, "pageSize": 50, "status": "Valid"},
    )

    # Deltas on the captured URL.
    s = captured["url"]
    assert "pageNo=2" in s
    assert "pageSize=50" in s
    assert "status=Valid" in s


def test_request_passes_json_body_for_post(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        captured["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"accepted": True})

    respx_mock.post(base_api_url(Environment.SANDBOX) + "/api/v1.0/documentsubmissions").mock(
        side_effect=_capture
    )

    client.login()
    client.request(
        "POST",
        "/api/v1.0/documentsubmissions",
        json={"documents": [{"id": "1"}]},
    )

    assert captured["content_type"] == "application/json"
    assert b'"documents"' in captured["content"]


# -------- qr url helper -----------------------------------------------------


def test_generate_document_qr_code_url() -> None:
    c = MyInvoisClient(client_id="cid", client_secret="csecret", environment=Environment.SANDBOX)
    url = c.generate_document_qr_code_url("ABC123", "long-id-xyz")
    assert url == f"{base_portal_url(Environment.SANDBOX)}/ABC123/share/long-id-xyz"
    c.close()
