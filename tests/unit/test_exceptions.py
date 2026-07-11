"""Tests for myinvois.exceptions — error hierarchy mapped to HTTP status."""

from __future__ import annotations

import pytest

from myinvois.exceptions import (
    AuthenticationError,
    MyInvoisError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    error_for_status,
)


def test_base_myinvois_error_is_exception() -> None:
    err = MyInvoisError("boom")
    assert isinstance(err, Exception)
    assert str(err) == "boom"
    assert err.status_code is None


def test_validation_error_maps_400() -> None:
    err = ValidationError("bad request", status_code=400)
    assert err.status_code == 400
    assert isinstance(err, MyInvoisError)


def test_auth_error_maps_401() -> None:
    err = AuthenticationError("unauthorized", status_code=401)
    assert err.status_code == 401
    assert isinstance(err, MyInvoisError)


def test_not_found_error_maps_404() -> None:
    err = NotFoundError("missing", status_code=404)
    assert err.status_code == 404


def test_rate_limit_error_maps_429() -> None:
    err = RateLimitError("slow down", status_code=429)
    assert err.status_code == 429


@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (400, ValidationError),
        (401, AuthenticationError),
        (403, AuthenticationError),
        (404, NotFoundError),
        (409, MyInvoisError),
        (429, RateLimitError),
        (500, MyInvoisError),
        (503, MyInvoisError),
    ],
)
def test_error_for_status_factory(status: int, exc_type: type[MyInvoisError]) -> None:
    err = error_for_status("oops", status_code=status)
    assert isinstance(err, exc_type)
    assert err.status_code == status
    assert str(err) == "oops"


def test_error_for_status_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        error_for_status("nope", status_code=99)
    with pytest.raises(ValueError):
        error_for_status("nope", status_code=600)
