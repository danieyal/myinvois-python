"""Tests for myinvois.config — environment URLs and CertConfig."""

from __future__ import annotations

import pytest

from myinvois.config import (
    CertConfig,
    Environment,
    base_api_url,
    base_identity_url,
    base_portal_url,
)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (Environment.SANDBOX, "https://preprod-api.myinvois.hasil.gov.my"),
        (Environment.PRODUCTION, "https://api.myinvois.hasil.gov.my"),
    ],
)
def test_base_api_url(env: Environment, expected: str) -> None:
    assert base_api_url(env) == expected


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (Environment.SANDBOX, "https://preprod-api.myinvois.hasil.gov.my/connect/token"),
        (Environment.PRODUCTION, "https://api.myinvois.hasil.gov.my/connect/token"),
    ],
)
def test_base_identity_url(env: Environment, expected: str) -> None:
    assert base_identity_url(env) == expected


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (Environment.SANDBOX, "https://preprod.myinvois.hasil.gov.my"),
        (Environment.PRODUCTION, "https://myinvois.hasil.gov.my"),
    ],
)
def test_base_portal_url(env: Environment, expected: str) -> None:
    assert base_portal_url(env) == expected


def test_environment_is_string_enum() -> None:
    # StrEnum means `str(Environment.SANDBOX)` round-trips to its value.
    assert str(Environment.SANDBOX) == "sandbox"
    assert Environment("sandbox") is Environment.SANDBOX
    assert Environment("production") is Environment.PRODUCTION


def test_cert_config_defaults_to_none() -> None:
    cfg = CertConfig()
    assert cfg.private_key_path is None
    assert cfg.certificate_path is None
    assert cfg.private_key_bytes is None
    assert cfg.certificate_bytes is None


def test_cert_config_accepts_paths() -> None:
    cfg = CertConfig(
        private_key_path="/tmp/key.pem",
        certificate_path="/tmp/cert.base64",
    )
    assert cfg.private_key_path == "/tmp/key.pem"
    assert cfg.certificate_path == "/tmp/cert.base64"


def test_cert_config_accepts_bytes() -> None:
    cfg = CertConfig(
        private_key_bytes=b"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
        certificate_bytes=b"MIIB...",
    )
    assert cfg.private_key_bytes is not None
    assert cfg.certificate_bytes is not None
