"""RED tests for the ``JsonSigner`` (XAdES-enveloped RSA-PKCS1v15-SHA256
signer for UBL JSON invoices).

Pins byte-for-byte equality between the Python-implemented signer and the
golden fixture ``tests/fixtures/golden_invoice_signed.json`` (md5
``18e7920ae3fdd812d03f76e37b513a21``). The fixture was generated deterministically
with the golden fixture generator using the same ``_sample_invoice()``
shape mirrored from ``tests/unit/test_envelope_builder.py`` and a fixed
``SigningTime = 2024-01-15T10:00:00Z``.

JSON diverges from XML in several important ways (PROVEN — see AGENTS.md):

* ``CanonicalizationMethod`` is NOT present inside ``SignedInfo``.
* ``Transforms`` array is NOT present inside ``Reference``.
* ``X509Data`` ADDS an ``X509SubjectName`` (= issuer-name string) BEFORE
  ``X509IssuerSerial`` (XML omits this). The XML variant only emits
  ``X509Certificate`` + ``X509IssuerSerial``.
* Reference 1 DigestValue (DocDigest) =
  ``base64(SHA256(unsigned_json_string.encode("utf-8")))`` (NOT SHA256 over
  XML reconstruction bytes). PROVEN match.
* Reference 2 DigestValue (PropsDigest) =
  ``base64(SHA256(json.dumps(qualifying_properties, separators=(",", ":"),
  ensure_ascii=False).encode("utf-8")))``
  - no whitespace stripping, no namespace replacement.
* CertDigest = ``base64(SHA256(cert_der))`` (identical to XML case).
* SignatureValue = ``base64(RSA-PKCS1v15-SHA256(unsigned_json_string.encode("utf-8")))``
  — signed over the JSON-string bytes, not XML bytes. PROVEN match.

Every test in this file is ``xfail(strict=True)`` until
``myinvois.ubl.signing.JsonSigner`` lands (Phase 4.7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

EXPECT_IMPLEMENTED = True

_XFAIL_REASON = (
    "JsonSigner not yet implemented (Phase 4.7). "
    "Set EXPECT_IMPLEMENTED=True at the top of this file once green."
)


def _maybe_xfail(func):
    if EXPECT_IMPLEMENTED:
        return func
    return pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)(func)


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

import sys  # noqa: E402

sys.path.insert(0, "tests/unit")
import test_envelope_builder as _json_fixture  # noqa: E402

_cert_pem = Path(__file__).resolve().parent.parent / "fixtures" / "cert" / "dummy_signing_cert.pem"
_key_pem = Path(__file__).resolve().parent.parent / "fixtures" / "cert" / "dummy_signing_key.pem"
_json_signed = Path(__file__).resolve().parent.parent / "fixtures" / "golden_invoice_signed.json"

_SIGNING_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

# Ground-truth primitive values (extracted from the fixture; guarded by
# isolated assertions so failures localise).
_EXPECTED_DOC_DIGEST_B64 = "RtAd1kuIdq57qY6MwyftOts3pS83ODOm2OmCbygGBHg="
_EXPECTED_PROPS_DIGEST_B64 = "a7a5p9SC7birTE1+vkMSEFB/ILTWp9aWR7SSfW1pTF0="
_EXPECTED_CERT_DIGEST_B64 = "UlhmSPmya4BK8Vd+VPdKdOxUAiLXC4F1uc1EB+NlaRM="
_EXPECTED_SIGNATURE_VALUE_PREFIX = "R//cvLKAAF73nRogLgFhStZVJPLJZTfZyFexFwiGjMN"


# ---------------------------------------------------------------------------
# Lazy importers.
# ---------------------------------------------------------------------------


def _import_signer():
    if EXPECT_IMPLEMENTED:
        from myinvois.ubl.signing import JsonSigner

        return JsonSigner
    pytest.skip("myinvois.ubl.signing.JsonSigner not yet importable")


def _import_certconfig():
    if EXPECT_IMPLEMENTED:
        from myinvois.config import CertConfig

        return CertConfig
    pytest.skip("CertConfig not yet importable (already exists but kept lazy for xfail)")


def _build_unsigned_json() -> bytes:
    """Use JsonEnvelopeBuilder to produce the same unsigned JSON the fixture
    was generated from."""
    from myinvois.ubl.builders import JsonEnvelopeBuilder

    builder = JsonEnvelopeBuilder(_json_fixture._sample_invoice())
    return builder.build_json().encode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJsonSignerAcceptanceContract:
    @_maybe_xfail
    def test_sign_returns_str(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert isinstance(out, str)

    @_maybe_xfail
    def test_sign_accepts_bytes_or_str(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out_b = JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        out_s = JsonSigner(cert).sign(
            _build_unsigned_json().decode("utf-8"), signing_time=_SIGNING_TIME
        )
        assert out_b == out_s


class TestJsonSignerPrimitiveDigests:
    @_maybe_xfail
    def test_reference_1_doc_digest_matches_fixture(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).digests(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert out.reference_1_value == _EXPECTED_DOC_DIGEST_B64

    @_maybe_xfail
    def test_reference_2_props_digest_matches_fixture(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).digests(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert out.reference_2_value == _EXPECTED_PROPS_DIGEST_B64

    @_maybe_xfail
    def test_cert_digest_matches_fixture(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).digests(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert out.cert_digest == _EXPECTED_CERT_DIGEST_B64

    @_maybe_xfail
    def test_signature_value_matches_fixture_prefix(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).digests(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert out.signature_value.startswith(_EXPECTED_SIGNATURE_VALUE_PREFIX)


class TestJsonSignerGoldenByteParity:
    @_maybe_xfail
    def test_signed_json_string_bytes_match_fixture_exact(self) -> None:
        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert out.encode("utf-8") == _json_signed.read_bytes()

    @_maybe_xfail
    def test_signed_json_md5_matches_fixture(self) -> None:
        import hashlib

        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME)
        assert hashlib.md5(out.encode("utf-8")).hexdigest() == "18e7920ae3fdd812d03f76e37b513a21"


class TestJsonStructuralInvariants:
    """JSON-only differences from XML wiring that the signer must preserve."""

    @_maybe_xfail
    def test_signed_info_omits_canonicalization_method(self) -> None:
        import json

        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = json.loads(JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME))
        sig = out["Invoice"][0]["UBLExtensions"][0]["UBLExtension"][0]["ExtensionContent"][0][
            "UBLDocumentSignatures"
        ][0]["SignatureInformation"][0]["Signature"][0]
        assert "CanonicalizationMethod" not in sig["SignedInfo"][0]

    @_maybe_xfail
    def test_reference_block_omits_transforms(self) -> None:
        import json

        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = json.loads(JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME))
        refs = out["Invoice"][0]["UBLExtensions"][0]["UBLExtension"][0]["ExtensionContent"][0][
            "UBLDocumentSignatures"
        ][0]["SignatureInformation"][0]["Signature"][0]["SignedInfo"][0]["Reference"]
        for ref in refs:
            assert "Transforms" not in ref

    @_maybe_xfail
    def test_x509_data_includes_x509_subject_name_before_issuer_serial(self) -> None:
        import json

        JsonSigner = _import_signer()
        CertConfig = _import_certconfig()
        cert = CertConfig(certificate_path=str(_cert_pem), private_key_path=str(_key_pem))
        out = json.loads(JsonSigner(cert).sign(_build_unsigned_json(), signing_time=_SIGNING_TIME))
        x509_data = out["Invoice"][0]["UBLExtensions"][0]["UBLExtension"][0]["ExtensionContent"][0][
            "UBLDocumentSignatures"
        ][0]["SignatureInformation"][0]["Signature"][0]["KeyInfo"][0]["X509Data"][0]
        keys = list(x509_data.keys())
        assert "X509SubjectName" in keys
        assert "X509IssuerSerial" in keys
        assert keys.index("X509SubjectName") < keys.index("X509IssuerSerial")
