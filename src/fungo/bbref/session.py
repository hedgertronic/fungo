"""Baseball-Reference transport: process-wide rate limiting + polite fetch.

Sports Reference publishes hard limits for automated clients: no more than 20
requests/minute to baseball-reference.com, with violators "jailed" up to a day
(https://www.sports-reference.com/bot-traffic.html). Community testing
(pybaseball) found the practical ceiling closer to 10/minute. Every request in
this subpackage therefore routes through a single module-wide rate limiter;
the floor between requests is not user-configurable below the safe default.

Transport is ``curl_cffi`` with Chrome TLS impersonation — B-R's Cloudflare
fingerprint-blocked generic Python clients for months in 2025, and the
impersonated handshake is the durable path.

This module is for polite, on-demand, single-page access — never bulk
harvesting, which Sports Reference's Terms of Use prohibit. Do not build
crawlers on top of it.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from curl_cffi import requests as curl_requests

from fungo.bbref.cache import cache_get, cache_put
from fungo.exceptions import BBRefError, RequestError

#####################################################################
# Base URL / pacing
#####################################################################

BASE_URL = "https://www.baseball-reference.com"

# Sports Reference states 20 req/min; >10/min has earned 1-hour blocks in
# community testing. 6.5s spacing ≈ 9.2 req/min, safely under both.
MIN_REQUEST_INTERVAL = 6.5

_BLOCKED_HINT = (
    "Baseball-Reference blocked the request (HTTP {code}). Sports Reference "
    "rate-limit jail can last up to a day — do NOT retry immediately. Wait it "
    "out, then resume at low volume."
)


#####################################################################
# Process-wide rate limiter
#####################################################################


class _RateLimiter:
    """Enforces a minimum interval between requests, process-wide.

    Thread-safe: concurrent callers queue on the lock and exit at least
    ``interval`` seconds apart, in arrival order.
    """

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._lock = threading.Lock()
        self._last_request = 0.0

    def wait(self) -> None:
        """Block until at least ``interval`` seconds since the last request.

        Uses a monotonic clock (immune to wall-clock jumps) and sleeps while
        holding the lock, so concurrent callers serialize and exit at least
        ``interval`` apart in arrival order — two threads waking together and
        both firing is exactly the burst that earns a Sports Reference block.
        """
        with self._lock:
            now = time.monotonic()
            remaining = self._last_request + self.interval - now
            if remaining > 0:
                time.sleep(remaining)
            self._last_request = time.monotonic()


_limiter = _RateLimiter(MIN_REQUEST_INTERVAL)


#####################################################################
# Fetch
#####################################################################


def _fetch(url: str, params: dict[str, Any] | None) -> bytes:
    """Transport-only fetch via ``curl_cffi`` with Chrome TLS impersonation.

    HTTP failures raise :class:`RequestError` with an ``HTTP <code>`` message
    so :func:`bbref_bytes` can map blocks to :class:`BBRefError`. No retries —
    retrying through a rate-limit block only extends it.

    Args:
        url: Full URL.
        params: Optional query parameters.

    Returns:
        The raw response body.

    Raises:
        RequestError: On any HTTP error status.
    """
    resp = curl_requests.get(url, params=params, impersonate="chrome", timeout=30)
    if resp.status_code >= 400:
        raise RequestError(f"HTTP {resp.status_code} for {url}")
    return bytes(resp.content)


def bbref_bytes(path: str, params: dict[str, Any] | None = None) -> bytes:
    """Fetch a Baseball-Reference URL through the shared rate limiter.

    A cache hit (when :func:`~fungo.bbref.cache.enable_cache` has been
    called) returns immediately with no rate-limit budget spent. On a
    cache miss the request proceeds through the limiter and the successful
    response is stored in the cache.

    A 403/429 raises :class:`BBRefError` with jail guidance instead of
    retrying.

    Args:
        path: Site path (e.g. ``/players/t/troutmi01.shtml``).
        params: Optional query parameters.

    Returns:
        The raw response body.

    Raises:
        BBRefError: On a 403/429 block.
        RequestError: On other transport failures.
    """
    url = f"{BASE_URL}{path}"
    cached = cache_get(url, params)
    if cached is not None:
        return cached
    _limiter.wait()
    try:
        data = _fetch(url, params)
    except RequestError as exc:
        msg = str(exc)
        for code in (403, 429):
            if f"HTTP {code}" in msg:
                raise BBRefError(_BLOCKED_HINT.format(code=code)) from exc
        raise
    cache_put(url, params, data)
    return data


def bbref_html(path: str, params: dict[str, Any] | None = None) -> str:
    """Fetch a Baseball-Reference page and return decoded HTML.

    Args:
        path: Site path.
        params: Optional query parameters.

    Returns:
        The response body decoded as UTF-8.
    """
    return bbref_bytes(path, params).decode("utf-8", errors="replace")
