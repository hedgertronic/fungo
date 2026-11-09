"""MLB Stats API core HTTP helper and small utilities.

Pure pass-through: every wrapper in this subpackage returns the raw JSON
response (``dict``) exactly as the API produced it. Transport (retry, backoff,
4xx-vs-5xx handling) lives in :mod:`fungo.http`; this module is only a thin
builder over it — base URL selection (v1 vs v1.1), param assembly, and date
formatting.

Gotchas worth remembering when building params (see also the module docstrings
throughout this subpackage):

- The API rarely errors on malformed input; it returns ``200 OK`` with an empty
  but structurally valid payload. Missing data looks identical to "no data."
- Query-param dates use ``MM/DD/YYYY``; timecodes use ``YYYYMMDD_HHMMSS``.
- ``sportId`` (singular) vs ``sportIds`` (plural) varies by endpoint.
- The live game feed uses ``/api/v1.1``; nearly everything else uses ``/api/v1``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast

from fungo import http
from fungo.exceptions import MLBStatsError

#####################################################################
# Base URL
#####################################################################

BASE_URL = "https://statsapi.mlb.com"


#####################################################################
# HTTP entry point
#####################################################################


def mlb_api(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the MLB Stats API and return the raw JSON payload.

    Transport (retry/backoff, 4xx raising :class:`~fungo.exceptions.RequestError`)
    is handled by :func:`fungo.http.request_json`. This call is intentionally
    routed through the ``http`` module object so tests can monkeypatch
    ``fungo.http.request_json``.

    Args:
        path: API path beginning with ``/api/v1`` or ``/api/v1.1``.
        params: Optional query parameters. ``None``-valued entries are dropped by
            the transport layer.

    Returns:
        The parsed JSON response as a ``dict``.

    Raises:
        RequestError: On a 4xx status or after exhausting transport retries.
        MLBStatsError: If the endpoint returns a top-level JSON array rather
            than an object (no MLB Stats API endpoint does, in practice).
    """
    data = http.request_json(f"{BASE_URL}{path}", params=params)
    if not isinstance(data, dict):
        raise MLBStatsError(
            f"Expected a JSON object from {path}, got {type(data).__name__}"
        )
    return data


#####################################################################
# Date / value formatting
#####################################################################


def _fmt_date(d: str | date | datetime | None) -> str | None:
    """Normalize a date input to ``MM/DD/YYYY``.

    Accepts ``"YYYY-MM-DD"``, ``"MM/DD/YYYY"``, :class:`datetime.date`, and
    :class:`datetime.datetime`. An unrecognized string is passed through
    unchanged; ``None`` returns ``None``.

    Args:
        d: Date as a string, ``date``, ``datetime``, or ``None``.

    Returns:
        The date formatted ``MM/DD/YYYY``, or ``None``.

    Raises:
        TypeError: If ``d`` is not a string, date, datetime, or ``None``.
    """
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.strftime("%m/%d/%Y")
    if isinstance(d, date):
        return d.strftime("%m/%d/%Y")
    if isinstance(d, str):
        s = d.strip()
        # Already MM/DD/YYYY
        if len(s) == 10 and s[2] == "/" and s[5] == "/":
            return s
        # ISO YYYY-MM-DD
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%Y")
        # Fallback — try ISO parsing, else pass through unchanged
        try:
            return datetime.fromisoformat(s).strftime("%m/%d/%Y")
        except ValueError:
            return s
    raise TypeError(f"Cannot format date from {type(d).__name__}: {d!r}")


def _csv(values: Any) -> str | None:
    """Join a list/tuple/set into a comma-separated string; pass scalars through.

    Args:
        values: A collection to join, a scalar to pass through, or ``None``.

    Returns:
        A comma-joined string, the scalar unchanged, or ``None``.
    """
    if values is None:
        return None
    if isinstance(values, (list, tuple, set)):
        return ",".join(str(v) for v in values)
    return cast("str | None", values)
