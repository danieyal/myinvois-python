"""Certificate utilities for the XAdES signer.

It exposes 5 helpers, each pinned against the canonical LHDN wire forms
recorded in the golden fixtures built from the test cert bundle at
``tests/fixtures/cert/dummy_signing_{cert,key}.pem``:

* ``load_x509(pem_bytes)`` -> ``cryptography.x509.Certificate``
* ``load_private_key(pem_bytes, password=None)`` -> ``cryptography...RSAPrivateKey``
* ``cert_pem_raw_content(pem_str)`` -> ``str`` (the bytes for
  ``<ds:X509Certificate>...</ds:X509Certificate>``).
* ``issuer_name_string(cert)`` -> ``str`` (the bytes for
  ``<ds:X509IssuerName>...</ds:X509IssuerName>`` and JSON
  ``X509SubjectName``); follows the canonical LHDN ``CN/E/OU/O/C`` reorder.
* ``serial_number_string(cert)`` -> ``str`` (the bytes for
  ``<ds:X509SerialNumber>...</ds:X509SerialNumber>``): ``"0x" + UPPER_HEX``.
* ``cert_digest_b64(cert)`` -> ``str`` (the bytes for the
  ``<ds:DigestValue>`` inside ``<xades:CertDigest>``);
  ``base64(SHA256(cert_der))``.

Canonical wire-form rules:

* ``getRawContent`` strips ``-----BEGIN-----``/``-----END-----`` lines and
  ANY trailing blank line, then concatenates the remaining base64 chunks
  with no separators.
* Issuer-name string: iterate the cert's issuer attributes in their DER
  order (OpenSSL's natural reading order), then move the LHDN-required
  ``CN``/``E``/``OU``/``O``/``C`` keys to the end in that fixed order; any
  unlisted keys keep their natural iteration slot before the listed ones.
  Joined as ``"CN=v, OU=v, O=v, C=v"`` (``", "`` separator).
* Serial-number string: ``"0x" + UPPER_HEX`` of the certificate's integer
  serial number. Note: leading zero hex digits from the serialised DER are
  not preserved here — not observed on LHDN-issued certs but worth guarding
  if a future cert shape triggers it.
* Cert digest: ``base64(SHA256(cert_der))``.
"""

from __future__ import annotations

import base64
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import Encoding, load_pem_private_key

if TYPE_CHECKING:
    from myinvois.config import CertConfig

__all__ = [
    "LoadedCert",
    "cert_digest_b64",
    "cert_pem_raw_content",
    "issuer_name_string",
    "load_cert_config",
    "load_private_key",
    "load_x509",
    "serial_number_string",
    "sign_sha256",
]


# ---------------------------------------------------------------------------
# Lazy CertConfig import to avoid a circular dependency
# (config.py is at the package top, this module is under ubl/signing/).
# We pull it lazily inside load_private_key_cert_pair_* callers if needed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadedCert:
    """Bundle of everything the signer needs from a CertConfig."""

    cert: x509.Certificate
    private_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey
    raw_pem_cert: str  # munged base64 (no BEGIN/END); used in ``<ds:X509Certificate>``
    raw_pem_private_key: str  # munged base64 (no BEGIN/END); used only by signing-side.
    # Note: signing itself uses the private key object directly, NOT raw_pem_private_key.


def load_x509(pem_bytes: bytes) -> x509.Certificate:
    """Parse a PEM-encoded X.509 certificate."""
    return x509.load_pem_x509_certificate(pem_bytes)


def load_private_key(
    pem_bytes: bytes, password: bytes | None = None
) -> rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey:
    """Parse a PEM-encoded PKCS#8 private key (or EC PRIVATE KEY).

    The MyInvois / LHDN SDK only officially supports RSA signatures today;
    EC types are tolerated so a later LHDN schema bump doesn't break the
    parser (but signers will fall through to RSA-PKCS1v15-SHA256).
    """
    key = load_pem_private_key(pem_bytes, password=password)
    if not isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)):
        raise TypeError(f"Unsupported private key type {type(key).__name__!r}; expected RSA or EC.")
    return key


# ---------------------------------------------------------------------------
# cert_pem_raw_content — strip BEGIN/END lines + trailing empties,
# then concatenate the rest WITHOUT separators.
# ---------------------------------------------------------------------------


def cert_pem_raw_content(pem_str: str) -> str:
    """Return the *raw* base64 body of a PEM-encoded cert/key.

    Output has no ``\\n`` separators between base64 chunks; see module
    docstring for the canonical wire-form rules.
    """
    content = pem_str.replace("\r", "")
    parts = content.split("\n")
    # Drop BEGIN line (always index 0 for a well-formed PEM).
    if parts and parts[0].startswith("-----BEGIN"):
        del parts[0]
    # Drop trailing blank lines (PEM files end with a newline).
    while parts and parts[-1] == "":
        parts.pop()
    # Drop END line (now the last entry).
    if parts and parts[-1].startswith("-----END"):
        parts.pop()
    return "".join(parts)


# ---------------------------------------------------------------------------
# Issuer name string — reorder to ['CN', 'E', 'OU', 'O', 'C'] (the LHDN-mandated
# order), preserving unlisted keys in their natural iteration slot before the
# listed keys are appended. Joined with ``", "`` separator as ``k=v`` items.
# ---------------------------------------------------------------------------


def issuer_name_string(cert: x509.Certificate) -> str:
    """Return the canonical LHDN issuer/subject-name string.

    The cert's issuer attributes are iterated in their DER (OpenSSL natural
    reading) order. The LHDN-required keys (``CN``, ``E``, ``OU``, ``O``,
    ``C``) are then moved to the end in that fixed order; any unlisted keys
    keep their natural iteration slot before the listed ones. Joined as
    ``"CN=v, OU=v, O=v, C=v"``.

    ``cryptography.x509.Name`` exposes issuer attributes as a sequence of
    ``NameOID`` items; we use a curated key map below so the output order
    matches the canonical LHDN cert shapes pinned by the golden fixtures.
    """
    # Build the natural-order issuer dict. The iteration of
    # `Name.attributes` follows OUTER-to-INNER in ASN.1 order (which for a
    # `C, O, OU, emailAddress, CN` cert layout would yield C, O, OU,
    # emailAddress, CN). OpenSSL preserves reading order from the cert's DER;
    # we mirror that by reading attributes in the iteration order cryptography
    # gives us, mapping each to its canonical short key.
    issuer_dict: OrderedDict[str, str] = OrderedDict()
    for attr in cert.issuer:
        key = _oid_to_canonical_short_key(attr.oid)
        if key is None:
            # Skip OID we don't know — canonical form still includes it under
            # its dotted-decimal OID string, so preserve that behaviour.
            key = attr.oid.dotted_string
        issuer_dict[key] = attr.value if isinstance(attr.value, str) else str(attr.value)

    # Apply the LHDN-mandated reorder: ['CN', 'E', 'OU', 'O', 'C'].
    # Each key, if present, is moved to the *end* in that order.
    issuer_keys = ["CN", "E", "OU", "O", "C"]
    for key in issuer_keys:
        if key in issuer_dict:
            value = issuer_dict.pop(key)
            issuer_dict[key] = value
    # Join as ``k1=v1, k2=v2`` using ``", "`` separator. Issuer DN values are
    # restricted (the CN/emailAddress strings do not contain URL-special
    # chars), so plain ``f"{k}={v}"`` items match the canonical wire form.
    return ", ".join(f"{k}={v}" for k, v in issuer_dict.items())


_OID_TO_CANONICAL_SHORT_KEY = {
    # cryptography NameOID -> canonical LHDN short key
    x509.oid.NameOID.COMMON_NAME: "CN",
    x509.oid.NameOID.SURNAME: "SN",
    x509.oid.NameOID.SERIAL_NUMBER: "serialNumber",
    x509.oid.NameOID.COUNTRY_NAME: "C",
    x509.oid.NameOID.LOCALITY_NAME: "L",
    x509.oid.NameOID.STATE_OR_PROVINCE_NAME: "ST",
    x509.oid.NameOID.ORGANIZATION_NAME: "O",
    x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME: "OU",
    x509.oid.NameOID.EMAIL_ADDRESS: "emailAddress",
    # OpenSSL represents emailAddress via the PKCS#9 emailAddress OID
    # (1.2.840.113549.1.9.1) — cryptography exposes it as ``NameOID.EMAIL_ADDRESS``
    # which is the same OID; included above for clarity.
}


def _oid_to_canonical_short_key(oid: x509.ObjectIdentifier) -> str | None:
    return _OID_TO_CANONICAL_SHORT_KEY.get(oid)


# ---------------------------------------------------------------------------
# Serial number string — ``"0x" + UPPER_HEX`` of the certificate's integer
# serial number.
# ---------------------------------------------------------------------------


def serial_number_string(cert: x509.Certificate) -> str:
    """Return the canonical LHDN serial-number string ``0x<UPPER_HEX>``.

    Edge case: a serialised serial may preserve leading zero hex digits that
    Python ``format(n, 'X')`` strips. For a 2^160 SHA-1 serial with no leading
    zero both match. A separate test should guard the leading-zero edge case
    if/when we encounter it in production.
    """
    return "0x" + format(cert.serial_number, "X")


# ---------------------------------------------------------------------------
# Cert digest — ``base64(SHA256(cert_der))``.
# ---------------------------------------------------------------------------


def cert_digest_b64(cert: x509.Certificate) -> str:
    """Return the CertDigest = ``base64(SHA256(cert.public_bytes(DER)))``."""
    cert_der = cert.public_bytes(Encoding.DER)
    return base64.b64encode(_sha256(cert_der)).decode("ascii")


def _sha256(data: bytes) -> bytes:
    import hashlib

    return hashlib.sha256(data).digest()


# ---------------------------------------------------------------------------
# Sign with RSA-PKCS1v15-SHA256. For EC keys the LHDN SDK does not define a
# path; we raise rather than silently fail.
# ---------------------------------------------------------------------------


def sign_sha256(data: bytes, private_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey) -> bytes:
    """RSA-PKCS1v15-SHA256 sign ``data`` and return the raw signature bytes."""
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise TypeError(
            "Only RSA private keys are supported for LHDN e-invoice signing; "
            f"got {type(private_key).__name__!r}."
        )
    return private_key.sign(data, PKCS1v15(), hashes.SHA256())


# ---------------------------------------------------------------------------
# Convenience: namedtuple-like loader that resolves a ``CertConfig`` once
# and pre-computes every helper output the signer will need.
# ---------------------------------------------------------------------------


def load_cert_config(cert_config: CertConfig) -> LoadedCert:
    """Resolve a ``CertConfig`` -> ``LoadedCert`` reading cert + private key.

    The dataclass contract: ``bytes`` takes precedence over ``path`` if both
    are supplied. The library NEVER reads the PEM on import; this is the only
    place the actual file/secret is consumed.
    """
    cert_pem_bytes: bytes
    key_pem_bytes: bytes
    if cert_config.certificate_bytes is not None:
        cert_pem_bytes = cert_config.certificate_bytes
    elif cert_config.certificate_path is not None:
        cert_pem_bytes = _read_path(cert_config.certificate_path)
    else:
        raise ValueError("CertConfig needs either certificate_path or certificate_bytes")

    if cert_config.private_key_bytes is not None:
        key_pem_bytes = cert_config.private_key_bytes
    elif cert_config.private_key_path is not None:
        key_pem_bytes = _read_path(cert_config.private_key_path)
    else:
        raise ValueError("CertConfig needs either private_key_path or private_key_bytes")

    cert = load_x509(cert_pem_bytes)
    private_key = load_private_key(key_pem_bytes)
    return LoadedCert(
        cert=cert,
        private_key=private_key,
        raw_pem_cert=cert_pem_raw_content(cert_pem_bytes.decode("utf-8")),
        raw_pem_private_key=cert_pem_raw_content(key_pem_bytes.decode("utf-8")),
    )


def _read_path(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
