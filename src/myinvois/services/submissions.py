"""Document-submission service — Phase 5 write endpoints.

Endpoints (mirrors the PHP SDK ``DocumentSubmissionService``):

- ``POST /api/v1.0/documentsubmissions/`` — submit one or more signed UBL
  documents. Returns HTTP 202 with the submission UID plus accepted/rejected
  document lists (see :class:`SubmitDocumentsResponse`).
- ``GET  /api/v1.0/documentsubmissions/{id}?pageNo=&pageSize=`` — pagination
  over the documents that belong to a single submission. Returns HTTP 200
  (see :class:`GetSubmissionResponse`).

The ``documents`` array sent to ``POST`` must contain one dict per document
with the four mandatory keys ``format``, ``document``, ``documentHash`` and
``codeNumber`` (spec: https://sdk.myinvois.hasil.gov.my/einvoicingapi/02-submit-documents/).
Use :func:`build_submission_payload` to build each entry — it auto-detects the
format (XML vs JSON) from the content, base64-encodes the payload, and
computes the SHA-256 hex digest exactly as the LHDN API expects.
"""

from __future__ import annotations

import base64
import hashlib
import json
from enum import StrEnum
from typing import TYPE_CHECKING

from myinvois.exceptions import ValidationError
from myinvois.services.models import (
    AcceptedDocument,
    DocumentSummary,
    DocumentSummaryTotals,
    GetSubmissionResponse,
    LhdnError,
    RejectedDocument,
    SubmitDocumentsResponse,
)

if TYPE_CHECKING:
    from myinvois.client import MyInvoisClient

__all__ = [
    "AcceptedDocument",
    "DocumentSubmissionFormat",
    "DocumentSummary",
    "DocumentSummaryTotals",
    "GetSubmissionResponse",
    "LhdnError",
    "RejectedDocument",
    "SubmissionOverallStatus",
    "SubmissionsService",
    "SubmitDocumentsResponse",
    "build_submission_payload",
]


class DocumentSubmissionFormat(StrEnum):
    """Format of the UBL document being submitted (sent as the ``format`` payload key).

    The LHDN Submit Documents API documents the values as ``"XML"`` and
    ``"JSON"`` (see https://sdk.myinvois.hasil.gov.my/einvoicingapi/02-submit-documents/#single-document-consists-of).
    Match the casing exactly.
    """

    XML = "XML"
    JSON = "JSON"


class SubmissionOverallStatus(StrEnum):
    """Overall batch-processing status returned by ``GET /documentsubmissions/{id}``.

    https://sdk.myinvois.hasil.gov.my/einvoicingapi/06-get-submission/
    """

    IN_PROGRESS = "in progress"
    VALID = "valid"
    PARTIALLY_VALID = "partially valid"
    INVALID = "invalid"


# ---------------------------------------------------------------------------
# build_submission_payload() helper
# ---------------------------------------------------------------------------


def _looks_like_json(content: bytes) -> bool:
    """``True`` if ``content`` decodes-and-parses as JSON, ``False`` otherwise.

    Matches PHP ``MyInvoisHelper::isJson()`` semantics: any leading whitespace
    stripped, then ``json.loads`` succeeds without raising.
    """
    try:
        json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return False
    return True


def build_submission_payload(
    code_number: str,
    content: bytes | str,
    *,
    format: DocumentSubmissionFormat | str | None = None,
) -> dict[str, str]:
    """Build the ``documents[]`` entry dict for a ``POST /documentsubmissions`` body.

    Mirrors PHP ``MyInvoisHelper::getSubmitDocument($codeNumber, $content)`` /
    the 3-arg variant ``getSubmitDocument($format, $codeNumber, $content)``.

    - ``content``: the (signed) UBL document, as ``bytes`` or ``str``. Used
      verbatim for both the ``base64.encode(document)`` field and the
      ``sha256(document)`` *hex* hash that LHDN expects (PHP ``MyInvoisHelper::getHash``
      returns lowercase hex via ``hash('sha256', ...)``).
    - ``format``: optional explicit override (``"XML"`` / ``"JSON"``); when
      ``None`` (default) it is inferred from the content's first non-whitespace
      character (``{`` / ``[`` -> JSON, otherwise XML — same heuristic as PHP).
    """
    raw = content.encode("utf-8") if isinstance(content, str) else content
    if format is None:
        fmt_val = "JSON" if _looks_like_json(raw) else "XML"
    elif isinstance(format, DocumentSubmissionFormat):
        fmt_val = format.value
    else:
        # Raw strings are accepted for symmetry with the rest of the SDK
        # (the public surface accepts raw strings next to enums).
        fmt_val = DocumentSubmissionFormat(str(format)).value
    return {
        "format": fmt_val,
        "document": base64.b64encode(raw).decode("ascii"),
        "documentHash": hashlib.sha256(raw).hexdigest(),
        "codeNumber": code_number,
    }


# ---------------------------------------------------------------------------
# SubmissionsService
# ---------------------------------------------------------------------------


class SubmissionsService:
    """Write-side operations for the LHDN document-submissions API.

    Exposed on :class:`~myinvois.client.MyInvoisClient` as
    ``client.submissions``.
    """

    BASE_PATH = "/api/v1.0/documentsubmissions"

    def __init__(self, client: MyInvoisClient) -> None:
        self._client = client

    def submit_documents(
        self,
        documents: list[dict[str, str]],
    ) -> SubmitDocumentsResponse:
        """Submit one or more signed UBL documents.

        ``documents`` must contain at least one entry; each entry is a dict
        with the four mandatory keys ``format``, ``document``, ``documentHash``,
        ``codeNumber``. Use :func:`build_submission_payload` to build each
        entry, or supply hand-built dicts directly.

        Returns a parsed :class:`SubmitDocumentsResponse`. The LHDN API
        responds with HTTP 202 (accepted for asynchronous validation);
        per-document sync-validation failures arrive as entries in
        ``rejected_documents`` while HTTP-level failures (4xx/5xx) raise a
        typed :class:`~myinvois.exceptions.MyInvoisError` subclass.
        """
        if not documents:
            raise ValidationError("submit_documents() requires a non-empty documents list.")
        body = {"documents": documents}
        raw = self._client.request("POST", f"{self.BASE_PATH}/", json=body)
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return SubmitDocumentsResponse.model_validate(raw)

    def get_submission(
        self,
        submission_uid: str,
        *,
        page_no: int | None = None,
        page_size: int | None = None,
    ) -> GetSubmissionResponse:
        """Retrieve a single submission's detail, paginated over its documents.

        ``page_no`` / ``page_size`` are optional; when ``None`` (default) they
        are not sent so the LHDN API returns the first page using its own
        defaults. The LHDN maximum page-size is 100.
        """
        params: dict[str, str] = {}
        if page_no is not None:
            params["pageNo"] = str(page_no)
        if page_size is not None:
            params["pageSize"] = str(page_size)
        raw = self._client.request(
            "GET", f"{self.BASE_PATH}/{submission_uid}", params=params or None
        )
        if not isinstance(raw, dict):
            raise TypeError(f"Expected dict from API, got {type(raw).__name__}")
        return GetSubmissionResponse.model_validate(raw)
