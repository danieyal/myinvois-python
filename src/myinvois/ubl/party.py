"""Party components: Party, PartyIdentification, PartyTaxScheme, LegalEntity,
Contact, AccountingParty, FinancialInstitutionBranch.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_serializer, model_validator

from myinvois.codes import MSIC

from ._base import _leaf, _UblModel
from .address import Address
from .tax import TaxScheme


class PartyIdentification(_UblModel):
    """`cac:PartyIdentification` — one ID with a schemeID attribute."""

    id: str = Field(serialization_alias="ID")
    scheme_id: str = Field(serialization_alias="schemeID")

    @model_validator(mode="after")
    def _requires_both(self) -> PartyIdentification:
        if not self.id:
            raise ValueError("PartyIdentification.id is required")
        if not self.scheme_id:
            raise ValueError("PartyIdentification.scheme_id is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        # PHP SDK zero-pads numeric schemeIDs to 4 digits.
        sid = self.scheme_id
        if sid.isdigit():
            sid = sid.zfill(4)
        return {"ID": _leaf(self.id, schemeID=sid)}


class PartyTaxScheme(_UblModel):
    """`cac:PartyTaxScheme` — at minimum a TaxScheme (e.g. OTH)."""

    registration_name: str | None = Field(default=None, serialization_alias="RegistrationName")
    company_id: str | None = Field(default=None, serialization_alias="CompanyID")
    tax_scheme: TaxScheme = Field(serialization_alias="TaxScheme")

    @model_validator(mode="after")
    def _must_have_tax_scheme(self) -> PartyTaxScheme:
        if self.tax_scheme is None:
            raise ValueError("PartyTaxScheme.tax_scheme is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.registration_name is not None:
            out["RegistrationName"] = _leaf(self.registration_name)
        if self.company_id is not None:
            out["CompanyID"] = _leaf(self.company_id)
        out["TaxScheme"] = self.tax_scheme.model_dump(by_alias=True, exclude_none=True)
        return out


class LegalEntity(_UblModel):
    """`cac:PartyLegalEntity` — the legal name + optional CompanyID."""

    registration_name: str = Field(serialization_alias="RegistrationName")
    company_id: str | None = Field(default=None, serialization_alias="CompanyID")
    company_id_scheme_id: str | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _must_have_registration_name(self) -> LegalEntity:
        if not self.registration_name:
            raise ValueError("LegalEntity.registration_name is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {"RegistrationName": _leaf(self.registration_name)}
        if self.company_id is not None:
            out["CompanyID"] = _leaf(self.company_id, schemeID=self.company_id_scheme_id)
        return out


class Contact(_UblModel):
    """`cac:Contact` — contact details of a party. Telephone is mandatory."""

    name: str | None = Field(default=None, serialization_alias="Name")
    telephone: str = Field(serialization_alias="Telephone")
    telefax: str | None = Field(default=None, serialization_alias="Telefax")
    electronic_mail: str | None = Field(default=None, serialization_alias="ElectronicMail")

    @model_validator(mode="after")
    def _must_have_telephone(self) -> Contact:
        if not self.telephone:
            raise ValueError("Contact.telephone is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.name is not None:
            out["Name"] = _leaf(self.name)
        out["Telephone"] = _leaf(self.telephone)
        if self.telefax is not None:
            out["Telefax"] = _leaf(self.telefax)
        if self.electronic_mail is not None:
            out["ElectronicMail"] = _leaf(self.electronic_mail)
        return out


class Party(_UblModel):
    """`cac:Party` — the supplier / customer / payee structure."""

    industry_classification_code: tuple[str, str] | None = Field(
        default=None,
        serialization_alias="IndustryClassificationCode",
        description="(code, description) tuple — code per MSIC, description per MSIC table.",
    )
    industry_classification_name_attr: str = Field(default="name", exclude=True, repr=False)
    endpoint_id: str | None = Field(default=None, exclude=True, repr=False)
    endpoint_id_scheme_id: str | None = Field(default=None, exclude=True, repr=False)
    party_identifications: list[PartyIdentification] = Field(
        default_factory=list, serialization_alias="PartyIdentification"
    )
    name: str | None = Field(default=None, exclude=True, repr=False)
    postal_address: Address = Field(serialization_alias="PostalAddress")
    physical_location: Address | None = Field(default=None, exclude=True, repr=False)
    party_tax_scheme: PartyTaxScheme | None = Field(
        default=None, serialization_alias="PartyTaxScheme"
    )
    legal_entity: LegalEntity | None = Field(default=None, serialization_alias="PartyLegalEntity")
    contact: Contact | None = Field(default=None, serialization_alias="Contact")

    @field_validator("industry_classification_code")
    @classmethod
    def _validate_industry_code(cls, v: tuple[str, str] | None) -> tuple[str, str] | None:
        if v is None:
            return v
        if not (isinstance(v, tuple | list) and len(v) == 2):
            raise ValueError("industry_classification_code must be a (code, description) tuple")
        code = v[0]
        if MSIC.description_for(code) is None:
            raise ValueError(f"unknown MSIC code {code!r}; see myinvois.codes.MSIC.all_rows()")
        return (code, v[1])

    @model_validator(mode="after")
    def _requires_address_and_legal_entity(self) -> Party:
        if self.postal_address is None:
            raise ValueError("Party.postal_address is required")
        if self.legal_entity is None:
            raise ValueError("Party.legal_entity is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.industry_classification_code is not None:
            code, desc = self.industry_classification_code
            # PHP's setIndustryClassificationCode(code, $name=null) keeps the
            # human-readable MSIC description in an attribute keyed "name"
            # (NOT listID="MSIC"). The wire form must match that attribute name.
            attr_name = self.industry_classification_name_attr
            out["IndustryClassificationCode"] = _leaf(code, **{attr_name: desc})
        if self.endpoint_id is not None and self.endpoint_id_scheme_id is not None:
            sid = self.endpoint_id_scheme_id
            if sid.isdigit():
                sid = sid.zfill(4)
            out["EndpointID"] = _leaf(self.endpoint_id, schemeID=sid)
        if self.party_identifications:
            out["PartyIdentification"] = [
                pi.model_dump(by_alias=True, exclude_none=True) for pi in self.party_identifications
            ]
        if self.name is not None:
            # PHP emits PartyName as `[{ "Name": [{"_": $name}] }]`.
            out["PartyName"] = {"Name": _leaf(self.name)}
        out["PostalAddress"] = self.postal_address.model_dump(by_alias=True, exclude_none=True)
        if self.physical_location is not None:
            out["PhysicalLocation"] = {
                "Address": self.physical_location.model_dump(by_alias=True, exclude_none=True)
            }
        if self.party_tax_scheme is not None:
            out["PartyTaxScheme"] = self.party_tax_scheme.model_dump(
                by_alias=True, exclude_none=True
            )
        if self.legal_entity is not None:
            out["PartyLegalEntity"] = self.legal_entity.model_dump(by_alias=True, exclude_none=True)
        if self.contact is not None:
            out["Contact"] = self.contact.model_dump(by_alias=True, exclude_none=True)
        return out


class AccountingParty(_UblModel):
    """`cac:AccountingSupplierParty` / `cac:AccountingCustomerParty`.

    The PHP SDK has a single class `AccountingParty` reused for both halves;
    the parent `Invoice` chooses the element name (`AccountingSupplierParty`
    or `AccountingCustomerParty`) at the wrap level.
    """

    customer_assigned_account_id: str | None = Field(
        default=None, serialization_alias="CustomerAssignedAccountID"
    )
    supplier_assigned_account_id: str | None = Field(
        default=None, serialization_alias="SupplierAssignedAccountID"
    )
    additional_account_id: str | None = Field(
        default=None, serialization_alias="AdditionalAccountID"
    )
    additional_account_id_scheme_agency_name: str = Field(
        default="CertEX", exclude=True, repr=False
    )
    party: Party = Field(serialization_alias="Party")

    @model_validator(mode="after")
    def _must_have_party(self) -> AccountingParty:
        if self.party is None:
            raise ValueError("AccountingParty.party is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.customer_assigned_account_id is not None:
            out["CustomerAssignedAccountID"] = _leaf(self.customer_assigned_account_id)
        if self.supplier_assigned_account_id is not None:
            out["SupplierAssignedAccountID"] = _leaf(self.supplier_assigned_account_id)
        if self.additional_account_id is not None:
            out["AdditionalAccountID"] = _leaf(
                self.additional_account_id,
                schemeAgencyName=self.additional_account_id_scheme_agency_name,
            )
        out["Party"] = self.party.model_dump(by_alias=True, exclude_none=True)
        return out


class FinancialInstitutionBranch(_UblModel):
    """`cac:FinancialInstitutionBranch` — a bank branch identifier."""

    id: str = Field(serialization_alias="ID")

    @model_validator(mode="after")
    def _must_have_id(self) -> FinancialInstitutionBranch:
        if not self.id:
            raise ValueError("FinancialInstitutionBranch.id is required")
        return self

    @model_serializer
    def _ser(self) -> dict[str, Any]:
        return {"ID": _leaf(self.id)}
