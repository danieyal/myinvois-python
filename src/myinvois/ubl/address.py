"""Address-related UBL components: Address, AddressLine, Country."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from myinvois.codes import Country as CountryTable
from myinvois.codes import MalaysianState

from ._base import _leaf, _UblModel


class AddressLine(_UblModel):
    """A single street address line (`cbc:AddressLine`).

    PHP `validate()` is empty for this class; we enforce only that the line is
    a non-empty string (the parent Address enforces `>=1` line items).
    """

    line: str = Field(serialization_alias="Line", min_length=1)

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {"Line": _leaf(self.line)}


class Country(_UblModel):
    """`cac:Country` with an `IdentificationCode` and the default
    listID/listAgencyID attributes (`ISO3166-1` / `6`).
    """

    identification_code: str = Field(serialization_alias="IdentificationCode")
    # Default attribute set from the PHP SDK.
    list_id: str = Field(default="ISO3166-1", exclude=True, repr=False)
    list_agency_id: str = Field(default="6", exclude=True, repr=False)

    @model_validator(mode="after")
    def _must_have_code(self) -> Country:
        if not self.identification_code:
            raise ValueError("Country.identification_code is required")
        # Sanity-check against the bundled country table (lookup-only).
        if CountryTable.name_for(self.identification_code) is None:
            raise ValueError(
                f"unknown country code {self.identification_code!r}; "
                "see myinvois.codes.Country.all_rows()"
            )
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {
            "IdentificationCode": _leaf(
                self.identification_code,
                listID=self.list_id,
                listAgencyID=self.list_agency_id,
            )
        }


class Address(_UblModel):
    """`cac:Address` — the postal address shared by parties and deliveries."""

    street_name: str | None = Field(default=None, serialization_alias="StreetName")
    additional_street_name: str | None = Field(
        default=None, serialization_alias="AdditionalStreetName"
    )
    building_number: str | None = Field(default=None, serialization_alias="BuildingNumber")
    city_name: str = Field(serialization_alias="CityName")
    postal_zone: str | None = Field(default=None, serialization_alias="PostalZone")
    country_subentity_code: str = Field(serialization_alias="CountrySubentityCode")
    address_lines: list[AddressLine] = Field(serialization_alias="AddressLine")
    country: Country = Field(serialization_alias="Country")

    @field_validator("address_lines")
    @classmethod
    def _at_least_one_line(cls, v: list[AddressLine]) -> list[AddressLine]:
        if not v:
            raise ValueError("Address.address_lines must contain at least one AddressLine")
        return v

    @model_validator(mode="after")
    def _validate_required(self) -> Address:
        # PHP Address.validate(): requires city_name, country_subentity_code, country
        # (address_lines is enforced by the field validator above).
        for attr, name in (
            ("city_name", "city_name"),
            ("country_subentity_code", "country_subentity_code"),
        ):
            if not getattr(self, attr):
                raise ValueError(f"Address.{name} is required")
        if not self.country:
            raise ValueError("Address.country is required")
        # Malaysian-state sanity check against the bundled table.
        if MalaysianState.description_for(self.country_subentity_code) is None:
            raise ValueError(
                f"unknown Malaysian state code {self.country_subentity_code!r}; "
                "see myinvois.codes.MalaysianState"
            )
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.street_name is not None:
            out["StreetName"] = _leaf(self.street_name)
        if self.additional_street_name is not None:
            out["AdditionalStreetName"] = _leaf(self.additional_street_name)
        if self.building_number is not None:
            out["BuildingNumber"] = _leaf(self.building_number)
        out["CityName"] = _leaf(self.city_name)
        if self.postal_zone is not None:
            out["PostalZone"] = _leaf(self.postal_zone)
        out["CountrySubentityCode"] = _leaf(self.country_subentity_code)
        if self.address_lines:
            out["AddressLine"] = [
                al.model_dump(by_alias=True, exclude_none=True) for al in self.address_lines
            ]
        else:
            out["AddressLine"] = []
        out["Country"] = self.country.model_dump(by_alias=True, exclude_none=True)
        return out
