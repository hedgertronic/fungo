"""FanGraphs core HTTP helpers — stdlib only.

FanGraphs fronts the entire site with Cloudflare, which TLS-fingerprint-blocks
generic HTTP clients (a browser User-Agent alone gets a 403 JS challenge). The
one known exemption is the HTTP client used by the FanGraphs mobile app:
``User-Agent: okhttp/4.12.0``. Every request in this subpackage sends that UA
through the shared stdlib transport in :mod:`fungo.http`.

That exemption is load-bearing and could be withdrawn at any time; a 403 here
raises :class:`~fungo.exceptions.FangraphsError` naming the condition rather
than a generic transport error.

FanGraphs' JSON differs from Savant's CSV convention: values arrive as native
JSON numbers (full float precision), and some string fields (``Team``,
``Season``) contain embedded HTML anchors. Rows include both ``playerid``
(FanGraphs) and ``xMLBAMID`` (MLBAM), so results join directly to Statcast
data and :mod:`fungo.lookup`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fungo import http
from fungo.exceptions import FangraphsError, RequestError

#####################################################################
# Base URL / headers
#####################################################################

BASE_URL = "https://www.fangraphs.com"

# The FanGraphs mobile app's HTTP client — exempt from the Cloudflare JS
# challenge that blocks every other non-browser client (verified 2026-07).
FG_USER_AGENT = "okhttp/4.12.0"

_BLOCKED_HINT = (
    "FanGraphs returned HTTP 403. The library relies on Cloudflare exempting "
    f"the FanGraphs mobile app's HTTP client (User-Agent: {FG_USER_AGENT!r}); "
    "if this persists, that exemption has likely been withdrawn and the "
    "fungo.fangraphs module needs a new access path."
)


#####################################################################
# HTTP entry points
#####################################################################


def fg_json(path: str, params: dict[str, Any] | None = None) -> Any:
    """Call a FanGraphs ``/api/...`` endpoint and return the raw JSON payload.

    Routed through ``fungo.http.request_json`` (tests monkeypatch that) with
    the okhttp User-Agent. A 403 is re-raised as :class:`FangraphsError` with
    the Cloudflare-exemption diagnosis; other transport errors propagate as
    :class:`~fungo.exceptions.RequestError`.

    Args:
        path: API path beginning with ``/api/``.
        params: Optional query parameters. ``None``-valued entries are dropped
            by the transport layer.

    Returns:
        The parsed JSON value exactly as FanGraphs produced it.

    Raises:
        FangraphsError: On an HTTP 403 (Cloudflare challenge).
        RequestError: On any other transport failure.
    """
    try:
        return http.request_json(
            f"{BASE_URL}{path}",
            params=params,
            headers={"User-Agent": FG_USER_AGENT},
        )
    except RequestError as exc:
        if "HTTP 403" in str(exc):
            raise FangraphsError(_BLOCKED_HINT) from exc
        raise


def fg_json_post(path: str, body: dict[str, Any]) -> Any:
    """POST a JSON body to a FanGraphs ``/api/...`` endpoint.

    Used by the splits leaderboards, whose API is POST-only. Sends the okhttp
    User-Agent like every other call here; a 403 raises
    :class:`FangraphsError` with the Cloudflare-exemption diagnosis.

    Args:
        path: API path beginning with ``/api/``.
        body: The request body, serialized as JSON.

    Returns:
        The parsed JSON response value.

    Raises:
        FangraphsError: On an HTTP 403 (Cloudflare challenge).
        RequestError: On any other transport failure or non-JSON response.
    """
    try:
        return http.request_json(
            f"{BASE_URL}{path}",
            headers={
                "User-Agent": FG_USER_AGENT,
                "Content-Type": "application/json",
            },
            data=json.dumps(body).encode("utf-8"),
        )
    except RequestError as exc:
        if "HTTP 403" in str(exc):
            raise FangraphsError(_BLOCKED_HINT) from exc
        raise


def fg_html(path: str, params: dict[str, Any] | None = None) -> str:
    """Fetch a FanGraphs page and return the decoded HTML.

    Used for the handful of pages with no JSON twin (``guts.aspx``). Sends the
    okhttp User-Agent like every other call in this subpackage.

    Args:
        path: Site path (e.g. ``/guts.aspx``).
        params: Optional query parameters.

    Returns:
        The response body decoded as UTF-8.

    Raises:
        FangraphsError: On an HTTP 403 (Cloudflare challenge).
        RequestError: On any other transport failure.
    """
    try:
        raw = http.request_bytes(
            f"{BASE_URL}{path}",
            params=params,
            headers={"User-Agent": FG_USER_AGENT},
        )
    except RequestError as exc:
        if "HTTP 403" in str(exc):
            raise FangraphsError(_BLOCKED_HINT) from exc
        raise
    return raw.decode("utf-8", errors="replace")


def fg_page_data(path: str) -> dict[str, Any]:
    """Fetch a FanGraphs page and return its embedded ``__NEXT_DATA__`` JSON.

    FanGraphs is a Next.js site: server-rendered pages carry their full data
    payload in a ``<script id="__NEXT_DATA__" type="application/json">`` tag.
    For pages with no public ``/api/...`` twin (Roster Resource), this is the
    reliable access path — one GET returns everything the page shows.

    Args:
        path: Site path (e.g. ``/roster-resource/depth-charts/rangers``).

    Returns:
        The parsed ``__NEXT_DATA__`` object (``props.pageProps`` holds the
        page's data).

    Raises:
        FangraphsError: On a 403, a missing ``__NEXT_DATA__`` tag, or
            unparseable embedded JSON.
        RequestError: On any other transport failure.
    """
    try:
        raw = http.request_bytes(
            f"{BASE_URL}{path}",
            headers={"User-Agent": FG_USER_AGENT},
        )
    except RequestError as exc:
        if "HTTP 403" in str(exc):
            raise FangraphsError(_BLOCKED_HINT) from exc
        raise

    html = raw.decode("utf-8", errors="replace")
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if match is None:
        raise FangraphsError(f"No __NEXT_DATA__ payload found on {path}")

    try:
        data: dict[str, Any] = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise FangraphsError(f"Unparseable __NEXT_DATA__ on {path}: {exc}") from exc
    return data
