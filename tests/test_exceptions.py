"""Tests for the exception hierarchy and ValidationError did-you-mean."""

from __future__ import annotations

from fungo.exceptions import (
    FungoError,
    MLBStatsError,
    RequestError,
    SavantError,
    ValidationError,
)


def test_hierarchy():
    assert issubclass(RequestError, FungoError)
    assert issubclass(SavantError, FungoError)
    assert issubclass(MLBStatsError, FungoError)
    assert issubclass(ValidationError, FungoError)
    assert issubclass(ValidationError, ValueError)


def test_request_error_status():
    assert RequestError("offline").status is None
    err = RequestError("HTTP 403 for x", status=403)
    assert err.status == 403
    assert str(err) == "HTTP 403 for x"


def test_validation_error_suggests_close_match():
    err = ValidationError("Dodgrs", "team", ["Dodgers", "Padres", "Giants"])
    msg = str(err)
    assert "Dodgrs" in msg
    assert "Did you mean 'Dodgers'?" in msg


def test_validation_error_lists_values_when_no_close_match():
    err = ValidationError("zzz", "team", ["Dodgers", "Padres"])
    msg = str(err)
    assert "Valid values:" in msg
    assert "Dodgers" in msg


def test_validation_error_without_valid_values():
    err = ValidationError("oops", "thing")
    assert "oops" in str(err)
    assert "not a valid thing" in str(err)


def test_validation_error_attributes():
    err = ValidationError("X", "field", ["A", "B"])
    assert err.value == "X"
    assert err.field_name == "field"
    assert err.valid_values == ["A", "B"]
