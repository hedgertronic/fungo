"""Exception hierarchy for fungo.

All library errors derive from :class:`FungoError`. Transport failures raise
:class:`RequestError`; Savant content errors raise :class:`SavantError`; MLB
Stats API errors raise :class:`MLBStatsError`; FanGraphs errors raise
:class:`FangraphsError`; Baseball-Reference errors raise :class:`BBRefError`;
bad client input raises :class:`ValidationError`, which also subclasses
:class:`ValueError` and emits a ``difflib``-powered "did you mean?" suggestion.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence

#####################################################################
# Base
#####################################################################


class FungoError(Exception):
    """Base class for all fungo errors."""


#####################################################################
# Transport / source errors
#####################################################################


class RequestError(FungoError):
    """Transport failure (HTTP status, network, or timeout). Raised by http.py."""


class SavantError(FungoError):
    """Baseball Savant content error (HTML instead of CSV, parse failure)."""


class MLBStatsError(FungoError):
    """MLB Stats API error."""


class FangraphsError(FungoError):
    """FanGraphs content or access error.

    Raised when FanGraphs serves a Cloudflare challenge (HTTP 403) instead of
    JSON — the API is reachable only because Cloudflare exempts the FanGraphs
    mobile app's HTTP client (``User-Agent: okhttp/4.12.0``); if that exemption
    is withdrawn, every call fails this way — or when a response is not the
    expected JSON shape.
    """


class BBRefError(FungoError):
    """Baseball-Reference content or access error.

    Raised when a page is blocked (Cloudflare challenge / rate-limit jail),
    when an expected table is missing from a page, or when a response is not
    parseable HTML.
    """


#####################################################################
# Client input validation
#####################################################################


class ValidationError(FungoError, ValueError):
    """Bad client input.

    When ``valid_values`` is provided, the message includes a "did you mean?"
    suggestion computed with :func:`difflib.get_close_matches`.

    Args:
        value: The offending input value.
        field_name: Name of the field/parameter the value was supplied for.
        valid_values: Optional collection of accepted values, used to build a
            suggestion and to list the allowed options.
    """

    def __init__(
        self,
        value: object,
        field_name: str,
        valid_values: Sequence[str] | None = None,
    ) -> None:
        self.value = value
        self.field_name = field_name
        self.valid_values = list(valid_values) if valid_values is not None else None

        message = f"{value!r} is not a valid {field_name}."
        if self.valid_values:
            matches = difflib.get_close_matches(
                str(value), self.valid_values, n=1, cutoff=0.6
            )
            if matches:
                message += f" Did you mean {matches[0]!r}?"
            else:
                preview = ", ".join(self.valid_values[:10])
                message += f" Valid values: {preview}"

        super().__init__(message)
