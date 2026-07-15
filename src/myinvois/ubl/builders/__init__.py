"""UBl envelope builders: ``JsonEnvelopeBuilder`` (canonical LHDN wire form) and
``XmlEnvelopeBuilder`` (XML counterpart, Phase 4 / XAdES-signed form).

The JSON builder produces byte-identical output to the PHP SDK's
``JsonDocumentBuilder::build()`` so Phase 4 signature digests round-trip
through LHDN's validator unchanged.
"""

from __future__ import annotations

from .json import JsonEnvelopeBuilder
from .xml import XmlEnvelopeBuilder

__all__ = ["JsonEnvelopeBuilder", "XmlEnvelopeBuilder"]
