"""Pydantic response models returned by the MyInvois API.

These models are read-side response schemas (Phase 2). Phase 3 will add the
write-side UBL document models under ``myinvois.ubl.models``.

Conventions:
- snake_case aliases for the LHDN camelCase JSON fields via Pydantic `alias`.
- Optional fields are tolerant of missing keys (`model_config = ConfigDict(extra="ignore")`)
  so forward-compatible additions by LHDN don't break parsing.
- Unknown fields are *ignored* (not rejected) — LHDN can add fields safely.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DocumentType",
    "DocumentTypeList",
    "DocumentTypeSchema",
    "DocumentTypeVersion",
    "Paginated",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Paginated(_Base):
    page_size: int
    total_pages: int = 0


class DocumentTypeSchema(_Base):
    schema_id: str | None = Field(default=None, alias="schemaId")
    valid_from: str | None = Field(default=None, alias="validFrom")
    valid_to: str | None = Field(default=None, alias="validTo")


class DocumentType(_Base):
    id: int
    name: str
    description: str | None = None
    code_number: str | None = Field(default=None, alias="codeNumber")
    active_since: str | None = Field(default=None, alias="activeSince")
    active_to: str | None = Field(default=None, alias="activeTo")
    active_version_id: int | None = Field(default=None, alias="activeVersionId")


class DocumentTypeVersion(_Base):
    id: int
    name: str
    description: str | None = None
    version_number: str | None = Field(default=None, alias="versionNumber")
    active_since: str | None = Field(default=None, alias="activeSince")
    active_to: str | None = Field(default=None, alias="activeTo")
    schemas: list[DocumentTypeSchema] = Field(default_factory=list)


class DocumentTypeList(_Base):
    total_pages: int = Field(default=0, alias="totalPages")
    page_size: int = Field(default=0, alias="pageSize")
    result: list[DocumentType]


# A small helper used by services to wrap raw dicts as models where the LHDN
# response shape is a plain list (no `result` wrapper).
def _as_items(raw: Any, *, model: type[BaseModel], key: str = "result") -> list[BaseModel]:
    if isinstance(raw, dict) and key in raw and isinstance(raw[key], list):
        return [model.model_validate(item) for item in raw[key]]
    if isinstance(raw, list):
        return [model.model_validate(item) for item in raw]
    return []
