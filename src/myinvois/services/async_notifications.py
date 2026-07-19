"""Async notifications service.

Mirrors :class:`~myinvois.services.notifications.NotificationsService`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from myinvois.services.notifications import NotificationStatus, _coerce_status, _to_zulu

if TYPE_CHECKING:
    from myinvois._async_client import AsyncMyInvoisClient

__all__ = ["AsyncNotificationsService"]


class AsyncNotificationsService:
    """Async operations on MyInvois notifications."""

    BASE_PATH = "/api/v1.0/notifications"

    def __init__(self, client: AsyncMyInvoisClient) -> None:
        self._client = client

    async def get_notifications(
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
        raw = await self._client.request("GET", f"{self.BASE_PATH}/taxpayer", params=params)
        return raw if isinstance(raw, dict) else {}
