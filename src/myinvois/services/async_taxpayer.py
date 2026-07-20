"""Async taxpayer service — TIN validation, TIN search, QR-code lookup.

Mirrors :class:`~myinvois.services.taxpayer.TaxpayerService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from myinvois.services.taxpayer import IdType, _coerce_id_type

if TYPE_CHECKING:
    from myinvois._async_client import AsyncMyInvoisClient

__all__ = ["AsyncTaxpayerService"]


class AsyncTaxpayerService:
    """Async taxpayer TIN validation/search + QR-lookup operations."""

    BASE_PATH = "/api/v1.0/taxpayer"
    QR_BASE_PATH = "/api/v1.0/taxpayers"

    def __init__(self, client: AsyncMyInvoisClient) -> None:
        self._client = client

    async def validate_tin(
        self,
        *,
        tin: str,
        id_type: IdType | str,
        id_value: str,
    ) -> bool:
        """Validate a Tax Identification Number before issuing an invoice."""
        params = {"idType": _coerce_id_type(id_type), "idValue": id_value}
        raw = await self._client.request("GET", f"{self.BASE_PATH}/validate/{tin}", params=params)
        if raw is None or raw in ("", {}):
            return True
        if isinstance(raw, dict):
            return not ("error" in raw or raw.get("valid") is False)
        return True

    async def search_tin(
        self,
        *,
        taxpayer_name: str | None = None,
        id_type: IdType | str | None = None,
        id_value: str | None = None,
        file_type: str | None = None,
    ) -> dict[str, Any]:
        """Search for a TIN using name and/or id type+value (AND semantics)."""
        params: dict[str, str] = {}
        if id_type is not None:
            params["idType"] = _coerce_id_type(id_type)
        if id_value is not None:
            params["idValue"] = id_value
        if taxpayer_name is not None:
            params["taxpayerName"] = taxpayer_name
        if file_type is not None:
            params["fileType"] = file_type
        raw = await self._client.request("GET", f"{self.BASE_PATH}/search/tin", params=params)
        return raw if isinstance(raw, dict) else {}

    async def get_from_qrcode(self, qr_code_text: str) -> dict[str, Any]:
        """Retrieve taxpayer info from a decoded QR-code base64 string."""
        raw = await self._client.request("GET", f"{self.QR_BASE_PATH}/qrcodeinfo/{qr_code_text}")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return raw
