"""Opt-in local response cache for Baseball-Reference fetches.

Historical Baseball-Reference pages are immutable once published; repeat
requests for the same URL spend rate-limit budget unnecessarily. Call
:func:`enable_cache` once at application start-up to activate the cache.
The cache is off by default — :func:`~fungo.bbref.session.bbref_bytes`
behaves exactly as today unless :func:`enable_cache` has been called.

Callers fetching current-season pages (standings, daily scoreboards)
should pass a ``ttl`` so stale entries are eventually refreshed. Historical
player pages, game logs, and WAR files are immutable and need no TTL.

Example::

    from fungo import bbref

    # Enable for immutable historical pages (no expiry).
    bbref.enable_cache()

    # Enable with a 1-hour TTL for current-season standings.
    bbref.enable_cache(ttl=3600)

    # Inspect / clean the cache directory.
    deleted = bbref.clear_cache()

    # Turn it off again (the directory is not removed).
    bbref.disable_cache()
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any

#####################################################################
# Cache state
#####################################################################

_CACHE_ENABLED: bool = False
_CACHE_TTL: float | None = None
_CACHE_DIR: Path | None = None

#####################################################################
# Directory helpers
#####################################################################


def _default_cache_dir() -> Path:
    """Return the default cache directory, following lookup.py's convention.

    Resolves ``$XDG_CACHE_HOME`` when set, otherwise ``~/.cache``, then
    appends ``fungo/bbref_cache/``.

    Returns:
        The resolved default path (caller creates it on demand).
    """
    return (
        Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser()
        / "fungo"
        / "bbref_cache"
    )


#####################################################################
# Public API
#####################################################################


def enable_cache(ttl: float | None = None, path: str | Path | None = None) -> Path:
    """Enable the local response cache for Baseball-Reference fetches.

    A cache hit skips the rate limiter entirely — no budget is spent and
    no delay is incurred. Historical B-R pages are immutable; ``ttl=None``
    means entries never expire and is appropriate for anything from a
    completed season. Callers fetching current-season pages (standings,
    daily scoreboards) should pass a ``ttl`` so entries are refreshed as
    the season progresses.

    Args:
        ttl: Entry lifetime in seconds. ``None`` means entries never
            expire.
        path: Cache directory. ``None`` resolves to
            ``<XDG_CACHE_HOME or ~/.cache>/fungo/bbref_cache/``, the
            same convention used by :mod:`fungo.lookup` for the Chadwick
            register.

    Returns:
        The resolved cache directory path.
    """
    global _CACHE_ENABLED, _CACHE_TTL, _CACHE_DIR
    resolved = Path(path) if path is not None else _default_cache_dir()
    resolved.mkdir(parents=True, exist_ok=True)
    _CACHE_DIR = resolved
    _CACHE_TTL = ttl
    _CACHE_ENABLED = True
    return resolved


def disable_cache() -> None:
    """Disable the local response cache (the default state).

    Subsequent calls to :func:`~fungo.bbref.session.bbref_bytes` go
    through the rate limiter and network exactly as if the cache had never
    been enabled. The cache directory and its files are not removed.
    """
    global _CACHE_ENABLED
    _CACHE_ENABLED = False


def clear_cache() -> int:
    """Delete all cache entry files and return the count deleted.

    Works whether or not the cache is currently enabled. The same default
    directory as :func:`enable_cache` is resolved if no custom path was
    set via a prior call to :func:`enable_cache`.

    Returns:
        Number of cache files deleted.
    """
    cache_dir = _CACHE_DIR if _CACHE_DIR is not None else _default_cache_dir()
    if not cache_dir.exists():
        return 0
    count = 0
    for entry in cache_dir.iterdir():
        if entry.is_file():
            entry.unlink()
            count += 1
    return count


#####################################################################
# Cache key + I/O
#####################################################################


def _cache_key(url: str, params: dict[str, Any] | None) -> str:
    """Return the sha256 hex digest for ``(url, sorted-params)``.

    Args:
        url: Full request URL.
        params: Query parameters, or ``None``.

    Returns:
        64-character lowercase hex digest used as the on-disk filename.
    """
    encoded = urllib.parse.urlencode(sorted(params.items())) if params else ""
    return hashlib.sha256(f"{url}{encoded}".encode()).hexdigest()


def cache_get(url: str, params: dict[str, Any] | None) -> bytes | None:
    """Return cached response bytes if the cache is enabled and the entry is fresh.

    Snapshots module globals to locals before any guard so mypy narrows
    them reliably. An :exc:`OSError` on read (e.g. a concurrent deletion)
    is caught and returns ``None`` so the caller falls through to a normal
    fetch.

    Args:
        url: Full request URL.
        params: Query parameters.

    Returns:
        Cached bytes on a hit, ``None`` on a miss or when the cache is
        disabled.
    """
    cache_dir = _CACHE_DIR
    ttl = _CACHE_TTL
    if not _CACHE_ENABLED or cache_dir is None:
        return None
    key = _cache_key(url, params)
    entry = cache_dir / key
    try:
        if not entry.exists():
            return None
        if ttl is not None:
            age = time.time() - entry.stat().st_mtime
            if age > ttl:
                return None
        return entry.read_bytes()
    except OSError:
        return None


def cache_put(url: str, params: dict[str, Any] | None, data: bytes) -> None:
    """Write response bytes to the cache.

    Only called after a successful fetch; errors raise before this point
    so failed responses are never cached. Write failures propagate to the
    caller — they are not silently swallowed.

    Args:
        url: Full request URL.
        params: Query parameters.
        data: Response bytes to store.
    """
    cache_dir = _CACHE_DIR
    if not _CACHE_ENABLED or cache_dir is None:
        return
    key = _cache_key(url, params)
    (cache_dir / key).write_bytes(data)
