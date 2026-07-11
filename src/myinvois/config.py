"""Configuration: environment URLs and certificate configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["CertConfig", "Environment", "base_api_url", "base_identity_url", "base_portal_url"]


class Environment(StrEnum):
    """MyInvois environment selector.

    Use `Environment.SANDBOX` (`preprod`) for development and
    `Environment.PRODUCTION` for live calls.
    """

    SANDBOX = "sandbox"
    PRODUCTION = "production"


# Base hostnames verified from klsheng/myinvois-php-sdk (IdentityService / DocumentService).
_API_HOSTS: dict[Environment, str] = {
    Environment.SANDBOX: "https://preprod-api.myinvois.hasil.gov.my",
    Environment.PRODUCTION: "https://api.myinvois.hasil.gov.my",
}

# The MyInvois portal (used for generating shareable document QR-code URLs).
_PORTAL_HOSTS: dict[Environment, str] = {
    Environment.SANDBOX: "https://preprod.myinvois.hasil.gov.my",
    Environment.PRODUCTION: "https://myinvois.hasil.gov.my",
}


def base_api_url(env: Environment) -> str:
    """Return the API base URL (without trailing slash) for the environment."""
    if env not in _API_HOSTS:
        raise ValueError(f"Unknown environment: {env!r}")
    return _API_HOSTS[env]


def base_identity_url(env: Environment) -> str:
    """Return the OAuth2 token endpoint URL for the environment."""
    return f"{base_api_url(env)}/connect/token"


def base_portal_url(env: Environment) -> str:
    """Return the MyInvois portal base URL (for QR-code share URLs)."""
    if env not in _PORTAL_HOSTS:
        raise ValueError(f"Unknown environment: {env!r}")
    return _PORTAL_HOSTS[env]


@dataclass(frozen=True, slots=True)
class CertConfig:
    """Digital-signing certificate configuration.

    Supply credentials either via filesystem paths or raw bytes. Bytes take
    precedence when both are provided. The library never reads these
    automatically on import — they are only consumed when a document is
    signed (Phase 4).

    - `private_key_path` / `certificate_path`: filesystem paths. The private
      key is expected to be a PEM-encoded PKCS#8 key (``-----BEGIN PRIVATE
      KEY-----``). The certificate is expected to be the raw base64 of a
      DER-encoded X.509 certificate (as published by LHDN / the gateway).
    - `private_key_bytes` / `certificate_bytes`: same content, supplied
      directly as ``bytes`` (e.g. from an env var or a secret store).
    """

    private_key_path: str | None = None
    certificate_path: str | None = None
    private_key_bytes: bytes | None = None
    certificate_bytes: bytes | None = None
