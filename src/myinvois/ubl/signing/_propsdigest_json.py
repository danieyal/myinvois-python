"""JSON PropsDigest helper.

Produces the SHA-256-base64 hash over the canonical QualifyingProperties JSON
byte sequence.

Canonical JSON encoding rules:

* No whitespace → Python ``separators=(",", ":")``.
* Non-ASCII passes through literally → Python ``ensure_ascii=False``.
* Forward slashes are NOT backslash-escaped (the default in Python).

The QualifyingProperties JSON structure (the canonical LHDN wire form)::

    {
      "Target": "signature",
      "SignedProperties": [{
        "Id": "id-xades-signed-props",
        "SignedSignatureProperties": [{
          "SigningTime": [{"_": "<2024-01-15T10:00:00Z>"}],
          "SigningCertificate": [{
            "Cert": [{
              "CertDigest": [{
                "DigestMethod": [{"_": "", "Algorithm": "...xmlenc#sha256"}],
                "DigestValue":     [{"_": "<b64-sha256-of-cert-der>"}]
              }],
              "IssuerSerial": [{
                "X509IssuerName":   [{"_": "<issuer-DN>"}],
                "X509SerialNumber": [{"_": "<0xUPPERHEX>"}]
              }]
            }]
          }]
        }]
      }]
    }
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

_DIGEST_METHOD_ALGORITHM = "http://www.w3.org/2001/04/xmlenc#sha256"


def compute_props_digest_json(
    issuer_name: str,
    serial_number_hex: str,
    cert_digest_b64: str,
    signing_time_str: str,
) -> str:
    """Return the base64-encoded SHA-256 of the QualifyingProperties JSON.

    The bytes-to-hash are emitted with canonical-JSON semantics: no
    whitespace, no Unicode escapes, no slash backslash-escapes.
    """
    qp = _build_qualifying_properties_dict(
        issuer_name=issuer_name,
        serial_number_hex=serial_number_hex,
        cert_digest_b64=cert_digest_b64,
        signing_time_str=signing_time_str,
    )
    encoded = json.dumps(
        qp,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return base64.b64encode(hashlib.sha256(encoded).digest()).decode("ascii")


def _build_qualifying_properties_dict(
    issuer_name: str,
    serial_number_hex: str,
    cert_digest_b64: str,
    signing_time_str: str,
) -> dict[str, Any]:
    """Build the canonical QualifyingProperties JSON dict."""
    return {
        "Target": "signature",
        "SignedProperties": [
            {
                "Id": "id-xades-signed-props",
                "SignedSignatureProperties": [
                    {
                        "SigningTime": [{"_": signing_time_str}],
                        "SigningCertificate": [
                            {
                                "Cert": [
                                    {
                                        "CertDigest": [
                                            {
                                                "DigestMethod": [
                                                    {"_": "", "Algorithm": _DIGEST_METHOD_ALGORITHM}
                                                ],
                                                "DigestValue": [{"_": cert_digest_b64}],
                                            }
                                        ],
                                        "IssuerSerial": [
                                            {
                                                "X509IssuerName": [{"_": issuer_name}],
                                                "X509SerialNumber": [{"_": serial_number_hex}],
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }


__all__ = ["compute_props_digest_json"]
