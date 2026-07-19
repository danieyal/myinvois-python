"""RED tests for the ``XmlSigner`` (XAdES-enveloped RSA-PKCS1v15-SHA256
signer for UBL XML invoices).

Pins byte-for-byte equality between the Python-implemented signer and the
golden fixture
``tests/fixtures/golden_invoice_signed.xml`` (md5 ``f36a659302dff7d7de0a0df725e43ad6``).
The fixture was generated deterministically with
the golden fixture generator using the same ``_sample_invoice()`` shape
mirrored from ``tests/unit/test_envelope_builder.py`` and a fixed
``SigningTime = 2024-01-15T10:00:00Z``.

Every test in this file is marked ``xfail(strict=True)`` until
``myinvois.ubl.signing.XmlSigner`` lands (Phase 4.6). Flip
``EXPECT_IMPLEMENTED = True`` at the top once the implementation is green.

Reference ground-truth (byte-for-byte with golden fixtures — see AGENTS.md
PHASE 4 section):

* Reference 1 DigestValue (DocDigest) — ``base64(SHA256(unsigned_xml_bytes))``
  → ``YtB0oeTpmTm7tBNDEaYt+wn+mvYjwzCQqXaxdqR8sjU=``
* Reference 2 DigestValue (PropsDigest) — bytes produced by the
  *xml-c14N* (+5 string-namespace injections) over the SignedProperties
  subtree → ``YcW987MWbZLRt0NDwjbU746lTtKStZ0grXZlak/X+xE=``
* CertDigest — ``base64(SHA256(cert_der))`` →
  ``UlhmSPmya4BK8Vd+VPdKdOxUAiLXC4F1uc1EB+NlaRM=``
* SignatureValue — RSA-PKCS1v15-SHA256 over the *unsigned* XML bytes
  (unwrapped from the UBLExtensions/sig:UBLDocumentSignatures block),
  base64-encoded, 344 chars.

If any of these primitives drift from the reference output this file localises
the failure to a single primitive before the final byte-for-byte assertion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

# Flip to True once XmlSigner is implemented.
EXPECT_IMPLEMENTED = True

_XFAIL_REASON = (
    "XmlSigner not yet implemented (Phase 4.6). "
    "Set EXPECT_IMPLEMENTED=True at the top of this file once green."
)


def _maybe_xfail(func):
    if EXPECT_IMPLEMENTED:
        return func
    return pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)(func)


# ---------------------------------------------------------------------------
# Fixture paths + sample invoice duplication points.
# ---------------------------------------------------------------------------

import sys  # noqa: E402

sys.path.insert(0, "tests/unit")
import test_envelope_builder as _json_fixture  # noqa: E402

_cert_pem = Path(__file__).resolve().parent.parent / "fixtures" / "cert" / "dummy_signing_cert.pem"
_key_pem = Path(__file__).resolve().parent.parent / "fixtures" / "cert" / "dummy_signing_key.pem"
_xml_signed = Path(__file__).resolve().parent.parent / "fixtures" / "golden_invoice_signed.xml"
_xml_unsigned = Path(__file__).resolve().parent.parent / "fixtures" / "golden_invoice_unsigned.xml"

_SIGNING_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

# Ground-truth primitive values (extracted from the fixture; guarded by
# isolated assertions so failures localise).
_EXPECTED_DOC_DIGEST_B64 = "YtB0oeTpmTm7tBNDEaYt+wn+mvYjwzCQqXaxdqR8sjU="
_EXPECTED_PROPS_DIGEST_B64 = "YcW987MWbZLRt0NDwjbU746lTtKStZ0grXZlak/X+xE="
_EXPECTED_CERT_DIGEST_B64 = "UlhmSPmya4BK8Vd+VPdKdOxUAiLXC4F1uc1EB+NlaRM="
_EXPECTED_SIGNATURE_VALUE_PREFIX = (
    "bst+LGcuaLayiKZIhGY5HzrdNn2yaKIs1yMBF97zGwWf8RtI2J0iHrQb4/WHh3RO"
)


# ---------------------------------------------------------------------------
# Lazy importer so importing this module before the impl exists is safe.
# ---------------------------------------------------------------------------


def _import_signer():
    if EXPECT_IMPLEMENTED:
        from myinvois.ubl.signing import XmlSigner

        return XmlSigner
    pytest.skip("myinvois.ubl.signing.XmlSigner not yet importable")


def _import_certconfig():
    if EXPECT_IMPLEMENTED:
        from myinvois.config import CertConfig

        return CertConfig
    pytest.skip("CertConfig not yet importable (already exists but kept lazy for xfail)")


def _build_unsigned_xml() -> bytes:
    """Use XmlEnvelopeBuilder to produce the same unsigned bytes as the reference
    fixture was generated from (md5-checks against
    ``golden_invoice_unsigned.xml``)."""
    from myinvois.ubl.builders import XmlEnvelopeBuilder

    builder = XmlEnvelopeBuilder(_json_fixture._sample_invoice())
    return builder.build_xml().encode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestXmlSignerAcceptanceContract:
    """The high-level contract for ``XmlSigner.sign``."""

    @_maybe_xfail
    def test_sign_returns_bytes(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(
            certificate_path=str(_cert_pem),
            private_key_path=str(_key_pem),
        )
        signer = XmlSigner(cert)
        out = signer.sign(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert isinstance(out, bytes)

    @_maybe_xfail
    def test_sign_accepts_byte_or_str_inputs(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out_bytes_in = XmlSigner(cert).sign(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        out_str_in = XmlSigner(cert).sign(
            _build_unsigned_xml().decode("utf-8"), signing_time=_SIGNING_TIME
        )
        assert out_bytes_in == out_str_in


class TestXmlSignerPrimitiveDigests:
    """Isolated assertions for every cryptographic primitive the signer emits,
    so a drift localises immediately rather than the final byte-for-byte test
    burrying the deployment error."""

    @_maybe_xfail
    def test_reference_1_doc_digest_matches_fixture(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).digests(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert out.reference_1_value == _EXPECTED_DOC_DIGEST_B64

    @_maybe_xfail
    def test_reference_2_props_digest_matches_fixture(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).digests(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert out.reference_2_value == _EXPECTED_PROPS_DIGEST_B64

    @_maybe_xfail
    def test_cert_digest_matches_fixture(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).digests(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert out.cert_digest == _EXPECTED_CERT_DIGEST_B64

    @_maybe_xfail
    def test_signature_value_matches_fixture_prefix(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).digests(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert out.signature_value.startswith(_EXPECTED_SIGNATURE_VALUE_PREFIX)


class TestXmlSignerGoldenByteParity:
    """The byte-for-byte pin against the golden fixture."""

    @_maybe_xfail
    def test_signed_xml_bytes_match_fixture_exact(self) -> None:
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).sign(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert out == _xml_signed.read_bytes(), (
            f"OUTPUT_LEN={len(out)} FIXTURE_LEN={_xml_signed.stat().st_size}"
        )

    @_maybe_xfail
    def test_signed_xml_md5_matches_fixture(self) -> None:
        """Weaker than byte-for-byte but cheaper on failure output."""
        import hashlib

        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).sign(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert hashlib.md5(out).hexdigest() == "f36a659302dff7d7de0a0df725e43ad6"


class TestXmlSignerStructuralInvariants:
    """Immutability/structural invariants of the signed XML output."""

    @_maybe_xfail
    def test_invoice_type_code_list_version_id_is_1_1_after_signing(self) -> None:
        """The reference XmlDocumentBuilder flips ``InvoiceTypeCode['listVersionID']``
        from ``"1.0"`` to ``"1.1"`` after signing — the Python signer must
        mutate the same way."""
        XmlSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = XmlSigner(cert).sign(_build_unsigned_xml(), signing_time=_SIGNING_TIME)
        assert 'cbc:InvoiceTypeCode listVersionID="1.1"' in out.decode("utf-8")


class TestXmlInputSanityPreSign:
    """Sanity check that the unsigned XML produced by ``XmlEnvelopeBuilder``
    matches the fixture's pre-sign state — these do NOT require the signer
    and therefore must pass even before the signer exists. (They guard
    against the fixture drifting silently under future refactorings.)"""

    def test_unsigned_xml_carries_list_version_id_1_0_before_signing(self) -> None:
        assert 'cbc:InvoiceTypeCode listVersionID="1.0"' in _build_unsigned_xml().decode("utf-8")

    def test_unsigned_xml_md5_matches_golden_invoice_unsigned_fixture(self) -> None:
        """The bytes fed to the signer must equal the canonical unsigned
        reference (md5 ``099e266ef6bb24d064261f155c2bc38c``)."""
        import hashlib

        out = _build_unsigned_xml()
        assert hashlib.md5(out).hexdigest() == "099e266ef6bb24d064261f155c2bc38c"
