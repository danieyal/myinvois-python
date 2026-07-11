"""Notifications service — query for previously sent notifications.

Endpoint (from PHP SDK NotificationService):
- GET /api/v1.0/notifications/taxpayer
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from myinvois.client import MyInvoisClient

__all__ = ["NotificationStatus", "NotificationsService"]


class NotificationStatus(StrEnum):
    PENDING = "pending"
    BATCHED = "batched"
    DELIVERED = "delivered"
    ERROR = "error"


class NotificationsService:
    """Operations on MyInvois notifications.

    Exposed on :class:`~myinvois.client.MyInvoisClient` as
    ``client.notifications``.
    """

    BASE_PATH = "/api/v1.0/notifications"

    def __init__(self, client: MyInvoisClient) -> None:
        self._client = client

    def get_notifications(
        self,
        *,
        date_from: datetime | str | None = None,
        date_to: datetime | str | None = None,
        type_: str | None = None,
        language: str | None = None,
        status: NotificationStatus | str | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List previously-sent notifications, optionally filtered."""
        params: dict[str, str] = {
            "pageNo": str(page_no),
            "pageSize": str(page_size),
        }
        for key, value in (
            ("dateFrom", _to_zulu(date_from)),
            ("dateTo", _to_zulu(date_to)),
            ("type", type_),
            ("language", language),
            ("status", _coerce_status(status)),
        ):
            if value is not None:
                params[key] = value
        raw = self._client.request("GET", f"{self.BASE_PATH}/taxpayer", params=params)
        return raw if isinstance(raw, dict) else {}


def _to_zulu(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return value


def _coerce_status(value: NotificationStatus | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, NotificationStatus):
        return value.value
    try:
        return NotificationStatus(value).value
    except ValueError as exc:
        raise ValueError(
            f"Unsupported status {value!r}; expected one of "
            + ", ".join(s.value for s in NotificationStatus)
        ) from exc
