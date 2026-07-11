"""Lahman Baseball Database — SABR-hosted CSV tables, 1871 to the present.

Sean Lahman's database of season-level batting, pitching, fielding, team, and
biographical data. The canonical home is SABR (https://sabr.org/lahman-database/;
version 2025, released January 2026, covering 1871-2025), which distributes it
under the Creative Commons Attribution-ShareAlike 3.0 Unported license
(CC BY-SA 3.0). The old ``chadwickbureau/baseballdatabank`` GitHub mirror is
deleted and must not be used.

Downloads ride SABR's Box shared links, discovered from the SABR page at
runtime because they change with each annual release (see
:mod:`fungo.lahman.api` for the seam and its fragility). Tables follow fungo's
CSV convention — ``list[dict]`` with every value a string — and are cached
locally under ``fungo/lahman/`` in the user cache dir until
:func:`refresh` / :func:`clear_cache`.
"""

from __future__ import annotations

from fungo.lahman.api import (
    discover_shared_name,
    download_table,
    fetch_table_index,
)
from fungo.lahman.tables import (
    clear_cache,
    get_batting,
    get_fielding,
    get_people,
    get_pitching,
    get_table,
    get_teams,
    list_tables,
    refresh,
)

__all__ = [
    "clear_cache",
    "discover_shared_name",
    "download_table",
    "fetch_table_index",
    "get_batting",
    "get_fielding",
    "get_people",
    "get_pitching",
    "get_table",
    "get_teams",
    "list_tables",
    "refresh",
]
