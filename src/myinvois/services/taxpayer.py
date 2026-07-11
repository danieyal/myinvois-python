"""Taxpayer service — TIN validation, TIN search, and QR-code lookup.

Endpoints (from PHP SDK TaxPayerService / TaxPayersService):
- GET /api/v1.0/taxpayer/validate/{tin}?idType&idValue
    Per PHP comments: an empty 200 body means the TIN is valid; an error body
    means invalid. We translate that into a boolean.
- GET /api/v1.0/taxpayer/search/tin?...   : search for a TIN by name or id
- GET /api/v1.0/taxpayers/qrcodeinfo/{qr} : taxpayer info from QR code

Supportable `IdType` values are NRIC, BRN, PASSPORT, ARMY.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from myinvois.client import MyInvoisClient

__all__ = ["IdType", "TaxpayerService", "TinSearchResult"]


class IdType(StrEnum):
    """Taxpayer identification scheme. See `IdentificationScheme` in the gateway."""

    NRIC = "NRIC"
    BRN = "BRN"
    PASSPORT = "PASSPORT"
    ARMY = "ARMY"


# LHDN's validate endpoint returns a small JSON body describing the taxpayer when the
# TIN is valid in newer API versions. We surface it as-is plus a `valid` flag.
class TinSearchResult(dict):  # type: ignore[type-arg]
    """Lightweight typed dict alias for `validate_tin` / `search_tin` payloads."""


class TaxpayerService:
    """Taxpayer TIN validation/search + QR-lookup operations.

    Exposed on :class:`~myinvois.client.MyInvoisClient` as ``client.taxpayer``.
    """

    BASE_PATH = "/api/v1.0/taxpayer"
    QR_BASE_PATH = "/api/v1.0/taxpayers"

    def __init__(self, client: MyInvoisClient) -> None:
        self._client = client

    def validate_tin(
        self,
        *,
        tin: str,
        id_type: IdType | str,
        id_value: str,
    ) -> bool:
        """Validate a Tax Identification Number before issuing an invoice.

        Returns ``True`` when the LHDN API accepts the TIN/id pair (per the
        PHP SDK: an empty 200 body means valid; an error payload means not
        valid).
        """
        params = {"idType": _coerce_id_type(id_type), "idValue": id_value}
        raw = self._client.request("GET", f"{self.BASE_PATH}/validate/{tin}", params=params)
        # Empty body / None → valid. Non-empty dict that looks like an error →
        # invalid. We do not return the payload because the contract is simply
        # yes/no.
        if raw is None or raw in ("", {}):
            return True
        if isinstance(raw, dict):
            return not ("error" in raw or raw.get("valid") is False)
        # Non-dict non-empty payloads: treat as valid.
        return True

    def search_tin(
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
        raw = self._client.request("GET", f"{self.BASE_PATH}/search/tin", params=params)
        return raw if isinstance(raw, dict) else {}

    def get_from_qrcode(self, qr_code_text: str) -> dict[str, Any]:
        """Retrieve taxpayer info from a decoded QR-code base64 string."""
        raw = self._client.request("GET", f"{self.QR_BASE_PATH}/qrcodeinfo/{qr_code_text}")
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return raw


def _coerce_id_type(value: IdType | str) -> str:
    """Normalize an IdType accepting either the enum or a string."""
    if isinstance(value, IdType):
        return value.value
    # Accept string by-name-lookup so mis-typed strings surface a nice error.
    try:
        return IdType(value).value
    except ValueError as exc:
        raise ValueError(
            f"Unsupported IdType {value!r}; expected one of " + ", ".join(it.value for it in IdType)
        ) from exc
