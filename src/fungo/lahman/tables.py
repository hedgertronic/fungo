"""Lahman table access — discovery-backed downloads with a local cache.

Downloaded tables land under the stdlib user cache dir
(``$XDG_CACHE_HOME``/``~/.cache`` -> ``fungo/lahman/{Table}.csv``), and the
discovered shared-link/file-id map is cached alongside them as
``_index.json``. The database has an annual release cadence, so both caches
persist until :func:`refresh` / :func:`clear_cache`; a cache hit never
touches the network.

Values follow fungo's CSV convention: every value is a string (``""`` for
empty cells). Callers cast themselves.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fungo import http
from fungo.exceptions import ValidationError
from fungo.lahman import api

#####################################################################
# Cache locations
#####################################################################

CACHE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser()
    / "fungo"
    / "lahman"
)

# Leading underscore keeps the index clear of any table's cache filename.
INDEX_FILENAME = "_index.json"

# In-memory index — {"shared_name": str, "files": {table: file_id}};
# populated on first use.
_INDEX: dict[str, Any] | None = None


#####################################################################
# Index (discovered link/file-id map)
#####################################################################


def _index_file() -> Path:
    """Return the on-disk path of the cached discovery index."""
    return CACHE_DIR / INDEX_FILENAME


def _load_index(force_refresh: bool = False) -> dict[str, Any]:
    """Load the discovery index: memory, then disk, then live discovery.

    Args:
        force_refresh: Re-discover from the SABR page, bypassing both caches.

    Returns:
        ``{"shared_name": str, "files": {table_name: file_id}}``.

    Raises:
        LahmanError: If live discovery fails (see :mod:`fungo.lahman.api`).
    """
    global _INDEX
    if _INDEX is not None and not force_refresh:
        return _INDEX

    index_file = _index_file()
    if not force_refresh and index_file.exists():
        try:
            cached = json.loads(index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached = None
        if (
            isinstance(cached, dict)
            and isinstance(cached.get("shared_name"), str)
            and isinstance(cached.get("files"), dict)
            and cached["files"]
        ):
            _INDEX = cached
            return _INDEX

    shared_name = api.discover_shared_name()
    files = api.fetch_table_index(shared_name)
    _INDEX = {"shared_name": shared_name, "files": files}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(_INDEX, indent=2), encoding="utf-8")
    return _INDEX


def _resolve_name(name: str, files: dict[str, str]) -> str:
    """Resolve ``name`` to a canonical table name, case-insensitively.

    A trailing ``.csv`` is tolerated (``"people.csv"`` -> ``"People"``).

    Args:
        name: The requested table name.
        files: The index's ``{table_name: file_id}`` map.

    Returns:
        The canonical table name as it appears in the folder listing.

    Raises:
        ValidationError: If ``name`` matches no table (with the valid table
            names attached for a "did you mean?" suggestion).
    """
    wanted = name[:-4] if name.lower().endswith(".csv") else name
    by_lower = {table.lower(): table for table in files}
    match = by_lower.get(wanted.lower())
    if match is None:
        raise ValidationError(name, "Lahman table", sorted(files))
    return match


#####################################################################
# Public API
#####################################################################


def list_tables(*, force_refresh: bool = False) -> list[str]:
    """List the available Lahman table names.

    Args:
        force_refresh: Re-discover the folder listing before answering.

    Returns:
        Sorted table names (e.g. ``["AllstarFull", ..., "Teams", ...]``).

    Raises:
        LahmanError: If discovery fails.
    """
    return sorted(_load_index(force_refresh=force_refresh)["files"])


def get_table(name: str, *, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch one Lahman table as a list of row dicts.

    Case-tolerant on ``name`` (``"people"`` and ``"People.csv"`` both resolve
    to ``People``). Served from the local cache when present; downloaded and
    cached otherwise.

    Args:
        name: Table name (see :func:`list_tables`).
        force_refresh: Re-discover the index and re-download the table,
            bypassing the caches.

    Returns:
        One ``dict`` per row; every value is a string.

    Raises:
        ValidationError: On an unknown table name.
        LahmanError: If discovery or the download fails.
    """
    index = _load_index(force_refresh=force_refresh)
    table = _resolve_name(name, index["files"])

    cache_file = CACHE_DIR / f"{table}.csv"
    if cache_file.exists() and not force_refresh:
        return http.parse_csv(cache_file.read_bytes())

    raw = api.download_table(index["shared_name"], index["files"][table], table)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(raw)
    return http.parse_csv(raw)


#####################################################################
# Conveniences
#####################################################################


def get_people() -> list[dict[str, Any]]:
    """Fetch the ``People`` table (player biographical data)."""
    return get_table("People")


def get_batting() -> list[dict[str, Any]]:
    """Fetch the ``Batting`` table (season batting stats)."""
    return get_table("Batting")


def get_pitching() -> list[dict[str, Any]]:
    """Fetch the ``Pitching`` table (season pitching stats)."""
    return get_table("Pitching")


def get_fielding() -> list[dict[str, Any]]:
    """Fetch the ``Fielding`` table (season fielding stats)."""
    return get_table("Fielding")


def get_teams() -> list[dict[str, Any]]:
    """Fetch the ``Teams`` table (season team stats and standings)."""
    return get_table("Teams")


#####################################################################
# Cache management
#####################################################################


def clear_cache() -> None:
    """Delete all cached tables and the discovery index (disk and memory)."""
    global _INDEX
    _INDEX = None
    if CACHE_DIR.exists():
        for path in CACHE_DIR.iterdir():
            if path.is_file():
                path.unlink()


def refresh() -> Path:
    """Clear the cache and re-discover the access path from the SABR page.

    Cached tables are deleted (each annual release changes the Box file ids,
    so stale CSVs would otherwise mask the new data) and the link/file-id map
    is re-discovered and re-cached.

    Returns:
        Path to the freshly written index file.

    Raises:
        LahmanError: If discovery fails.
    """
    clear_cache()
    _load_index(force_refresh=True)
    return _index_file()
