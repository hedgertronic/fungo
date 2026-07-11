"""Retrosheet data access — first-party parsed CSVs, cached locally.

    The information used here was obtained free of charge from and is
    copyrighted by Retrosheet. Interested parties may contact Retrosheet
    at "www.retrosheet.org".

Retrosheet publishes game logs (1871-), parsed play-by-play (1903-), season
schedules (1877-, including the upcoming season), biographical files, and
per-season statistical CSV bundles as static zip files with no rate limits,
refreshed in roughly twice-yearly bulk releases. Each dataset is downloaded
once on first use, extracted into the stdlib user cache dir
(``$XDG_CACHE_HOME``/``~/.cache`` -> ``fungo/retrosheet/``), and read from
disk on subsequent calls — the same model :mod:`fungo.lookup` uses for the
Chadwick register. Pass ``force_refresh=True`` (or call :func:`refresh`)
after a new Retrosheet release; :func:`clear_cache` deletes the local copies.

Every function returns ``list[dict]`` with every value a string (``""`` for
empty cells) — callers cast themselves. Headered source files keep their own
column names; the headerless game logs and the colliding-header schedules are
keyed by the positional constants :data:`GAME_LOG_FIELDS` /
:data:`SCHEDULE_FIELDS`. Player IDs are Retrosheet IDs — bridge to MLBAM /
FanGraphs / Baseball-Reference via :func:`fungo.lookup.lookup`.
"""

from __future__ import annotations

from fungo.retrosheet.fields import GAME_LOG_FIELDS, SCHEDULE_FIELDS
from fungo.retrosheet.files import (
    clear_cache,
    get_allplayers,
    get_batting,
    get_biofile,
    get_coaches,
    get_fielding,
    get_game_logs,
    get_gameinfo,
    get_pitching,
    get_plays,
    get_relatives,
    get_schedule,
    get_teamstats,
    refresh,
)

__all__ = [
    "GAME_LOG_FIELDS",
    "SCHEDULE_FIELDS",
    "clear_cache",
    "get_allplayers",
    "get_batting",
    "get_biofile",
    "get_coaches",
    "get_fielding",
    "get_game_logs",
    "get_gameinfo",
    "get_pitching",
    "get_plays",
    "get_relatives",
    "get_schedule",
    "get_teamstats",
    "refresh",
]
