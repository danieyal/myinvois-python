"""Aggregate of the cryptographic primitives produced by a signer.

Both ``XmlSigner`` and ``JsonSigner`` expose a ``digests()`` method that
returns a populated ``SignerDigests`` instance, so the fixture tests can
isolate individual primitives rather than wait for the byte-for-byte
match on the final signed payload.

Field semantics:

* ``reference_1_value`` — ``base64(SHA256(document_to_be_signed))``;
  document_to_be_signed is the raw bytes emitted by the unsigned builder.
* ``reference_2_value`` — ``base64(SHA256(propsDigest_payload))``;
  for XML this is the c14N'd ``<xades:SignedProperties>`` subtree with
  5 xmlns-injections; for JSON this is the ``json.dumps`` form of the
  QualifyingProperties object (computed by ``_propsdigest_json.py``).
* ``cert_digest`` — ``base64(SHA256(cert_der_bytes))``.
* ``signature_value`` — ``base64(RSA-PKCS1v15-SHA256(document_to_be_signed))``.
  Always 344 chars for an RSA-2048 (PKCS#1 v1.5) signature.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignerDigests:
    reference_1_value: str
    reference_2_value: str
    cert_digest: str
    signature_value: str


__all__ = ["SignerDigests"]
