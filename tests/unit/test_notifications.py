"""Tests for myinvois.services.notifications — list notifications.

Endpoint (from the API NotificationService):
- GET /api/v1.0/notifications/taxpayer  : list previously sent notifications

Filters: dateFrom, dateTo, type, language, status, pageNo, pageSize.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from myinvois.client import MyInvoisClient
from myinvois.config import Environment, base_identity_url
from myinvois.services.notifications import NotificationsService, NotificationStatus


@pytest.fixture
def client(respx_mock: Any) -> Iterator[MyInvoisClient]:
    respx_mock.post(base_identity_url(Environment.SANDBOX)).mock(
        return_value=httpx.Response(200, json={"access_token": "TOK", "expires_in": 3600})
    )
    c = MyInvoisClient("cid", "csecret", environment=Environment.SANDBOX)
    yield c
    c.close()


def test_notification_status_enum() -> None:
    assert NotificationStatus.PENDING.value == "pending"
    assert NotificationStatus.DELIVERED.value == "delivered"
    assert NotificationStatus.ERROR.value == "error"


def test_get_notifications_passes_filters(client: MyInvoisClient, respx_mock: Any) -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": [], "totalPages": 0, "pageSize": 20})

    respx_mock.get(url__regex=r".*/notifications/taxpayer.*").mock(side_effect=_capture)

    client.notifications.get_notifications(
        date_from=datetime(2024, 1, 1, tzinfo=UTC),
        date_to=datetime(2024, 1, 31, tzinfo=UTC),
        type_="DocumentValidationResult",
        language="en",
        status=NotificationStatus.DELIVERED,
        page_no=2,
        page_size=50,
    )

    s = captured["url"]
    assert "dateFrom=2024-01-01T00%3A00%3A00Z" in s
    assert "dateTo=2024-01-31T00%3A00%3A00Z" in s
    assert "type=DocumentValidationResult" in s
    assert "language=en" in s
    assert "status=delivered" in s
    assert "pageNo=2" in s
    assert "pageSize=50" in s


def test_get_notifications_returns_dict(client: MyInvoisClient, respx_mock: Any) -> None:
    respx_mock.get(url__regex=r".*/notifications/taxpayer.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": [
                    {
                        "id": 1,
                        "type": "DocumentValidationResult",
                        "language": "en",
                        "status": "delivered",
                        "message": "Document validated",
                    }
                ],
                "totalPages": 1,
                "pageSize": 20,
            },
        )
    )

    body = client.notifications.get_notifications()
    assert body["totalPages"] == 1
    assert len(body["result"]) == 1
    assert body["result"][0]["type"] == "DocumentValidationResult"


def test_notifications_property_returns_service(client: MyInvoisClient) -> None:
    assert isinstance(client.notifications, NotificationsService)
